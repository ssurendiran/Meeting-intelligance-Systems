import json
from typing import Dict, Any, Set
from openai import OpenAI

from app.core.config import settings
from app.rag.retriever import retrieve
from app.rag.context import pack_context
from .prompts import SYSTEM_SUMMARY_PROMPT, USER_SUMMARY_PROMPT


def allowed_sources(retrieved) -> Set[str]:
    allowed = set()
    for r in retrieved:
        f, a, b = r.get("file"), r.get("line_start"), r.get("line_end")
        if f and isinstance(a, int) and isinstance(b, int):
            allowed.add(f"{f}:{a}-{b}")
    return allowed


def filter_evidence(data: Dict[str, Any], allowed: Set[str]) -> Dict[str, Any]:
    def keep(items):
        out = []
        for it in items:
            ev = it.get("evidence")
            if isinstance(ev, str) and ev in allowed:
                out.append(it)
        return out

    return {
        "decisions": keep(data.get("decisions", [])),
        "action_items": keep(data.get("action_items", [])),
        "risks_or_open_questions": keep(data.get("risks_or_open_questions", [])),
    }


def summarize(meeting_id: str) -> Dict[str, Any]:
    retrieved = retrieve(
        meeting_id=meeting_id,
        question="decisions action items owners due dates risks open questions",
        top_k=12,
    )
    context = pack_context(retrieved, max_chunks=min(10, len(retrieved)))
    allowed = sorted(list(allowed_sources(retrieved)))

    oc = OpenAI(api_key=settings.openai_api_key)

    # IMPORTANT: tell model the ONLY allowed evidence strings
    user_msg = USER_SUMMARY_PROMPT.replace("<<CONTEXT>>", context).replace(
        "<<ALLOWED_EVIDENCE>>", "\n".join(allowed)
    )

    resp = oc.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_SUMMARY_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)

    # deterministic guardrail
    return filter_evidence(data, set(allowed))
