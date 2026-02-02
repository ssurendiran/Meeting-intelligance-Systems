import re
import uuid
import os
import time
import json
from collections import OrderedDict
from typing import List, Optional
from fastapi.responses import StreamingResponse
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Request,
    BackgroundTasks,
)

from app.core.config import settings
from app.models.schemas import (
    IngestResponse,
    AskRequest,
    AskResponse,
    SummaryRequest,
    SummaryResponse,
    IngestAsyncResponse,
    JobStatusResponse,
    LimitsResponse,
    GenerateSampleTranscriptRequest,
    GenerateSampleTranscriptResponse,
)

from app.ingest.parser import parse_transcript, has_valid_transcript_format
from app.ingest.chunker import chunk_turns
from app.ingest.indexer import index_chunks
from app.ingest.meeting_stats import (
    compute_meeting_stats,
    format_meeting_overview,
    save_meeting_metadata,
    load_meeting_metadata,
    timestamp_to_seconds,
)
from app.ingest.duplicate_check import (
    content_hash,
    get_existing_meeting_id,
    register_ingested,
)
from app.ingest.jobs import JOBS, Job
from app.ingest.worker import run_index_job

from app.rag.context import pack_context
from app.rag.answerer import generate_answer

from app.extract.summarizer import summarize

from app.guardrails.citations import (
    allowed_ranges,
    normalize_and_filter_citations,
    require_citations_or_refuse,
)
from app.guardrails.errors import as_http_500
from app.guardrails.prompt_injection import detect_prompt_injection
from app.guardrails.rate_limit import SimpleRateLimiter

from app.rag.query_rewriter import rewrite_queries
from app.rag.retriever import retrieve_multi, retrieve_chunks_containing_time

from app.core.openai_client import get_openai_client


# -------------------------
# App setup
# -------------------------

app = FastAPI(title="Meeting Intelligence RAG")


RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60
rate_limiter = SimpleRateLimiter(max_requests=RATE_LIMIT_REQUESTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS)

UPLOAD_ROOT = os.path.join(os.getcwd(), "data", "uploads")
DATA_ROOT = os.path.join(os.getcwd(), "data")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# Short-term conversation memory per meeting: last (question, answer, retrieved) for follow-ups like "give me more detail"
ASK_MEMORY_MAX = 200
ASK_MEMORY: OrderedDict[str, dict] = OrderedDict()

FOLLOW_UP_PHRASES = (
    "more detail", "elaborate", "expand", "tell me more", "what else", "go on",
    "continue", "give me more", "can you elaborate", "expand on that", "further detail",
)


def _is_follow_up(question: str, has_memory: bool = False) -> bool:
    """Returns True if the question looks like a follow-up (short/vague, or contains phrases like 'more detail', 'elaborate').
    Why available: Used by /ask and /ask_stream to decide whether to use stored previous question for retrieval and to include previous answer in context."""
    if not (question or "").strip():
        return False
    q = (question or "").strip().lower()
    # Short vague questions (why? how? what about cost?) when we have prior context
    if has_memory and (len(q.split()) <= 3 or len(q) <= 15):
        return True
    if len(q.split()) <= 5 and any(p in q for p in FOLLOW_UP_PHRASES):
        return True
    return any(p in q for p in FOLLOW_UP_PHRASES)


def _get_ask_memory(meeting_id: str) -> Optional[dict]:
    """Returns the last stored (question, answer, retrieved) for this meeting, or None.
    Why available: Enables follow-up questions (e.g. 'give me more detail') by reusing the prior question for retrieval and prior answer in context."""
    return ASK_MEMORY.get(meeting_id)


def _save_ask_memory(meeting_id: str, question: str, answer: str, retrieved: list) -> None:
    """Stores the last ask exchange (question, answer, retrieved) for this meeting; evicts oldest when over ASK_MEMORY_MAX.
    Why available: Required so the next request for the same meeting can treat follow-ups correctly via _get_ask_memory."""
    while len(ASK_MEMORY) >= ASK_MEMORY_MAX and ASK_MEMORY:
        ASK_MEMORY.popitem(last=False)
    ASK_MEMORY[meeting_id] = {"question": question, "answer": answer, "retrieved": list(retrieved)}
    ASK_MEMORY.move_to_end(meeting_id)


def _parse_timestamps_from_question(text: str) -> List[str]:
    """Extracts timestamps from the question: [HH:MM:SS] or standalone HH:MM:SS (e.g. 'at 00:12:46'). Returns a list of timestamp strings.
    Why available: Lets users ask about a specific time (e.g. 'What was said at 00:12:46?'); used to filter retrieval and context."""
    if not (text or "").strip():
        return []
    seen: set = set()
    out: List[str] = []
    for ts in re.findall(r"\[(\d{2}:\d{2}:\d{2})\]", text):
        if ts not in seen:
            seen.add(ts)
            out.append(ts)
    for ts in re.findall(r"(?<!\d)(\d{2}:\d{2}:\d{2})(?!\d)", text):
        if ts not in seen:
            seen.add(ts)
            out.append(ts)
    return out


def _parse_speaker_from_question(text: str, known_speakers: Optional[List[str]] = None) -> Optional[str]:
    """Extracts a speaker name from the question when it matches known meeting speakers (e.g. 'What did Alice say?'). Returns the speaker name or None.
    Why available: Lets users filter by speaker via natural language like time; used for retrieval and context when known_speakers is available."""
    if not (text or "").strip() or not known_speakers:
        return None
    q = text.strip().lower()
    for speaker in known_speakers:
        if not (speaker or "").strip():
            continue
        s = speaker.strip()
        sl = s.lower()
        if sl not in q:
            continue
        # Require word boundary so "Alice" does not match "Alicia"
        if not re.search(r"\b" + re.escape(sl) + r"\b", q):
            continue
        # Require speaker-related phrase to avoid false positives
        phrases = [
            r"what did\s+" + re.escape(sl) + r"\s+say",
            r"what did\s+" + re.escape(sl) + r"\s+think",
            r"what did\s+" + re.escape(sl) + r"\s+mention",
            r"what did\s+" + re.escape(sl) + r"\s+suggest",
            r"\b" + re.escape(sl) + r"\s+said\b",
            r"\b" + re.escape(sl) + r"\s+think",
            r"\b" + re.escape(sl) + r"'s\b",
            r"focus on\s+" + re.escape(sl),
            r"only\s+" + re.escape(sl),
            r"from\s+" + re.escape(sl),
        ]
        if any(re.search(p, q) for p in phrases):
            return s
    return None


NO_TRANSCRIPT_FOR_TIME = "No transcript found for that time."


def _ask_retrieve_and_build_context(
    meeting_id: str,
    question: str,
    previous_question: str | None,
    top_k: int,
    data_root: str,
    speaker_filter: str | None = None,
    stored_previous_question: str | None = None,
    stored_previous_answer: str | None = None,
) -> tuple[str, dict]:
    """Runs retrieval (multi-query + optional time/speaker filter), builds context string, and returns status and payload.
    Returns ("ok", {retrieved, context, parsed_ts, meeting_meta, retr_ms}) on success; ("not_found", {retr_ms}) or ("time_not_found", {retr_ms}) on failure.
    Why available: Shared by /ask and /ask_stream to avoid duplicated logic; centralizes follow-up handling, time filtering, and speaker filtering."""
    parsed_ts = _parse_timestamps_from_question(question)
    if not parsed_ts and previous_question:
        parsed_ts = _parse_timestamps_from_question(previous_question)
    if not parsed_ts and stored_previous_question:
        parsed_ts = _parse_timestamps_from_question(stored_previous_question)
    meeting_meta = load_meeting_metadata(meeting_id, data_root)

    # Parse speaker from question (like time) when known speakers available; request body overrides
    known_speakers = [s["speaker"] for s in (meeting_meta.get("speaker_stats") or [])] if meeting_meta else []
    parsed_speaker = _parse_speaker_from_question(question, known_speakers)
    if not parsed_speaker and previous_question:
        parsed_speaker = _parse_speaker_from_question(previous_question, known_speakers)
    if not parsed_speaker and stored_previous_question:
        parsed_speaker = _parse_speaker_from_question(stored_previous_question, known_speakers)
    effective_speaker = speaker_filter or parsed_speaker

    # For follow-ups, use stored previous question + semantic anchor (avoid user phrase as query noise)
    use_for_retrieval = question
    if _is_follow_up(question, has_memory=bool(stored_previous_question or previous_question)) and (stored_previous_question or previous_question):
        use_for_retrieval = (stored_previous_question or previous_question or "").strip() + " Provide more detail with citations."

    queries = rewrite_queries(use_for_retrieval)
    t_retr = time.perf_counter()
    retrieved = retrieve_multi(meeting_id, queries, top_k=top_k, speaker_filter=effective_speaker)
    retr_ms = (time.perf_counter() - t_retr) * 1000.0

    if parsed_ts:
        req_sec = timestamp_to_seconds(parsed_ts[0])
        time_chunks = retrieve_chunks_containing_time(
            meeting_id, req_sec, limit=20, speaker_filter=effective_speaker
        )
        if time_chunks:
            by_cid = {r["chunk_id"]: r for r in time_chunks}
            for r in retrieved:
                if r.get("chunk_id") and r["chunk_id"] not in by_cid:
                    by_cid[r["chunk_id"]] = r
            retrieved = list(by_cid.values())

    if not retrieved:
        return ("not_found", {"retr_ms": retr_ms})

    first_sec = last_sec = None
    if meeting_meta and "first_timestamp" in meeting_meta and "last_timestamp" in meeting_meta:
        first_sec = timestamp_to_seconds(meeting_meta["first_timestamp"])
        last_sec = timestamp_to_seconds(meeting_meta["last_timestamp"])
    else:
        time_starts = [r["time_start"] for r in retrieved if r.get("time_start")]
        time_ends = [r["time_end"] for r in retrieved if r.get("time_end")]
        if time_starts:
            first_sec = min(timestamp_to_seconds(t) for t in time_starts)
        if time_ends:
            last_sec = max(timestamp_to_seconds(t) for t in time_ends)

    if parsed_ts and first_sec is not None and last_sec is not None:
        for ts in parsed_ts:
            ts_sec = timestamp_to_seconds(ts)
            if ts_sec < first_sec or ts_sec > last_sec:
                return ("time_not_found", {"retr_ms": retr_ms})

    if parsed_ts:
        req_sec = timestamp_to_seconds(parsed_ts[0])
        filtered = [
            r for r in retrieved
            if r.get("time_start") is not None and r.get("time_end") is not None
            and timestamp_to_seconds(r["time_start"]) <= req_sec <= timestamp_to_seconds(r["time_end"])
        ]
        if filtered:
            retrieved = filtered
        elif any(r.get("time_start") is not None for r in retrieved):
            return ("time_not_found", {"retr_ms": retr_ms})

    if not meeting_meta:
        meeting_meta = load_meeting_metadata(meeting_id, data_root)
    overview = format_meeting_overview(meeting_meta) if meeting_meta else ""
    context = pack_context(retrieved, max_chunks=min(8, len(retrieved)))
    if overview:
        context = overview + "\n\n---\n\n" + context
    if parsed_ts:
        context = (
            f"STRICT TIME FILTER: The user asked about time [{parsed_ts[0]}]. "
            "Answer ONLY from transcript content at this time. Do not use content from before or after. "
            "If the context has no content for this time, respond exactly: No transcript found for that time.\n\n---\n\n"
            + context
        )
    if effective_speaker:
        context = (
            f"SPEAKER FILTER: The user asked to focus on speaker \"{effective_speaker}\". "
            "Base your answer only on what this speaker said in the context below.\n\n---\n\n"
            + context
        )
    # Follow-up: include previous reply so the model can elaborate; do not treat it as evidence
    if _is_follow_up(question, has_memory=bool(stored_previous_answer)) and stored_previous_answer:
        context = (
            "Treat Previous reply as non-authoritative. Only the transcript context counts as evidence.\n\n"
            f"Previous reply: {stored_previous_answer}\n\n"
            f"User follow-up: {question.strip()}\n\n"
            "Use the transcript below to add more detail or elaborate on what was said. Keep citations from the transcript.\n\n---\n\n"
            + context
        )
    return ("ok", {"retrieved": retrieved, "context": context, "parsed_ts": parsed_ts, "meeting_meta": meeting_meta, "retr_ms": retr_ms})


# -------------------------
# Root
# -------------------------

@app.get("/")
def root():
    """Returns a minimal welcome payload with app name and docs URL.
    Why available: Gives clients and load balancers a simple root endpoint to confirm the API is running."""
    return {"app": "Meeting Intelligence RAG", "docs": "/docs"}


@app.get("/health")
def health():
    """Returns 200 OK with status. Used by load balancers and probes (e.g. Cloudflare) to check if the API is up.
    Why available: Standard endpoint for uptime checks and orchestration."""
    return {"status": "ok"}


# -------------------------
# Limits (for UI / clients)
# -------------------------

@app.get("/limits", response_model=LimitsResponse)
def limits(request: Request):
    """Returns current API limits (max file size, chunk turns, retrieve top_k, rate limit window).
    Why available: Lets the UI and clients display or enforce limits before uploading or asking."""
    rate_limiter.check(request)
    return LimitsResponse(
        max_file_kb=settings.max_file_kb,
        chunk_turns=settings.chunk_turns,
        retrieve_top_k=settings.retrieve_top_k,
        rate_limit_requests=RATE_LIMIT_REQUESTS,
        rate_limit_window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )


# -------------------------
# Summary
# -------------------------

@app.post("/summary", response_model=SummaryResponse)
def summary(req: SummaryRequest, request: Request):
    """Extracts a structured meeting summary (about, discussions, planning, outcome, MOM, decisions, action items, risks) for a meeting ID via RAG + LLM.
    Why available: Core feature so users can get a concise summary without reading the full transcript."""
    rate_limiter.check(request)

    try:
        uuid.UUID(req.meeting_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid meeting_id (must be UUID)")

    data, usage = summarize(req.meeting_id, DATA_ROOT)
    return SummaryResponse(**data)


# -------------------------
# Sync Ingest
# -------------------------

@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request, files: List[UploadFile] = File(...)):
    """Parses uploaded transcript file(s), chunks them, indexes to Qdrant, and returns meeting_id and counts. Rejects duplicate content (same hash returns existing meeting_id).
    Why available: Primary way to add meeting transcripts so they can be queried via /ask and /summary."""
    rate_limiter.check(request)

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    # Read and validate all files first; collect contents for duplicate check
    contents: List[bytes] = []
    all_turns = []
    file_infos: List[tuple] = []  # (filename, turns) per file

    for f in files:
        content = await f.read()
        if len(content) > settings.max_file_kb * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"{f.filename} exceeds 1 MB limit ({settings.max_file_kb} KB).",
            )
        text = content.decode("utf-8", errors="replace")
        if not has_valid_transcript_format(text):
            raise HTTPException(
                status_code=400,
                detail="Incorrect file. Transcripts should be text files with speaker labels and timestamps (e.g. [HH:MM:SS] Speaker: text).",
            )
        turns = parse_transcript(text)
        contents.append(content)
        all_turns.extend(turns)
        file_infos.append((f.filename or "transcript.txt", turns))

    # If this exact content was already ingested, return 200 with existing meeting_id (idempotent)
    combined_hash = content_hash(contents)
    existing_meeting_id = get_existing_meeting_id(combined_hash, DATA_ROOT)
    if existing_meeting_id:
        return IngestResponse(
            meeting_id=existing_meeting_id,
            files_indexed=0,
            chunks_indexed=0,
        )

    meeting_id = str(uuid.uuid4())
    sync_dir = os.path.join(UPLOAD_ROOT, "sync", meeting_id)
    os.makedirs(sync_dir, exist_ok=True)

    filenames = [f.filename or "transcript.txt" for f in files]
    all_chunks = []
    for (content, (out_name, turns)) in zip(contents, file_infos):
        chunks = chunk_turns(
            meeting_id=meeting_id,
            file_name=out_name,
            turns=turns,
            turns_per_chunk=settings.chunk_turns,
        )
        all_chunks.extend(chunks)
        out_path = os.path.join(sync_dir, out_name)
        with open(out_path, "wb") as out:
            out.write(content)

    chunks_indexed = index_chunks(all_chunks)
    meeting_meta = compute_meeting_stats(all_turns)
    save_meeting_metadata(meeting_id, meeting_meta, DATA_ROOT)
    register_ingested(combined_hash, meeting_id, DATA_ROOT)
    last_meeting_id_path = os.path.join(DATA_ROOT, "last_meeting_id.txt")
    with open(last_meeting_id_path, "w") as f:
        f.write(meeting_id)

    return IngestResponse(
        meeting_id=meeting_id,
        files_indexed=len(files),
        chunks_indexed=chunks_indexed,
    )


# -------------------------
# Ask (strict RAG)
# -------------------------

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    """Answers a question about a meeting using RAG: multi-query retrieval, context build, LLM answer, and citation guardrails. Returns answer and citations.
    Why available: Main Q&A feature; answers are grounded in retrieved chunks and citations reference transcript lines."""
    rate_limiter.check(request)
    top_k = req.top_k or settings.retrieve_top_k

    try:
        if top_k <= 0:
            raise HTTPException(status_code=400, detail="top_k must be > 0")

        hit, _ = detect_prompt_injection(req.question)
        if hit:
            raise HTTPException(status_code=400, detail="Query contains disallowed content.")

        memory = _get_ask_memory(req.meeting_id)
        stored_q = memory["question"] if memory and _is_follow_up(req.question, has_memory=bool(memory)) else None
        stored_a = memory["answer"] if memory and _is_follow_up(req.question, has_memory=bool(memory)) else None

        status, data = _ask_retrieve_and_build_context(
            req.meeting_id, req.question, req.previous_question, top_k, DATA_ROOT,
            speaker_filter=req.speaker_filter,
            stored_previous_question=stored_q,
            stored_previous_answer=stored_a,
        )
        retrieved = data.get("retrieved") or []
        context = data.get("context") or ""

        if status == "not_found":
            return AskResponse(answer="Not found in transcript.", citations=[], retrieved=[])

        if status == "time_not_found":
            return AskResponse(answer=NO_TRANSCRIPT_FOR_TIME, citations=[], retrieved=[])

        parsed_ts = data["parsed_ts"]

        answer, citations, _debug = generate_answer(req.question, context, retrieved)

        allowed = allowed_ranges(retrieved)
        citations = normalize_and_filter_citations(citations, allowed)
        answer = require_citations_or_refuse(answer, citations)
        if parsed_ts and not citations:
            answer = NO_TRANSCRIPT_FOR_TIME

        _save_ask_memory(req.meeting_id, req.question, answer, retrieved)
        return AskResponse(answer=answer, citations=citations, retrieved=retrieved)

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "openai" in err_msg or "api_key" in err_msg or "authentication" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="LLM service unavailable. Check OPENAI_API_KEY and network.",
            )
        if "qdrant" in err_msg or "connection" in err_msg or "connect" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="Vector store unavailable. Check Qdrant is running (e.g. docker-compose up -d).",
            )
        raise as_http_500(e)


# -------------------------
# Async Ingest (large files)
# -------------------------

@app.post("/ingest_async", response_model=IngestAsyncResponse)
async def ingest_async(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    """Saves uploaded files to a job directory, enqueues a background index job, and returns job_id. Client polls GET /jobs/{job_id} for status (queued / running / done / failed).
    Why available: Allows large uploads without blocking; UI can show progress and retry on failure."""
    rate_limiter.check(request)

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    meeting_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    job_dir = os.path.join(UPLOAD_ROOT, job_id)
    os.makedirs(job_dir, exist_ok=True)

    for f in files:
        content = await f.read()
        if len(content) > settings.max_file_kb * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename} exceeds 1 MB limit")

        out_path = os.path.join(job_dir, f.filename or "transcript.txt")
        with open(out_path, "wb") as out:
            out.write(content)

    JOBS[job_id] = Job(
        job_id=job_id,
        meeting_id=meeting_id,
        status="queued",
        created_at=time.time(),
    )

    def _runner():
        """Background task: run index job and update job status."""
        j = JOBS[job_id]
        try:
            j.status = "running"
            j.started_at = time.time()
            files_indexed, chunks_indexed = run_index_job(meeting_id, job_dir)
            j.files_indexed = files_indexed
            j.chunks_indexed = chunks_indexed
            j.status = "done"
            j.finished_at = time.time()
        except Exception as e:
            j.status = "failed"
            j.error = str(e)
            j.finished_at = time.time()

    background_tasks.add_task(_runner)

    return IngestAsyncResponse(job_id=job_id, meeting_id=meeting_id)


# -------------------------
# Job Status
# -------------------------

@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, request: Request):
    """Returns the status of an async ingest job (queued / running / done / failed), plus files_indexed, chunks_indexed, and error if failed.
    Why available: Lets clients poll after POST /ingest_async to know when indexing is done or if it failed."""
    rate_limiter.check(request)

    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        meeting_id=job.meeting_id,
        status=job.status,
        files_indexed=job.files_indexed,
        chunks_indexed=job.chunks_indexed,
        error=job.error,
    )


# -------------------------
# Generate sample transcript (LLM, for UI download / test upload)
# -------------------------

SAMPLE_TRANSCRIPT_SYSTEM = """You generate a meeting transcript as plain text.
Rules:
- Every line that is spoken MUST be in this exact format: [HH:MM:SS] SpeakerName: text
- Use timestamps in order (e.g. 00:00:00, 00:00:15, 00:01:00).
- Include discussions, decisions, action items, and a few risks or open questions.
- Output ONLY the transcript, no explanations. No markdown."""


# Guardrail: line prefixes that must never be shown (prompt/role leakage)
_SAMPLE_TRANSCRIPT_FORBIDDEN_LINE_PREFIXES = (
    "system:",
    "user:",
    "human:",
    "assistant:",
    "instruction:",
    "prompt:",
)


def _is_transcript_safe_line(line: str) -> bool:
    """Returns True if the line is safe to stream (no system/user/assistant/prompt-style prefixes that could leak instructions).
    Why available: Guardrail for streamed sample transcript so we never expose prompt or role text to the user."""
    s = line.strip()
    if not s:
        return True
    lower = s.lower()
    return not any(lower.startswith(p) for p in _SAMPLE_TRANSCRIPT_FORBIDDEN_LINE_PREFIXES)


def _stream_sample_transcript_only(client, user_msg: str, approx_lines: int):
    """Streams only the LLM-generated transcript lines (filters unsafe prefixes) and caps output at 1 MB.
    Why available: Used when generate_sample_transcript is called with stream=True; keeps response safe and bounded."""
    max_bytes = 1 * 1024 * 1024
    resp = client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SAMPLE_TRANSCRIPT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=min(4096, max(512, approx_lines * 40)),
        stream=True,
        stream_options={"include_usage": True},
    )
    total = 0
    buffer = ""
    last_usage = None
    for chunk in resp:
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            last_usage = usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None) or ""
        if not content:
            continue
        buffer += content
        while "\n" in buffer:
            line, _, buffer = buffer.partition("\n")
            line_with_newline = line + "\n"
            if _is_transcript_safe_line(line):
                b = line_with_newline.encode("utf-8")
                total += len(b)
                if total <= max_bytes:
                    yield b
            if total > max_bytes:
                buffer = ""
                break
        if total > max_bytes:
            buffer = ""
            break
        if len(buffer.encode("utf-8")) + total > max_bytes:
            break
    if buffer and total <= max_bytes and _is_transcript_safe_line(buffer):
        yield buffer.encode("utf-8")


@app.post("/generate_sample_transcript")
def generate_sample_transcript(req: GenerateSampleTranscriptRequest, request: Request):
    """Generates a sample meeting transcript via LLM from a topic (and optional participants); response can be streamed or returned in full.
    Why available: Lets users create demo transcripts for testing ingest and RAG without uploading a real file."""
    rate_limiter.check(request)

    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    
    participants = req.participants if req.participants else None
    if participants:
        names = [n.strip() for n in participants if n and n.strip()]
        if len(names) < 2:
            raise HTTPException(status_code=400, detail="At least 2 participants required")
        if len(names) > 10:
            raise HTTPException(status_code=400, detail="At most 10 participants allowed")
        speaker_list = ", ".join(names)
        user_msg = (
            f"Generate a meeting transcript with EXACTLY these {len(names)} speakers and NO other names: {speaker_list}. "
            f"Every spoken line MUST have SpeakerName exactly one of: {speaker_list}. Do not add any other speaker names. "
            f"About {req.approx_lines} lines. Topic: {topic}. Use format [HH:MM:SS] SpeakerName: text on every spoken line."
        )
    else:
        user_msg = (
            f"Generate a meeting transcript with {req.num_speakers} speakers, about {req.approx_lines} lines. "
            f"Topic: {topic}. Use format [HH:MM:SS] Speaker: text on every spoken line."
        )
    client = get_openai_client()

    if req.stream:
        return StreamingResponse(
            _stream_sample_transcript_only(client, user_msg, req.approx_lines),
            media_type="text/plain; charset=utf-8",
        )

    resp = client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SAMPLE_TRANSCRIPT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=min(4096, max(512, req.approx_lines * 40)),
    )
    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="No transcript generated")
    if not has_valid_transcript_format(raw):
        raise HTTPException(status_code=422, detail="Generated text did not match transcript format")
    if len(raw.encode("utf-8")) > 1 * 1024 * 1024:
        raw = raw[: (1 * 1024 * 1024 - 100)].rsplit("\n", 1)[0]
    return GenerateSampleTranscriptResponse(transcript=raw)


