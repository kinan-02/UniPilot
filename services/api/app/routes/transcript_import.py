"""Transcript PDF import routes (preview only — persistence is a later phase)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.clients.transcript_parser_client import TranscriptParserClientError, parse_transcript_pdf
from app.config import get_settings
from app.db.mongo import get_database
from app.dependencies.auth import AuthContext, require_auth
from app.middleware.auth_rate_limiter import enforce_transcript_import_rate_limit
from app.schemas.transcript_import import (
    CommitTranscriptImportRequest,
    CommitTranscriptImportResponse,
    ParseTranscriptPreviewResponse,
)
from app.services.transcript_import_service import commit_transcript_import

router = APIRouter(prefix="/transcript-import", tags=["transcript-import"])

PDF_CONTENT_TYPES = frozenset({"application/pdf", "application/x-pdf"})


def success_response(data: dict) -> dict:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def validate_upload(content: bytes, *, content_type: str | None, max_bytes: int) -> None:
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"PDF exceeds maximum upload size of {max_bytes} bytes",
        )
    if content_type and content_type not in PDF_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")


@router.post("/parse")
async def parse_transcript_upload(
    request: Request,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Parse an official transcript PDF and return a preview without persisting records."""
    await enforce_transcript_import_rate_limit(request, auth.user_id)
    settings = get_settings()
    content = await file.read()
    validate_upload(
        content,
        content_type=file.content_type,
        max_bytes=settings.transcript_import_max_upload_bytes,
    )

    try:
        parse_result = await parse_transcript_pdf(
            content,
            filename=file.filename or "transcript.pdf",
        )
    except TranscriptParserClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    preview = ParseTranscriptPreviewResponse.model_validate(parse_result)
    return success_response({"parsePreview": preview.model_dump()})


@router.post("/commit")
async def commit_transcript_import_records(
    request: Request,
    payload: CommitTranscriptImportRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Persist selected parsed transcript rows as imported completed courses."""
    await enforce_transcript_import_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await commit_transcript_import(database, auth.user_id, payload)
    response = CommitTranscriptImportResponse.model_validate(result)
    return success_response({"importResult": response.model_dump()})
