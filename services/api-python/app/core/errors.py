from fastapi import Request
from fastapi.responses import JSONResponse


async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": "Internal server error",
        },
    )
