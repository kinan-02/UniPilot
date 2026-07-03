"""Prepare agent message attachments (transcript PDF parsing)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, UploadFile

from app.clients.transcript_parser_client import TranscriptParserClientError, parse_transcript_pdf
from app.config import Settings, get_settings
from app.routes.transcript_import import PDF_CONTENT_TYPES, validate_upload


async def build_transcript_attachment(
    upload: UploadFile,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    content = await upload.read()
    validate_upload(
        content,
        content_type=upload.content_type,
        max_bytes=cfg.transcript_import_max_upload_bytes,
    )

    try:
        parse_preview = await parse_transcript_pdf(
            content,
            filename=upload.filename or "transcript.pdf",
            settings=cfg,
        )
    except TranscriptParserClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return {
        "type": "transcript_pdf",
        "filename": upload.filename or "transcript.pdf",
        "contentType": upload.content_type or "application/pdf",
        "parsePreview": parse_preview,
    }


def is_pdf_upload(upload: UploadFile | None) -> bool:
    if upload is None:
        return False
    content_type = (upload.content_type or "").lower()
    if content_type in PDF_CONTENT_TYPES:
        return True
    filename = (upload.filename or "").lower()
    return filename.endswith(".pdf")
