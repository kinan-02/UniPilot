"""Tests for application exception handlers."""

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from app.main import http_exception_handler, validation_exception_handler


@pytest.mark.asyncio
async def test_validation_exception_handler_includes_errors():
    exc = RequestValidationError(errors=[{"loc": ["body", "file"], "msg": "field required", "type": "missing"}])
    response = await validation_exception_handler(None, exc)
    assert response.status_code == 400
    payload = response.body.decode()
    assert "Validation failed" in payload
    assert "field required" in payload


@pytest.mark.asyncio
async def test_http_exception_handler_uses_fallback_detail_for_non_string():
    response = await http_exception_handler(None, HTTPException(status_code=403, detail={"reason": "denied"}))
    assert response.status_code == 403
    assert "Request failed" in response.body.decode()
