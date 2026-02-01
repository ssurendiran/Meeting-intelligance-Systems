from dataclasses import dataclass
from typing import Dict, Any, Iterator, Iterable, List
from .parser import Turn
from .meeting_stats import timestamp_to_seconds


@dataclass
class Chunk:
    """A contiguous segment of transcript lines with metadata (file, line range, timestamps, speakers).
    Why available: Standard unit for indexing and retrieval; payload is stored in Qdrant for RAG."""

    chunk_id: str
    text: str
    payload: Dict[str, Any]


def chunk_turns_stream(
    *,
    meeting_id: str,
    file_name: str,
    turns: Iterable[Turn],
    turns_per_chunk: int = 8,
) -> Iterator[Chunk]:
    """Streaming chunker: consumes turns iterator and yields chunks incrementally (each chunk has chunk_id, text, payload).
    Why available: Used at ingest so we can chunk and index without holding all turns in memory."""
    buf: List[Turn] = []
    chunk_index = 0

    def flush() -> Chunk | None:
        """Build one chunk from the current buffer and return it; clear buffer. Used by chunk_turns_stream when buffer is full or at end."""
        nonlocal chunk_index, buf
        if not buf:
            return None

        chunk_index += 1
        line_start = buf[0].line_no
        line_end = buf[-1].line_no
        time_start = buf[0].timestamp
        time_end = buf[-1].timestamp
        speakers = sorted({t.speaker for t in buf})

        body = "\n".join([f"[{t.timestamp}] {t.speaker}: {t.text}" for t in buf]).strip()
        cid = f"{meeting_id}:{file_name}:{chunk_index}"

        payload = {
            "meeting_id": meeting_id,
            "file": file_name,
            "chunk_id": cid,
            "line_start": line_start,
            "line_end": line_end,
            "time_start": time_start,
            "time_end": time_end,
            "time_start_sec": timestamp_to_seconds(time_start),
            "time_end_sec": timestamp_to_seconds(time_end),
            "speakers": speakers,
        }

        buf = []
        return Chunk(chunk_id=cid, text=body, payload=payload)

    for t in turns:
        buf.append(t)
        if len(buf) >= turns_per_chunk:
            ch = flush()
            if ch:
                yield ch

    ch = flush()
    if ch:
        yield ch


def chunk_turns(
    *,
    meeting_id: str,
    file_name: str,
    turns: List[Turn],
    turns_per_chunk: int = 8,
) -> List[Chunk]:
    """Split a list of transcript turns into chunks of up to turns_per_chunk lines. Each chunk has a unique chunk_id, text, and payload (file, line_start, line_end, time_start, time_end, speakers). Returns a list of Chunk objects.
    Why available: Non-streaming API used by worker when all turns are already in memory."""
    return list(
        chunk_turns_stream(
            meeting_id=meeting_id,
            file_name=file_name,
            turns=turns,
            turns_per_chunk=turns_per_chunk,
        )
    )
