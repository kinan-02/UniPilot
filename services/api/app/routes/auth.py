from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_auth_rate_limits
from app.repositories.user_repository import (
    create_google_user,
    create_user,
    ensure_user_indexes,
    find_user_by_email,
    find_user_by_google_id,
    find_user_by_id,
    to_public_user,
)
from app.schemas.auth import AuthProvidersResponse, LoginRequest, RegisterRequest
from app.security.cookies import (
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.security.google_oauth import (
    GoogleOAuthError,
    GoogleUserInfo,
    build_google_authorization_url,
    exchange_code_for_id_token,
    verify_google_id_token,
)
from app.security.jwt import create_access_token
from app.security.oauth_state import consume_oauth_state, issue_oauth_state
from app.security.password import hash_password, verify_password
from app.security.refresh_tokens import issue_refresh_token, revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])

_user_indexes_ready = False

REGISTRATION_FAILED_MESSAGE = (
    "Registration could not be completed. Try signing in or use a different email."
)
GOOGLE_ACCOUNT_EXISTS_MESSAGE = (
    "An account with this email already exists. Sign in with your password, "
    "or use Google if you originally registered with Google."
)
GOOGLE_EMAIL_NOT_VERIFIED_MESSAGE = (
    "Google did not return a verified email address for this account."
)
GOOGLE_SIGN_IN_REQUIRED_MESSAGE = (
    "This account uses Google sign-in. Please continue with Google."
)


async def _ensure_user_indexes_once() -> None:
    global _user_indexes_ready

    if _user_indexes_ready:
        return

    database = await get_database()
    await ensure_user_indexes(database)
    _user_indexes_ready = True


def reset_user_indexes_state() -> None:
    global _user_indexes_ready
    _user_indexes_ready = False


def success_response(data: Any, *, status_code: int = 200) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


async def _build_auth_payload(
    *,
    user: dict[str, Any],
    remember_me: bool = False,
) -> dict[str, Any]:
    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )
    refresh_token = await issue_refresh_token(
        user_id=str(user["_id"]),
        remember_me=remember_me,
    )
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "rememberMe": remember_me,
        "user": to_public_user(user),
    }


def _json_auth_response(
    payload: dict[str, Any],
    *,
    status_code: int,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=success_response(
            {
                "accessToken": payload["accessToken"],
                "user": payload["user"],
            },
            status_code=status_code,
        ),
    )
    set_auth_cookies(
        response,
        access_token=payload["accessToken"],
        refresh_token=payload["refreshToken"],
        remember_me=bool(payload.get("rememberMe")),
    )
    return response


def _oauth_error_redirect(*, error_code: str) -> RedirectResponse:
    settings = get_settings()
    query = urlencode({"error": error_code})
    return RedirectResponse(
        url=f"{settings.resolved_web_app_url()}/login?{query}",
        status_code=302,
    )


def _oauth_success_redirect() -> RedirectResponse:
    settings = get_settings()
    return RedirectResponse(
        url=f"{settings.resolved_web_app_url()}/auth/callback",
        status_code=302,
    )


async def _resolve_google_user_from_callback(code: str, *, settings) -> GoogleUserInfo:
    if settings.e2e_google_oauth_stub_enabled() and code.startswith("e2e|"):
        parts = code.split("|", 2)
        if len(parts) != 3:
            raise GoogleOAuthError("E2E Google stub code is invalid")
        _, email, google_id = parts
        normalized_email = email.strip().lower()
        normalized_google_id = google_id.strip()
        if not normalized_email or not normalized_google_id:
            raise GoogleOAuthError("E2E Google stub code is invalid")
        return GoogleUserInfo(
            google_id=normalized_google_id,
            email=normalized_email,
            email_verified=True,
        )

    id_token = await exchange_code_for_id_token(code, settings=settings)
    return verify_google_id_token(id_token, settings=settings)


@router.get("/providers")
async def get_auth_providers() -> dict[str, Any]:
    settings = get_settings()
    providers = AuthProvidersResponse(
        google=settings.google_oauth_enabled(),
        googleE2eStub=settings.e2e_google_oauth_stub_enabled(),
    )
    return success_response(providers.model_dump())


@router.post("/register", status_code=201)
async def register_user(
    payload: RegisterRequest,
    request: Request,
) -> JSONResponse:
    await enforce_auth_rate_limits(request, email=payload.email)
    await _ensure_user_indexes_once()
    database = await get_database()

    existing_user = await find_user_by_email(database, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail=REGISTRATION_FAILED_MESSAGE,
        )

    password_hash = hash_password(payload.password)

    try:
        user = await create_user(
            database,
            email=payload.email,
            password_hash=password_hash,
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail=REGISTRATION_FAILED_MESSAGE,
        ) from None

    auth_payload = await _build_auth_payload(user=user, remember_me=True)
    return _json_auth_response(auth_payload, status_code=201)


@router.post("/login")
async def login_user(
    payload: LoginRequest,
    request: Request,
) -> JSONResponse:
    await enforce_auth_rate_limits(request, email=payload.email)
    database = await get_database()
    user = await find_user_by_email(database, payload.email)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    password_hash = user.get("passwordHash")
    if not password_hash:
        raise HTTPException(
            status_code=401,
            detail=GOOGLE_SIGN_IN_REQUIRED_MESSAGE,
        )

    if not verify_password(payload.password, password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    auth_payload = await _build_auth_payload(user=user, remember_me=payload.rememberMe)
    return _json_auth_response(auth_payload, status_code=200)


@router.get("/google")
async def start_google_oauth(
    request: Request,
    remember_me: bool = Query(default=False, alias="rememberMe"),
) -> RedirectResponse:
    await enforce_auth_rate_limits(request)
    settings = get_settings()
    if not settings.google_oauth_enabled():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    state = await issue_oauth_state(remember_me=remember_me)
    authorization_url = build_google_authorization_url(state=state, settings=settings)
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/google/callback")
async def complete_google_oauth(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    await enforce_auth_rate_limits(request)
    settings = get_settings()
    if not settings.google_oauth_enabled():
        return _oauth_error_redirect(error_code="google_not_configured")

    if error:
        return _oauth_error_redirect(error_code="google_denied")

    if not code or not state:
        return _oauth_error_redirect(error_code="google_invalid_callback")

    remember_me = await consume_oauth_state(state)
    if remember_me is None:
        return _oauth_error_redirect(error_code="google_invalid_state")

    try:
        google_user = await _resolve_google_user_from_callback(code, settings=settings)
    except GoogleOAuthError:
        return _oauth_error_redirect(error_code="google_auth_failed")

    if not google_user.email_verified:
        return _oauth_error_redirect(error_code="google_email_unverified")

    await _ensure_user_indexes_once()
    database = await get_database()

    user = await find_user_by_google_id(database, google_user.google_id)
    if user is None:
        existing_by_email = await find_user_by_email(database, google_user.email)
        if existing_by_email:
            return _oauth_error_redirect(error_code="google_account_exists")

        try:
            user = await create_google_user(
                database,
                email=google_user.email,
                google_id=google_user.google_id,
            )
        except DuplicateKeyError:
            user = await find_user_by_google_id(database, google_user.google_id)
            if user is None:
                return _oauth_error_redirect(error_code="google_account_exists")

    auth_payload = await _build_auth_payload(user=user, remember_me=remember_me)
    response = _oauth_success_redirect()
    set_auth_cookies(
        response,
        access_token=auth_payload["accessToken"],
        refresh_token=auth_payload["refreshToken"],
        remember_me=remember_me,
    )
    return response


@router.post("/refresh")
async def refresh_session(
    request: Request,
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_TOKEN_COOKIE),
) -> JSONResponse:
    await enforce_auth_rate_limits(request)
    refresh_token = refresh_token_cookie or request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    rotation = await rotate_refresh_token(refresh_token)
    if rotation is None:
        response = JSONResponse(
            status_code=401,
            content={
                "success": False,
                "data": None,
                "error": "Refresh token is invalid or expired",
            },
        )
        clear_auth_cookies(response)
        return response

    user_id, new_refresh_token, remember_me = rotation
    database = await get_database()
    user = await find_user_by_id(database, user_id)
    if not user:
        response = JSONResponse(
            status_code=401,
            content={
                "success": False,
                "data": None,
                "error": "Refresh token is invalid or expired",
            },
        )
        clear_auth_cookies(response)
        return response

    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )
    response = JSONResponse(
        content=success_response(
            {
                "accessToken": access_token,
                "user": to_public_user(user),
            }
        )
    )
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=new_refresh_token,
        remember_me=remember_me,
    )
    return response


@router.post("/logout")
async def logout_user(request: Request) -> JSONResponse:
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token:
        await revoke_refresh_token(refresh_token)

    response = JSONResponse(content=success_response({"loggedOut": True}))
    clear_auth_cookies(response)
    return response


@router.get("/me")
async def get_current_user(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    database = await get_database()
    user = await find_user_by_id(database, auth.user_id)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication token is invalid or expired",
        )

    return success_response({"user": to_public_user(user)})
