"""Unit tests for app/core/errors.py — covers all handler branches."""
import pytest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    envelope_error,
    first_validation_message,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


def _make_request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    return Request(scope)


# ---------------------------------------------------------------------------
# envelope_error
# ---------------------------------------------------------------------------


def test_envelope_error_sets_status_code():
    response = envelope_error(404, "not found")
    assert response.status_code == 404


def test_envelope_error_body_structure():
    response = envelope_error(422, "bad input")
    import json
    body = json.loads(response.body)
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] == "bad input"


# ---------------------------------------------------------------------------
# first_validation_message
# ---------------------------------------------------------------------------


def test_first_validation_message_returns_fallback_when_no_errors():
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = []
    assert first_validation_message(exc) == "Validation failed"


def test_first_validation_message_strips_value_error_prefix():
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [{"msg": "Value error, email must be valid"}]
    assert first_validation_message(exc) == "email must be valid"


def test_first_validation_message_returns_plain_msg_unchanged():
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [{"msg": "field required"}]
    assert first_validation_message(exc) == "field required"


def test_first_validation_message_handles_missing_msg_key():
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [{}]
    result = first_validation_message(exc)
    assert result == "Validation failed"


def test_first_validation_message_uses_only_first_error():
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [
        {"msg": "first error"},
        {"msg": "second error"},
    ]
    assert first_validation_message(exc) == "first error"


# ---------------------------------------------------------------------------
# http_exception_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_handler_string_detail():
    request = _make_request()
    exc = HTTPException(status_code=403, detail="forbidden")
    response = await http_exception_handler(request, exc)
    assert response.status_code == 403
    import json
    body = json.loads(response.body)
    assert body["error"] == "forbidden"
    assert body["success"] is False


@pytest.mark.asyncio
async def test_http_exception_handler_non_string_detail():
    """Non-string detail should be coerced to str — covers the str(detail) branch."""
    request = _make_request()
    exc = HTTPException(status_code=400, detail={"code": "INVALID"})
    response = await http_exception_handler(request, exc)
    assert response.status_code == 400
    import json
    body = json.loads(response.body)
    assert "INVALID" in body["error"]


@pytest.mark.asyncio
async def test_http_exception_handler_401():
    request = _make_request()
    exc = HTTPException(status_code=401, detail="unauthorized")
    response = await http_exception_handler(request, exc)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# validation_exception_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_exception_handler_returns_400():
    request = _make_request()
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [{"msg": "field required"}]
    response = await validation_exception_handler(request, exc)
    assert response.status_code == 400
    import json
    body = json.loads(response.body)
    assert body["error"] == "field required"


# ---------------------------------------------------------------------------
# unhandled_exception_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unhandled_exception_handler_generic_exception_returns_500():
    request = _make_request()
    exc = ValueError("something broke internally")
    response = await unhandled_exception_handler(request, exc)
    assert response.status_code == 500
    import json
    body = json.loads(response.body)
    assert body["error"] == "Internal server error"
    assert body["success"] is False


@pytest.mark.asyncio
async def test_unhandled_exception_handler_starlette_http_exception_uses_its_status():
    request = _make_request()
    exc = StarletteHTTPException(status_code=404, detail="not found")
    response = await unhandled_exception_handler(request, exc)
    assert response.status_code == 404
    import json
    body = json.loads(response.body)
    assert body["error"] == "not found"


@pytest.mark.asyncio
async def test_unhandled_exception_handler_starlette_non_string_detail():
    request = _make_request()
    exc = StarletteHTTPException(status_code=422, detail={"reason": "schema"})
    response = await unhandled_exception_handler(request, exc)
    assert response.status_code == 422
    import json
    body = json.loads(response.body)
    assert "schema" in body["error"]
