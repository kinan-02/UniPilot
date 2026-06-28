"""Unit tests for PDF intake helpers."""

import pytest

from app.services.pdf_intake import is_pdf_bytes, validate_upload_size


def test_is_pdf_bytes_detects_pdf_magic():
    assert is_pdf_bytes(b"%PDF-1.4 sample") is True
    assert is_pdf_bytes(b"not-a-pdf") is False


def test_validate_upload_size_rejects_large_payload():
    with pytest.raises(ValueError, match="maximum upload size"):
        validate_upload_size(b"x" * 11, max_bytes=10)
