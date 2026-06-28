"""Integration tests for transcript import routes."""

from unittest.mock import patch

import pytest

VALID_PASSWORD = "StrongPass123!"
SAMPLE_PDF = b"%PDF-1.4\n00960401 Data Science 88 3.0\n"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_transcript_import_parse_requires_auth(auth_client):
    response = await auth_client.post(
        "/transcript-import/parse",
        files={"file": ("transcript.pdf", SAMPLE_PDF, "application/pdf")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_transcript_import_parse_returns_preview(auth_client):
    token = await register_access_token(auth_client, "transcript-import@example.com")
    parse_result = {
        "courses": [],
        "studentId": None,
        "studentName": None,
        "warnings": [],
        "parseMetadata": {
            "pageCount": 1,
            "extractor": "pymupdf-text",
            "pipelineVersion": "0.3.0-official-he-en",
            "textCharCount": 42,
            "ocrUsed": False,
        },
    }

    with patch(
        "app.routes.transcript_import.parse_transcript_pdf",
        return_value=parse_result,
    ):
        response = await auth_client.post(
            "/transcript-import/parse",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("transcript.pdf", SAMPLE_PDF, "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["parsePreview"]["parseMetadata"]["pageCount"] == 1


@pytest.mark.asyncio
async def test_transcript_import_parse_rejects_empty_upload(auth_client):
    token = await register_access_token(auth_client, "transcript-empty@example.com")
    response = await auth_client.post(
        "/transcript-import/parse",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("transcript.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["error"].lower()
