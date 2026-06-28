"""Transcript parser service tests."""

from io import BytesIO

import fitz
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "2024-1")
    page.insert_text((72, 96), "00960401 Introduction to Data Science 3.0 85")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["service"] == "transcript-parser"
    assert payload["data"]["status"] == "ok"


async def test_parse_rejects_non_pdf(client):
    response = await client.post(
        "/parse",
        files={"file": ("transcript.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Uploaded file must be a PDF"


async def test_parse_rejects_oversized_upload(client, pdf_bytes, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    get_settings.cache_clear()
    response = await client.post(
        "/parse",
        files={"file": ("transcript.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert "maximum upload size" in response.json()["error"]


async def test_parse_requires_internal_token_when_configured(client, pdf_bytes, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "secret-token")
    get_settings.cache_clear()
    response = await client.post(
        "/parse",
        files={"file": ("transcript.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 401


async def test_parse_accepts_pdf_with_internal_token(client, pdf_bytes, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "secret-token")
    get_settings.cache_clear()
    response = await client.post(
        "/parse",
        headers={"X-Internal-Service-Token": "secret-token"},
        files={"file": ("transcript.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    parse_result = payload["data"]["parseResult"]
    assert parse_result["parseMetadata"]["pageCount"] == 1
    assert parse_result["parseMetadata"]["extractor"] == "pymupdf-text"
    assert parse_result["parseMetadata"]["pipelineVersion"] == "0.3.0-official-he-en"


async def test_parse_returns_warning_for_empty_text_pdf(client):
    document = fitz.open()
    document.new_page()
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    empty_pdf = buffer.getvalue()

    response = await client.post(
        "/parse",
        files={"file": ("empty.pdf", empty_pdf, "application/pdf")},
    )
    assert response.status_code == 200
    warnings = response.json()["data"]["parseResult"]["warnings"]
    assert any("No extractable text" in warning for warning in warnings)


async def test_parse_returns_422_when_pipeline_raises(client, monkeypatch):
    def boom(_content: bytes):
        raise RuntimeError("pipeline failure")

    monkeypatch.setattr("app.routes.parse.parse_technion_transcript_pdf", boom)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "sample")
    buffer = BytesIO()
    document.save(buffer)
    document.close()

    response = await client.post(
        "/parse",
        files={"file": ("transcript.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "Unable to parse transcript PDF"


async def test_parse_returns_400_when_pipeline_value_error(client, monkeypatch):
    def invalid(_content: bytes):
        raise ValueError("Invalid PDF structure")

    monkeypatch.setattr("app.routes.parse.parse_technion_transcript_pdf", invalid)

    response = await client.post(
        "/parse",
        files={"file": ("transcript.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid PDF structure"
