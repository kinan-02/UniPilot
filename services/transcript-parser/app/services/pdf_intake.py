"""PDF intake validation."""

from __future__ import annotations

PDF_MAGIC = b"%PDF-"


def is_pdf_bytes(content: bytes) -> bool:
    return content.startswith(PDF_MAGIC)


def validate_upload_size(content: bytes, *, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise ValueError(f"PDF exceeds maximum upload size of {max_bytes} bytes")
