import traceback
from fastapi import HTTPException

def as_http_500(e: Exception) -> HTTPException:
    """Log exception and return a generic 500 HTTPException (no internal details leaked).
    Why available: Centralized error handling so API never leaks stack traces or internal state to clients."""
    traceback.print_exc()
    return HTTPException(status_code=500, detail="Internal server error")
