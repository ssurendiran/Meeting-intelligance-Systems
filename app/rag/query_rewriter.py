"""
Query rewriting: expand user question into 1-3 retrieval-friendly queries for multi-query RAG.
"""
import logging
from typing import List

from app.core.openai_client import get_openai_client
from app.core.config import settings
from app.prompts.loader import get_system_prompt

logger = logging.getLogger(__name__)


def rewrite_queries(question: str, max_queries: int = 3) -> List[str]:
    """Use the LLM to rewrite or expand the user question into up to max_queries retrieval-friendly queries for multi-query RAG. Deduplicates and preserves order. On LLM failure or empty result, returns [question] as the single query.
    Why available: Improves retrieval recall by running multiple queries (e.g. rephrased, keyword-focused) and merging results; used by _ask_retrieve_and_build_context."""
    question = (question or "").strip()
    if not question:
        return [question]

    try:
        oc = get_openai_client()
        rewrite_system = get_system_prompt("rag_rewrite")
        resp = oc.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role": "system", "content": rewrite_system},
                {"role": "user", "content": question},
            ],
            temperature=0.2,
            max_tokens=150,
        )
        raw = (resp.choices[0].message.content or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        # Dedupe while preserving order; cap at max_queries
        seen = set()
        out: List[str] = []
        for ln in lines:
            key = ln.lower()
            if key not in seen and len(out) < max_queries:
                seen.add(key)
                out.append(ln)
        if out:
            return out
    except Exception as e:
        logger.warning("query_rewrite_failed", exc_info=True, extra={"question_preview": question[:80]})
    return [question]
