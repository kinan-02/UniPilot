from fastapi import Response

from app.config import get_settings
from app.security.jwt import parse_expires_in
from app.security.refresh_tokens import refresh_token_ttl_seconds

ACCESS_TOKEN_COOKIE = "unipilot_access_token"
REFRESH_TOKEN_COOKIE = "unipilot_refresh_token"
REFRESH_TOKEN_PATH = "/auth"


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
    remember_me: bool = False,
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
    refresh_cookie_kwargs: dict[str, object] = {
        "key": REFRESH_TOKEN_COOKIE,
        "value": refresh_token,
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
        "path": REFRESH_TOKEN_PATH,
    }
    if remember_me:
        refresh_cookie_kwargs["max_age"] = refresh_token_ttl_seconds(remember_me=True)
    response.set_cookie(**refresh_cookie_kwargs)  # type: ignore[arg-type]


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
