from dataclasses import dataclass
from typing import List, Dict, Any
from .parser import Turn


@dataclass
class Chunk:
    chunk_id: str
    text: str
    payload: Dict[str, Any]


def chunk_turns(
    *,
    meeting_id: str,
    file_name: str,
    turns: List[Turn],
    turns_per_chunk: int = 8,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    if not turns:
        return chunks

    buf: List[Turn] = []
    chunk_index = 0

    def flush():
        nonlocal chunk_index, buf
        if not buf:
            return
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
            "speakers": speakers,
        }
        chunks.append(Chunk(chunk_id=cid, text=body, payload=payload))
        buf = []

    for t in turns:
        buf.append(t)
        if len(buf) >= turns_per_chunk:
            flush()

    flush()
    return chunks
