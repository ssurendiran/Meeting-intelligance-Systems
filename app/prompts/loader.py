"""
Versioned prompt loader: reads prompts from app/prompts/{version}/{component}.yaml.
Use PROMPT_VERSION (default v1) to select version.
"""
from pathlib import Path

import yaml

# Base path: app/prompts/ (next to this file)
_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompts(
    component: str,
    version: str | None = None,
) -> dict[str, str]:
    """Load prompt templates for a component. Returns dict with keys "system", "user" (user optional); values may contain placeholders like <<CONTEXT>>, <<QUESTION>>, <<ALLOWED_EVIDENCE>>.
    Why available: Centralizes versioned prompts so RAG answer, query rewrite, and summary extraction can be updated without code changes."""
    if version is None:
        try:
            from app.core.config import settings
            version = getattr(settings, "prompt_version", "v1")
        except Exception:
            version = "v1"

    path = _PROMPTS_DIR / version / f"{component}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f) or {}

    out: dict[str, str] = {}
    for key in ("system", "user"):
        val = data.get(key)
        if val is not None:
            out[key] = val.strip() if isinstance(val, str) else str(val).strip()
    return out


def get_system_prompt(component: str, version: str | None = None) -> str:
    """Load and return the 'system' prompt template for the given component (e.g. rag_answer, extract_summary). Raises ValueError if the component has no system prompt in the specified version."""
    prompts = load_prompts(component, version=version)
    if "system" not in prompts:
        raise ValueError(f"Component {component} has no 'system' prompt in version {version}")
    return prompts["system"]


def get_user_prompt(component: str, version: str | None = None) -> str:
    """Load and return the 'user' prompt template for the given component. Raises ValueError if the component has no user prompt in the specified version.
    Why available: Used by answerer, summarizer, and query_rewriter to build the user message with placeholders filled."""
    prompts = load_prompts(component, version=version)
    if "user" not in prompts:
        raise ValueError(f"Component {component} has no 'user' prompt in version {version}")
    return prompts["user"]
