from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import get_settings
from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_auth_rate_limits
from app.repositories.outlook_token_repository import (
    delete_outlook_tokens,
    ensure_outlook_token_indexes,
    find_outlook_tokens_by_user_id,
    to_public_outlook_status,
    upsert_outlook_tokens,
)
from app.security.microsoft_oauth import (
    MicrosoftOAuthError,
    build_microsoft_authorization_url,
    exchange_code_for_tokens,
    fetch_microsoft_user_profile,
    generate_pkce_pair,
)
from app.security.outlook_oauth_state import (
    consume_outlook_oauth_state,
    issue_outlook_oauth_state,
)

router = APIRouter(prefix="/integrations/outlook", tags=["outlook-integration"])

_indexes_ready = False


async def _ensure_indexes_once() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    database = await get_database()
    await ensure_outlook_token_indexes(database)
    _indexes_ready = True


def reset_outlook_integration_indexes_state() -> None:
    global _indexes_ready
    _indexes_ready = False


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _oauth_error_redirect(*, error_code: str) -> RedirectResponse:
    settings = get_settings()
    params = urlencode({"outlook": "error", "code": error_code})
    return RedirectResponse(
        url=f"{settings.resolved_web_app_url()}/settings/integrations?{params}",
        status_code=302,
    )


def _oauth_success_redirect() -> RedirectResponse:
    settings = get_settings()
    params = urlencode({"outlook": "connected"})
    return RedirectResponse(
        url=f"{settings.resolved_web_app_url()}/settings/integrations?{params}",
        status_code=302,
    )


@router.get("/status")
async def outlook_connection_status(
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    settings = get_settings()
    await _ensure_indexes_once()
    database = await get_database()
    token_document = await find_outlook_tokens_by_user_id(database, auth.user_id)
    status = to_public_outlook_status(token_document)
    status["available"] = settings.microsoft_oauth_enabled()
    return _success(status)


@router.get("/connect")
async def connect_outlook(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> RedirectResponse:
    await enforce_auth_rate_limits(request)
    settings = get_settings()
    if not settings.microsoft_oauth_enabled():
        raise HTTPException(status_code=503, detail="Outlook integration is not configured")

    code_verifier, code_challenge = generate_pkce_pair()
    state = await issue_outlook_oauth_state(
        user_id=auth.user_id,
        code_verifier=code_verifier,
    )
    authorization_url = build_microsoft_authorization_url(
        state=state,
        code_challenge=code_challenge,
        settings=settings,
    )
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/callback")
async def outlook_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    await enforce_auth_rate_limits(request)
    settings = get_settings()
    if not settings.microsoft_oauth_enabled():
        return _oauth_error_redirect(error_code="outlook_not_configured")

    if error:
        return _oauth_error_redirect(error_code="outlook_denied")

    if not code or not state:
        return _oauth_error_redirect(error_code="outlook_invalid_callback")

    consumed = await consume_outlook_oauth_state(state)
    if consumed is None:
        return _oauth_error_redirect(error_code="outlook_invalid_state")

    user_id, code_verifier = consumed

    try:
        token_response = await exchange_code_for_tokens(
            code=code,
            code_verifier=code_verifier,
            settings=settings,
        )
        if not token_response.refresh_token:
            return _oauth_error_redirect(error_code="outlook_missing_refresh_token")

        profile = await fetch_microsoft_user_profile(token_response.access_token)
    except MicrosoftOAuthError:
        return _oauth_error_redirect(error_code="outlook_auth_failed")

    await _ensure_indexes_once()
    database = await get_database()
    await upsert_outlook_tokens(
        database,
        user_id=user_id,
        microsoft_user_id=profile.microsoft_user_id,
        email=profile.email,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        access_token_expires_at=token_response.expires_at,
        scopes=settings.resolved_microsoft_scopes(),
    )
    return _oauth_success_redirect()


@router.delete("/disconnect")
async def disconnect_outlook(
    auth: AuthContext = Depends(require_auth),
) -> JSONResponse:
    await _ensure_indexes_once()
    database = await get_database()
    deleted = await delete_outlook_tokens(database, auth.user_id)
    return JSONResponse(status_code=200, content=_success({"disconnected": deleted}))
