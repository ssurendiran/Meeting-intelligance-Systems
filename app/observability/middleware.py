import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()

        # attach to request state for handlers if needed
        request.state.request_id = rid

        response = await call_next(request)

        dur_ms = (time.perf_counter() - start) * 1000.0
        # simple structured log line (JSON-ish)
        print(f'{{"request_id":"{rid}","path":"{request.url.path}","method":"{request.method}","status":{response.status_code},"latency_ms":{dur_ms:.2f}}}')
        response.headers["x-request-id"] = rid
        return response



def get_request_id(request: Request) -> str:
    # middleware sets this
    return getattr(request.state, "request_id", "unknown")
