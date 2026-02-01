import json
from typing import Dict, Any, Iterable, List

from app.core.config import settings
from app.guardrails.citations import allowed_ranges, normalize_and_filter_citations, require_citations_or_refuse
from app.core.openai_client import get_openai_client
from app.models.schemas import Citation
from app.prompts.loader import get_system_prompt, get_user_prompt
from app.utils.retry import with_retry


def stream_answer_events(question: str, context: str, retrieved: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """Stream RAG answer as a sequence of events for Server-Sent Events. Emits: delta events with incremental text; a final event with full answer and citations (parsed and guardrailed); or an error event with message. Citations are computed only at the end after the full response is parsed.
    Why available: Powers /ask_stream so the UI can show the answer as it is generated for better perceived latency."""
    oc = get_openai_client()

    allowed = allowed_ranges(retrieved)
    allowed_list = sorted([f"{f}:{a}-{b}" for (f, a, b) in allowed])

    system_prompt = get_system_prompt("rag_answer")
    user_prompt = get_user_prompt("rag_answer")
    msg = (
        user_prompt
        .replace("<<QUESTION>>", question)
        .replace("<<CONTEXT>>", context)
        .replace("<<ALLOWED_EVIDENCE>>", "\n".join(allowed_list))
    )

    try:
        stream = with_retry(lambda: oc.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg},
            ],
            temperature=0.1,
            stream=True,
        ))

        buf = []

        for ev in stream:
            delta = ev.choices[0].delta.content if ev.choices else None
            if delta:
                buf.append(delta)
                yield {"type": "delta", "text": delta}

        raw = "".join(buf).strip()

        # Try to parse JSON (prompt requests JSON only). Fallback to raw text.
        try:
            data = json.loads(raw)
            answer = (data.get("answer") or "").strip()
            cites_raw = data.get("citations") or []
        except Exception:
            answer = raw
            cites_raw = []

        parsed: List[Citation] = []
        if isinstance(cites_raw, list):
            for c in cites_raw:
                try:
                    parsed.append(Citation(
                        file=str(c["file"]),
                        line_start=int(c["line_start"]),
                        line_end=int(c["line_end"]),
                    ))
                except Exception:
                    pass

        parsed = normalize_and_filter_citations(parsed, allowed)
        answer = require_citations_or_refuse(answer, parsed)

        # If answer became refusal, citations must be empty (consistent semantics).
        if answer == "Not found in transcript.":
            parsed = []

        yield {
            "type": "final",
            "answer": answer,
            "citations": [c.model_dump() for c in parsed],
        }

    except Exception as e:
        yield {"type": "error", "message": str(e)}
