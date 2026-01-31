import traceback
from fastapi import HTTPException

def as_http_500(e: Exception) -> HTTPException:
    traceback.print_exc()
    return HTTPException(status_code=500, detail=str(e))
