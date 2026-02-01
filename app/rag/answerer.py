import json
import re
from typing import List
from app.core.config import settings
from app.core.openai_client import get_openai_client
from app.models.schemas import Citation
from app.prompts.loader import get_system_prompt, get_user_prompt
from app.guardrails.citations import allowed_ranges


CITE_RE = re.compile(r"\[([^\]:]+):(\d+)-(\d+)\]")




def _parse_citations(answer_text: str) -> List[Citation]:
    """Extract [file:line_start-line_end] citations from answer text using a regex. Deduplicates by (file, line_start, line_end) and returns a list of Citation objects.
    Why available: Fallback when the LLM returns citations in text instead of in the JSON citations field."""
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


def generate_answer(question: str, context: str, retrieved):
    """Generate a RAG answer by calling the LLM with the question and packed context. Parses the response for answer text and citations (file, line_start, line_end). Returns (answer_text, list_of_Citation, debug_dict) where debug_dict includes raw response, allowed evidence list, and token usage.
    Why available: Core RAG answer generation used by /ask (and by streamer for /ask_stream)."""
    allowed_set = allowed_ranges(retrieved)
    allowed_list = sorted([f"{f}:{a}-{b}" for (f, a, b) in allowed_set])

    system_prompt = get_system_prompt("rag_answer")
    user_prompt = get_user_prompt("rag_answer")
    msg = (
        user_prompt
        .replace("<<QUESTION>>", question)
        .replace("<<CONTEXT>>", context)
        .replace("<<ALLOWED_EVIDENCE>>", "\n".join(allowed_list))
    )

    oc = get_openai_client()
    resp = oc.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": msg},
        ],
        temperature=0.1,
    )

    raw = resp.choices[0].message.content or ""
    usage = {}
    if getattr(resp, "usage", None) is not None:
        u = resp.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
        }

    try:
        data = json.loads(raw)
        answer = (data.get("answer") or "").strip()
    except Exception:
        answer = raw.strip()
        data = {"answer": answer}

    parsed: List[Citation] = []

    citations_json = data.get("citations")
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

    if not parsed:
        parsed = _parse_citations(answer)

    # NOTE: DO NOT filter here.
    # Filtering should happen in main.py guardrail layer.

    return answer, parsed, {"raw": raw, "allowed": allowed_list, "usage": usage}
