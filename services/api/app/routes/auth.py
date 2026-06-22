from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_auth_rate_limits
from app.repositories.user_repository import (
    create_user,
    ensure_user_indexes,
    find_user_by_email,
    find_user_by_id,
    to_public_user,
)
from app.schemas.auth import LoginRequest, RegisterRequest
from app.security.cookies import (
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.security.jwt import create_access_token
from app.security.password import hash_password, verify_password
from app.security.refresh_tokens import issue_refresh_token, revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])

_user_indexes_ready = False

REGISTRATION_FAILED_MESSAGE = (
    "Registration could not be completed. Try signing in or use a different email."
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


async def _build_auth_payload(*, user: dict[str, Any]) -> dict[str, Any]:
    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )
    refresh_token = await issue_refresh_token(user_id=str(user["_id"]))
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
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
    )
    return response


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

    auth_payload = await _build_auth_payload(user=user)
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

    if not verify_password(payload.password, user["passwordHash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    auth_payload = await _build_auth_payload(user=user)
    return _json_auth_response(auth_payload, status_code=200)


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

    user_id, new_refresh_token = rotation
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
