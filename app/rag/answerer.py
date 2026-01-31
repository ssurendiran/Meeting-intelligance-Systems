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

def _filter_to_allowed(citations: List[Citation], allowed: Set[Tuple[str, int, int]]) -> List[Citation]:
    if not allowed:
        return citations
    return [c for c in citations if (c.file, c.line_start, c.line_end) in allowed]


def _parse_citations(answer_text: str) -> List[Citation]:
    cites = []
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

    msg = USER_PROMPT.format(question=question, context=context)

    resp = oc.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg},
        ],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or ""

    # Try parse JSON; if model returned plain text, wrap it.
    try:
        data = json.loads(raw)
        answer = data.get("answer", "").strip()
    except Exception:
        answer = raw.strip()
        data = {"answer": answer}

    citations = data.get("citations")
    if isinstance(citations, list) and citations:
        parsed = []
        for c in citations:
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
        # fallback to regex if empty
        if parsed:
            return answer, parsed, {"raw": raw}
    # fallback: parse citations from inline markers
    parsed = _parse_citations(answer)
    allowed = _allowed_ranges(retrieved)
    parsed = _filter_to_allowed(parsed, allowed)

    return answer, parsed, {"raw": raw}
