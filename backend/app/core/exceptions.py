from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging_config import logger


class DocuMindError(Exception):
    """Base application error with an HTTP-friendly message."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def documind_error_handler(request: Request, exc: DocuMindError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
