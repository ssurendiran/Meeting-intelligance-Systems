from typing import List, Dict, Any


def pack_context(retrieved: List[Dict[str, Any]], max_chunks: int = 8) -> str:
    # Deduplicate by chunk_id, keep highest score first (already sorted by qdrant)
    seen = set()
    kept = []
    for r in retrieved:
        cid = r.get("chunk_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        kept.append(r)
        if len(kept) >= max_chunks:
            break

    blocks = []
    for r in kept:
        blocks.append(
            f"SOURCE: {r['file']}:{r['line_start']}-{r['line_end']}\n{r['text']}".strip()
        )
    return "\n\n---\n\n".join(blocks)
