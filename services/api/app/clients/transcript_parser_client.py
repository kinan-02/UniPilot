"""HTTP client for the internal transcript-parser service."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class TranscriptParserClientError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def parse_transcript_pdf(
    content: bytes,
    *,
    filename: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    url = f"{settings.resolved_transcript_parser_url()}/parse"
    headers: dict[str, str] = {}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(settings.transcript_parser_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers=headers,
            files={"file": (filename, content, "application/pdf")},
        )

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") if isinstance(payload, dict) else None
        if not detail:
            detail = "Transcript parser request failed"
        raise TranscriptParserClientError(status_code=response.status_code, detail=str(detail))

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise TranscriptParserClientError(
            status_code=502,
            detail="Transcript parser returned an invalid response",
        )

    data = payload.get("data")
    if not isinstance(data, dict) or "parseResult" not in data:
        raise TranscriptParserClientError(
            status_code=502,
            detail="Transcript parser response missing parseResult",
        )

    return data["parseResult"]
