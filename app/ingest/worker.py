import os
from typing import List
from app.core.config import settings
from app.ingest.parser import parse_transcript
from app.ingest.chunker import chunk_turns
from app.ingest.indexer import index_chunks
from app.ingest.meeting_stats import compute_meeting_stats, save_meeting_metadata


def run_index_job(meeting_id: str, upload_dir: str) -> tuple[int, int]:
    """Read files(s) from upload_dir, parse, chunk, index into Qdrant, and compute meeting stats (duration, who talked most); save metadata for RAG. Returns (files_indexed, chunks_indexed).
    Why available: Single entry point for sync and async ingest so /ingest and background /ingest_async both use the same pipeline."""
    all_chunks = []
    all_turns: List = []
    files_indexed = 0

    for fname in sorted(os.listdir(upload_dir)):
        path = os.path.join(upload_dir, fname)
        if not os.path.isfile(path):
            continue

        with open(path, "rb") as f:
            content = f.read()

        if len(content) > settings.max_file_kb * 1024:
            continue

        text = content.decode("utf-8", errors="replace")
        turns = parse_transcript(text)
        all_turns.extend(turns)
        chunks = chunk_turns(
            meeting_id=meeting_id,
            file_name=fname,
            turns=turns,
            turns_per_chunk=settings.chunk_turns,
        )
        all_chunks.extend(chunks)
        files_indexed += 1

    chunks_indexed = index_chunks(all_chunks)

    data_root = os.path.join(os.getcwd(), "data")
    meeting_meta = compute_meeting_stats(all_turns)
    save_meeting_metadata(meeting_id, meeting_meta, data_root)

    return files_indexed, chunks_indexed
