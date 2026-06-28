"""Transcript PDF parse routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.core.responses import success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.services.pdf_intake import is_pdf_bytes, validate_upload_size
from app.services.pdf_pipeline import parse_technion_transcript_pdf

router = APIRouter(prefix="/parse", tags=["parse"])


@router.post("")
async def parse_transcript_pdf(
    file: UploadFile = File(...),
    _: None = Depends(require_internal_service_token),
) -> dict:
    settings = get_settings()
    content = await file.read()

    try:
        validate_upload_size(content, max_bytes=settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not is_pdf_bytes(content):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    try:
        result = parse_technion_transcript_pdf(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Unable to parse transcript PDF") from exc

    return success_response({"parseResult": result.model_dump()})
