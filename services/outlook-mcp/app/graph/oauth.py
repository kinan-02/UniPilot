"""Microsoft OAuth 2.0 authorization-code flow with PKCE."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings, get_settings
from app.graph.errors import OutlookIntegrationError, OutlookNetworkError


class MicrosoftOAuthError(OutlookIntegrationError):
    code = "microsoft_oauth_error"


@dataclass(frozen=True)
class MicrosoftTokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str
    token_type: str

    @property
    def expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=max(0, self.expires_in - 60))


@dataclass(frozen=True)
class MicrosoftUserProfile:
    microsoft_user_id: str
    email: str
    display_name: str | None


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")
    return verifier, challenge


def _authority_base(settings: Settings) -> str:
    tenant = settings.microsoft_tenant_id.strip() or "common"
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


def build_microsoft_authorization_url(
    *,
    state: str,
    code_challenge: str,
    settings: Settings | None = None,
    redirect_uri: str | None = None,
) -> str:
    resolved = settings or get_settings()
    client_id = (resolved.microsoft_client_id or "").strip()
    if not client_id:
        raise MicrosoftOAuthError("Microsoft OAuth is not configured")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri or (resolved.microsoft_redirect_uri or "").strip(),
        "response_mode": "query",
        "scope": " ".join(resolved.resolved_microsoft_scopes()),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
    }
    if not params["redirect_uri"]:
        raise MicrosoftOAuthError("Microsoft redirect URI is not configured")

    return f"{_authority_base(resolved)}/authorize?{urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    settings: Settings | None = None,
) -> MicrosoftTokenResponse:
    resolved = settings or get_settings()
    client_id = (resolved.microsoft_client_id or "").strip()
    if not client_id:
        raise MicrosoftOAuthError("Microsoft OAuth is not configured")

    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_authority_base(resolved)}/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise OutlookNetworkError() from exc

    if response.status_code != 200:
        raise MicrosoftOAuthError("Microsoft token exchange failed")

    body = response.json()
    access_token = body.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise MicrosoftOAuthError("Microsoft token response missing access_token")

    refresh_token = body.get("refresh_token")
    expires_in = int(body.get("expires_in", 3600))
    scope = str(body.get("scope", ""))
    token_type = str(body.get("token_type", "Bearer"))

    return MicrosoftTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        expires_in=expires_in,
        scope=scope,
        token_type=token_type,
    )


async def refresh_access_token(
    *,
    refresh_token: str,
    settings: Settings | None = None,
) -> MicrosoftTokenResponse:
    resolved = settings or get_settings()
    client_id = (resolved.microsoft_client_id or "").strip()
    if not client_id:
        raise MicrosoftOAuthError("Microsoft OAuth is not configured")

    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(resolved.resolved_microsoft_scopes()),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_authority_base(resolved)}/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise OutlookNetworkError() from exc

    if response.status_code != 200:
        error_body: dict[str, Any] = {}
        try:
            error_body = response.json()
        except Exception:
            pass
        error_code = str(error_body.get("error", ""))
        if error_code in {"invalid_grant", "interaction_required", "consent_required"}:
            from app.graph.errors import OutlookConsentRequiredError

            raise OutlookConsentRequiredError()
        raise MicrosoftOAuthError("Microsoft token refresh failed")

    body = response.json()
    access_token = body.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise MicrosoftOAuthError("Microsoft refresh response missing access_token")

    new_refresh = body.get("refresh_token")
    expires_in = int(body.get("expires_in", 3600))
    scope = str(body.get("scope", ""))
    token_type = str(body.get("token_type", "Bearer"))

    return MicrosoftTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh if isinstance(new_refresh, str) else refresh_token,
        expires_in=expires_in,
        scope=scope,
        token_type=token_type,
    )


async def fetch_microsoft_user_profile(
    access_token: str,
    *,
    settings: Settings | None = None,
) -> MicrosoftUserProfile:
    _ = settings
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                params={"$select": "id,mail,userPrincipalName,displayName"},
            )
    except httpx.HTTPError as exc:
        raise OutlookNetworkError() from exc

    if response.status_code != 200:
        raise MicrosoftOAuthError("Failed to fetch Microsoft user profile")

    body = response.json()
    microsoft_user_id = str(body.get("id", "")).strip()
    email = str(body.get("mail") or body.get("userPrincipalName") or "").strip().lower()
    if not microsoft_user_id or not email:
        raise MicrosoftOAuthError("Microsoft profile missing id or email")

    display_name = body.get("displayName")
    return MicrosoftUserProfile(
        microsoft_user_id=microsoft_user_id,
        email=email,
        display_name=str(display_name) if display_name else None,
    )
