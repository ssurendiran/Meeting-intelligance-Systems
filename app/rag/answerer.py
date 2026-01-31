import json
import re
from typing import List, Tuple, Set
from openai import OpenAI

from app.core.config import settings
from app.models.schemas import Citation
from .prompts import SYSTEM_PROMPT, USER_PROMPT


CITE_RE = re.compile(r"\[([^\]:]+):(\d+)-(\d+)\]")


def _allowed_ranges(retrieved) -> Set[Tuple[str, int, int]]:
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


def _filter_to_allowed(citations: List[Citation], allowed: Set[Tuple[str, int, int]]) -> List[Citation]:
    """
    Keep citations only if they overlap a retrieved source range.
    Clamp them into the retrieved range so we never cite outside retrieved context.
    """
    if not allowed:
        return citations

    allowed_by_file = {}
    for f, a, b in allowed:
        allowed_by_file.setdefault(f, []).append((a, b))

    out: List[Citation] = []
    seen = set()

    for c in citations:
        for a, b in allowed_by_file.get(c.file, []):
            if _overlaps(c.line_start, c.line_end, a, b):
                ns = max(c.line_start, a)
                ne = min(c.line_end, b)
                key = (c.file, ns, ne)
                if key not in seen:
                    seen.add(key)
                    out.append(Citation(file=c.file, line_start=ns, line_end=ne))
                break

    return out


def _parse_citations(answer_text: str) -> List[Citation]:
    cites: List[Citation] = []
    seen = set()
    for m in CITE_RE.finditer(answer_text):
        f, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        key = (f, a, b)
        if key in seen:
            continue
        seen.add(key)
        cites.append(Citation(file=f, line_start=a, line_end=b))
    return cites


def generate_answer(question: str, context: str, retrieved) -> Tuple[str, List[Citation], dict]:
    oc = OpenAI(api_key=settings.openai_api_key)

    allowed_set = _allowed_ranges(retrieved)
    allowed_list = sorted([f"{f}:{a}-{b}" for (f, a, b) in allowed_set])

    msg = (
        USER_PROMPT
        .replace("<<QUESTION>>", question)
        .replace("<<CONTEXT>>", context)
        .replace("<<ALLOWED_EVIDENCE>>", "\n".join(allowed_list))
    )

    resp = oc.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg},
        ],
        temperature=0.1,
    )

    raw = resp.choices[0].message.content or ""

    # Expect JSON. If model misbehaves, fallback to raw text.
    try:
        data = json.loads(raw)
        answer = (data.get("answer") or "").strip()
    except Exception:
        answer = raw.strip()
        data = {"answer": answer}

    citations_json = data.get("citations")
    parsed: List[Citation] = []

    # Preferred: parse citations from JSON
    if isinstance(citations_json, list):
        for c in citations_json:
            try:
                parsed.append(
                    Citation(
                        file=str(c["file"]),
                        line_start=int(c["line_start"]),
                        line_end=int(c["line_end"]),
                    )
                )
            except Exception:
                pass

    # Fallback: parse inline markers like [transcript1.txt:1-8]
    if not parsed:
        parsed = _parse_citations(answer)

    parsed = _filter_to_allowed(parsed, allowed_set)

    return answer, parsed, {"raw": raw, "allowed": allowed_list}
