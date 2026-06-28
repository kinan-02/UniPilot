"""Unit tests for transcript parser HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.transcript_parser_client import TranscriptParserClientError, parse_transcript_pdf


@pytest.mark.asyncio
async def test_parse_transcript_pdf_returns_parse_result():
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {"parseResult": {"courses": [], "warnings": [], "parseMetadata": {}}},
            "error": None,
        },
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        result = await parse_transcript_pdf(b"%PDF-sample", filename="transcript.pdf")

    assert result == {"courses": [], "warnings": [], "parseMetadata": {}}


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_on_parser_error():
    response = httpx.Response(
        400,
        json={"success": False, "data": None, "error": "Uploaded file must be a PDF"},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"bad", filename="transcript.pdf")

    assert exc_info.value.status_code == 400
    assert "PDF" in exc_info.value.detail


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_on_invalid_success_payload():
    response = httpx.Response(
        200,
        json={"success": False, "data": None, "error": "failed"},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"%PDF-sample", filename="transcript.pdf")

    assert exc_info.value.status_code == 502
