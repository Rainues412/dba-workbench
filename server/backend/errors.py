"""Shared API error response model."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.observability import logger


_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    428: "PRECONDITION_REQUIRED",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    details: object | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    error = {
        "code": code or _ERROR_CODES.get(status_code, "INTERNAL_ERROR"),
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(
        {"error": error},
        status_code=status_code,
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return error_response(request, status_code=exc.status_code, message=message)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return error_response(
        request,
        status_code=422,
        message="Request validation failed",
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        extra={
            "event": "request_error",
            "request_id": _request_id(request),
            "method": request.method,
            "path": request.url.path,
        },
    )
    return error_response(
        request,
        status_code=500,
        message="Internal server error",
    )
