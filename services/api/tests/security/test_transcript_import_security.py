"""Security tests for transcript import endpoints."""

from unittest.mock import patch

import pytest

from app.middleware.auth_rate_limiter import enforce_transcript_import_rate_limit

VALID_PASSWORD = "StrongPass123!"
SAMPLE_PDF = b"%PDF-1.4\nsample transcript\n"
PARSE_RESULT = {
    "courses": [],
    "studentId": None,
    "studentName": None,
    "warnings": [],
    "parseMetadata": {
        "pageCount": 1,
        "extractor": "pymupdf-text",
        "pipelineVersion": "0.1.0-stub",
        "textCharCount": 10,
        "ocrUsed": False,
    },
}


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_transcript_import_parse_enforces_rate_limit(auth_client, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_IMPORT_RATE_LIMIT_MAX", "1")
    from app.config import get_settings

    get_settings.cache_clear()

    token = await register_access_token(auth_client, "transcript-rate-limit@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.routes.transcript_import.parse_transcript_pdf", return_value=PARSE_RESULT):
        first = await auth_client.post(
            "/transcript-import/parse",
            headers=headers,
            files={"file": ("transcript.pdf", SAMPLE_PDF, "application/pdf")},
        )
        assert first.status_code == 200

        second = await auth_client.post(
            "/transcript-import/parse",
            headers=headers,
            files={"file": ("transcript.pdf", SAMPLE_PDF, "application/pdf")},
        )
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_enforce_transcript_import_rate_limit_raises_429(monkeypatch):
    from fastapi import HTTPException, Request

    monkeypatch.setenv("TRANSCRIPT_IMPORT_RATE_LIMIT_MAX", "1")
    from app.config import get_settings
    from app.middleware.auth_rate_limiter import reset_in_memory_rate_limit_store

    get_settings.cache_clear()
    reset_in_memory_rate_limit_store()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/transcript-import/parse",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)

    await enforce_transcript_import_rate_limit(request, "user-1")
    with pytest.raises(HTTPException) as exc_info:
        await enforce_transcript_import_rate_limit(request, "user-1")

    assert exc_info.value.status_code == 429
