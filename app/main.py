import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import List

from app.core.config import settings
from app.models.schemas import IngestResponse, AskRequest, AskResponse
from app.ingest.parser import parse_transcript
from app.ingest.chunker import chunk_turns
from app.ingest.indexer import index_chunks
from app.rag.retriever import retrieve
from app.rag.context import pack_context
from app.rag.answerer import generate_answer
from app.extract.summarizer import summarize
from app.models.schemas import SummaryRequest, SummaryResponse


app = FastAPI(title="Meeting Intelligence RAG")

@app.post("/summary", response_model=SummaryResponse)
def summary(req: SummaryRequest):
    return summarize(req.meeting_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    meeting_id = str(uuid.uuid4())
    total_chunks = 0
    indexed_files = 0

    all_chunks = []
    for f in files:
        content = await f.read()
        if len(content) > settings.max_file_kb * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename} exceeds MAX_FILE_KB")
        text = content.decode("utf-8", errors="replace")

        turns = parse_transcript(text)
        chunks = chunk_turns(
            meeting_id=meeting_id,
            file_name=f.filename or "transcript.txt",
            turns=turns,
            turns_per_chunk=settings.chunk_turns,
        )
        all_chunks.extend(chunks)
        total_chunks += len(chunks)
        indexed_files += 1

    indexed = index_chunks(all_chunks)

    return IngestResponse(meeting_id=meeting_id, files_indexed=indexed_files, chunks_indexed=indexed)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    top_k = req.top_k or settings.retrieve_top_k
    retrieved = retrieve(req.meeting_id, req.question, top_k=top_k)
    if not retrieved:
        return AskResponse(answer="Not found in transcript.", citations=[], retrieved=[])

    context = pack_context(retrieved, max_chunks=min(8, len(retrieved)))
    answer, citations, debug = generate_answer(req.question, context, retrieved)


    # guardrail: if no citations, degrade response
    if not citations:
        answer = "Not found in transcript."

    return AskResponse(answer=answer, citations=citations, retrieved=retrieved)
