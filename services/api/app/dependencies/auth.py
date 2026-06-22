from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.cookies import ACCESS_TOKEN_COOKIE
from app.security.jwt import verify_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    return credentials.credentials


def resolve_access_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    access_token_cookie: str | None,
) -> str | None:
    bearer_token = get_bearer_token(credentials)
    if bearer_token:
        return bearer_token

    if access_token_cookie:
        return access_token_cookie

    return request.cookies.get(ACCESS_TOKEN_COOKIE)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> AuthContext:
    token = resolve_access_token(request, credentials, access_token_cookie)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is required",
        )

    try:
        payload = verify_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is invalid or expired",
        ) from None

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is invalid or expired",
        )

    return AuthContext(user_id=str(user_id), email=str(email))
