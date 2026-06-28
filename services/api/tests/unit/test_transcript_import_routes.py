"""Unit tests for transcript import route helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.clients.transcript_parser_client import TranscriptParserClientError
from app.routes.transcript_import import validate_upload

VALID_PASSWORD = "StrongPass123!"


async def _register_token(client, email: str = "transcript-route@example.com") -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


def test_validate_upload_rejects_empty_file():
    with pytest.raises(HTTPException) as exc_info:
        validate_upload(b"", content_type="application/pdf", max_bytes=1024)
    assert exc_info.value.status_code == 400


def test_validate_upload_rejects_oversized_file():
    with pytest.raises(HTTPException) as exc_info:
        validate_upload(b"x" * 11, content_type="application/pdf", max_bytes=10)
    assert exc_info.value.status_code == 400


def test_validate_upload_rejects_non_pdf_content_type():
    with pytest.raises(HTTPException) as exc_info:
        validate_upload(b"%PDF-1.4", content_type="text/plain", max_bytes=1024)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_parse_route_maps_parser_client_error(auth_client):
    token = await _register_token(auth_client)
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.routes.transcript_import.parse_transcript_pdf",
        AsyncMock(
            side_effect=TranscriptParserClientError(status_code=422, detail="Invalid PDF layout"),
        ),
    ):
        response = await auth_client.post(
            "/transcript-import/parse",
            headers=headers,
            files={"file": ("transcript.pdf", b"%PDF-1.4", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "Invalid PDF layout"
