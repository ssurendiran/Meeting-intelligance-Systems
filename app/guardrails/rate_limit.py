import time
from collections import defaultdict
from fastapi import HTTPException
from starlette.requests import Request


class SimpleRateLimiter:
    """Token-bucket style rate limiter; in-memory (per process). Used by API to cap requests per client IP.
    Why available: Protects the API from abuse and ensures fair usage across clients."""

    def __init__(self, max_requests: int, window_seconds: int):
        """Configure limiter: max_requests per window_seconds per client IP."""
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.storage = defaultdict(list)  # ip -> [timestamps]

    def check(self, request: Request):
        """Raise 429 if the client has exceeded the rate limit; otherwise record the request. Called on each protected endpoint."""
        now = time.time()
        ip = request.client.host if request.client else "unknown"

        timestamps = self.storage[ip]

        # Remove expired timestamps
        self.storage[ip] = [
            t for t in timestamps if now - t < self.window_seconds
        ]

        if len(self.storage[ip]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry later.",
            )

        self.storage[ip].append(now)
