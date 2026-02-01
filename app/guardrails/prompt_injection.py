from typing import Tuple

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "you are chatgpt",
    "reveal",
    "exfiltrate",
    "api key",
    "password",
    "token",
]

def detect_prompt_injection(text: str) -> Tuple[bool, str]:
    """Lightweight heuristic detector: returns (True, pattern) if text contains typical injection phrasing (e.g. 'ignore previous instructions', 'system prompt'). Transcript is untrusted; we still allow retrieval but prepend a security note to context.
    Why available: Reduces risk of prompt injection via uploaded transcript content; used by pack_context."""
    t = (text or "").lower()
    for p in INJECTION_PATTERNS:
        if p in t:
            return True, p
    return False, ""
