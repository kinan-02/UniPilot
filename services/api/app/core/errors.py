from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def envelope_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": message,
        },
    )


def first_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Validation failed"

    error = errors[0]
    message = error.get("msg", "Validation failed")

    if isinstance(message, str) and message.startswith("Value error, "):
        return message.removeprefix("Value error, ")

    return str(message)


async def http_exception_handler(
    _request: Request,
    exc: HTTPException,
) -> JSONResponse:
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return envelope_error(exc.status_code, message)


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return envelope_error(400, first_validation_message(exc))


async def unhandled_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        detail = exc.detail
        error_message = detail if isinstance(detail, str) else str(detail)
        return envelope_error(exc.status_code, error_message)

    return envelope_error(500, "Internal server error")
