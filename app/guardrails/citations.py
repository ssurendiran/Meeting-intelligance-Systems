from typing import List, Dict, Any, Set, Tuple
from app.models.schemas import Citation

def allowed_ranges(retrieved: List[Dict[str, Any]]) -> Set[Tuple[str, int, int]]:
    """Return the set of (file, line_start, line_end) ranges from retrieved chunks.
    Why available: Defines which citation ranges are valid so we can filter or clamp LLM citations to retrieved context only."""
    allowed = set()
    for r in retrieved:
        f = r.get("file")
        a = r.get("line_start")
        b = r.get("line_end")
        if f and isinstance(a, int) and isinstance(b, int):
            allowed.add((f, a, b))
    return allowed

def _overlaps(a1: int, a2: int, b1: int, b2: int) -> bool:
    """Return True if range [a1, a2] overlaps range [b1, b2]. Used by citation_overlaps_range and normalize_and_filter_citations."""
    return not (a2 < b1 or b2 < a1)


def citation_overlaps_range(
    file: str,
    line_start: int,
    line_end: int,
    allowed: Set[Tuple[str, int, int]],
) -> bool:
    """Return True if the citation (file, line_start, line_end) overlaps any allowed range. Shared for app and tests."""
    for f, a, b in allowed:
        if f == file and _overlaps(line_start, line_end, a, b):
            return True
    return False

def normalize_and_filter_citations(
    citations: List[Citation],
    allowed: Set[Tuple[str, int, int]],
) -> List[Citation]:
    """Keep citations only if they overlap a retrieved (allowed) source range; clamp each citation into that range so we never cite outside retrieved context.
    Why available: Guardrail so /ask and /ask_stream only return citations that reference actual retrieved transcript lines."""
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
    """Return the answer if at least one citation exists; otherwise return the refusal message 'Not found in transcript.' so the user knows the model had no evidence.
    Why available: Prevents answers that are not grounded in the transcript from being shown to the user."""
    if citations:
        return answer
    return "Not found in transcript."
