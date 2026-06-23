"""Google OAuth 2.0 authorization-code helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.config import Settings, get_settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


class GoogleOAuthError(Exception):
    pass


@dataclass(frozen=True)
class GoogleUserInfo:
    google_id: str
    email: str
    email_verified: bool


def build_google_authorization_url(*, state: str, settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    client_id = (resolved.google_oauth_client_id or "").strip()
    if not client_id:
        raise GoogleOAuthError("Google OAuth is not configured")

    params = {
        "client_id": client_id,
        "redirect_uri": resolved.resolved_google_oauth_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_id_token(
    code: str,
    *,
    settings: Settings | None = None,
) -> str:
    resolved = settings or get_settings()
    client_id = (resolved.google_oauth_client_id or "").strip()
    client_secret = (resolved.google_oauth_client_secret or "").strip()
    if not client_id or not client_secret:
        raise GoogleOAuthError("Google OAuth is not configured")

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": resolved.resolved_google_oauth_redirect_uri(),
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)
        if response.status_code != 200:
            raise GoogleOAuthError("Google token exchange failed")

        body = response.json()
        id_token = body.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise GoogleOAuthError("Google token response missing id_token")
        return id_token


def verify_google_id_token(id_token: str, *, settings: Settings | None = None) -> GoogleUserInfo:
    resolved = settings or get_settings()
    client_id = (resolved.google_oauth_client_id or "").strip()
    if not client_id:
        raise GoogleOAuthError("Google OAuth is not configured")

    jwk_client = PyJWKClient(GOOGLE_JWKS_URL)
    signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    claims: dict[str, Any] = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        options={"require": ["exp", "iss", "sub", "email"]},
    )

    issuer = claims.get("iss")
    if issuer not in GOOGLE_ISSUERS:
        raise GoogleOAuthError("Google token issuer is invalid")

    email = str(claims.get("email", "")).strip().lower()
    if not email:
        raise GoogleOAuthError("Google account email is missing")

    return GoogleUserInfo(
        google_id=str(claims["sub"]),
        email=email,
        email_verified=bool(claims.get("email_verified")),
    )
