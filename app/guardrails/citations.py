from typing import List, Dict, Any, Set, Tuple
from app.models.schemas import Citation

def allowed_ranges(retrieved: List[Dict[str, Any]]) -> Set[Tuple[str, int, int]]:
    allowed = set()
    for r in retrieved:
        f = r.get("file")
        a = r.get("line_start")
        b = r.get("line_end")
        if f and isinstance(a, int) and isinstance(b, int):
            allowed.add((f, a, b))
    return allowed

def _overlaps(a1: int, a2: int, b1: int, b2: int) -> bool:
    # [a1,a2] overlaps [b1,b2]
    return not (a2 < b1 or b2 < a1)

def normalize_and_filter_citations(
    citations: List[Citation],
    allowed: Set[Tuple[str, int, int]],
) -> List[Citation]:
    """
    Keep citations only if they overlap a retrieved (allowed) source range.
    Clamp the citation into that range so we never cite outside retrieved context.
    """
    if not allowed:
        return citations

    normalized: List[Citation] = []
    allowed_by_file: Dict[str, List[Tuple[int, int]]] = {}
    for f, a, b in allowed:
        allowed_by_file.setdefault(f, []).append((a, b))

    for c in citations:
        file_ranges = allowed_by_file.get(c.file, [])
        for a, b in file_ranges:
            if _overlaps(c.line_start, c.line_end, a, b):
                # clamp into allowed range
                ns = max(c.line_start, a)
                ne = min(c.line_end, b)
                normalized.append(Citation(file=c.file, line_start=ns, line_end=ne))
                break

    # de-dupe
    uniq = {(c.file, c.line_start, c.line_end): c for c in normalized}
    return list(uniq.values())

def require_citations_or_refuse(answer: str, citations: List[Citation]) -> str:
    if citations:
        return answer
    return "Not found in transcript."
