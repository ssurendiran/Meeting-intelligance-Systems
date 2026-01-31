import uuid
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException

from app.core.config import settings
from app.models.schemas import (
    IngestResponse,
    AskRequest,
    AskResponse,
    SummaryRequest,
    SummaryResponse,
)
from app.ingest.parser import parse_transcript
from app.ingest.chunker import chunk_turns
from app.ingest.indexer import index_chunks

from app.rag.retriever import retrieve
from app.rag.context import pack_context
from app.rag.answerer import generate_answer

from app.extract.summarizer import summarize

from app.guardrails.citations import (
    allowed_ranges,
    normalize_and_filter_citations,
    require_citations_or_refuse,
)

from app.guardrails.errors import as_http_500
from app.observability.middleware import RequestTimingMiddleware


app = FastAPI(title="Meeting Intelligence RAG")
app.add_middleware(RequestTimingMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/summary", response_model=SummaryResponse)
def summary(req: SummaryRequest):
    # Validate UUID format for meeting_id (helps catch client mistakes)
    try:
        uuid.UUID(req.meeting_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid meeting_id (must be UUID)")

    return summarize(req.meeting_id)


@app.post("/ingest", response_model=IngestResponse)
async def ingest(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    meeting_id = str(uuid.uuid4())
    indexed_files = 0
    all_chunks = []

    for f in files:
        content = await f.read()
        if len(content) > settings.max_file_kb * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"{f.filename} exceeds MAX_FILE_KB ({settings.max_file_kb}KB)",
            )

        text = content.decode("utf-8", errors="replace")
        turns = parse_transcript(text)

        chunks = chunk_turns(
            meeting_id=meeting_id,
            file_name=f.filename or "transcript.txt",
            turns=turns,
            turns_per_chunk=settings.chunk_turns,
        )
        all_chunks.extend(chunks)
        indexed_files += 1

    indexed = index_chunks(all_chunks)
    return IngestResponse(
        meeting_id=meeting_id,
        files_indexed=indexed_files,
        chunks_indexed=indexed,
    )


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        # Validate UUID format for meeting_id (helps catch client mistakes)
        try:
            uuid.UUID(req.meeting_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid meeting_id (must be UUID)")

        top_k = req.top_k or settings.retrieve_top_k
        if top_k <= 0:
            raise HTTPException(status_code=400, detail="top_k must be > 0")

        retrieved = retrieve(req.meeting_id, req.question, top_k=top_k)
        if not retrieved:
            return AskResponse(answer="Not found in transcript.", citations=[], retrieved=[])

        context = pack_context(retrieved, max_chunks=min(8, len(retrieved)))
        answer, citations, _debug = generate_answer(req.question, context, retrieved)

        # Guardrail: if model returns empty answer, refuse
        if not (answer or "").strip():
            return AskResponse(answer="Not found in transcript.", citations=[], retrieved=retrieved)

        # Guardrail 1: only allow citations that match retrieved ranges
        allowed = allowed_ranges(retrieved)
        citations = normalize_and_filter_citations(citations, allowed)

        # Guardrail 2: if no valid citations remain, refuse
        answer = require_citations_or_refuse(answer, citations)

        return AskResponse(answer=answer, citations=citations, retrieved=retrieved)

    except HTTPException:
        raise
    except Exception as e:
        raise as_http_500(e)
