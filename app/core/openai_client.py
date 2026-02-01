"""OpenAI client for chat and embeddings (api_key from config)."""
from typing import Any

from app.core.config import settings
from openai import OpenAI

_openai_client: Any = None


def get_openai_client() -> OpenAI:
    """Return a singleton OpenAI client configured with api_key from settings. Used for chat completions and embeddings across the app.
    Why available: Single place to get the OpenAI client so all modules (answerer, retriever, indexer, summarizer, query_rewriter, streamer) use the same config."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client
