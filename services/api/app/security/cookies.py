from datetime import timedelta

from fastapi import Response

from app.config import get_settings
from app.security.jwt import parse_expires_in

ACCESS_TOKEN_COOKIE = "unipilot_access_token"
REFRESH_TOKEN_COOKIE = "unipilot_refresh_token"
REFRESH_TOKEN_PATH = "/auth"
REFRESH_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _cookie_secure() -> bool:
    settings = get_settings()
    return settings.environment == "production"


def access_token_max_age_seconds() -> int:
    settings = get_settings()
    return int(parse_expires_in(settings.jwt_expires_in).total_seconds())


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    secure = _cookie_secure()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=access_token_max_age_seconds(),
        path="/",
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=REFRESH_TOKEN_MAX_AGE_SECONDS,
        path=REFRESH_TOKEN_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    secure = _cookie_secure()
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )
