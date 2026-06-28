"""Unit tests for transcript import route helpers."""

import pytest
from fastapi import HTTPException

from app.routes.transcript_import import validate_upload


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
