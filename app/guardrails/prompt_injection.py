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
    """
    Very lightweight heuristic detector.
    We treat transcript as untrusted input. If it contains typical injection phrasing,
    we still allow retrieval but we tighten generation instructions.
    """
    t = (text or "").lower()
    for p in INJECTION_PATTERNS:
        if p in t:
            return True, p
    return False, ""
