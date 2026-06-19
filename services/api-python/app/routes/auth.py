from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_auth_rate_limit
from app.repositories.user_repository import (
    create_user,
    ensure_user_indexes,
    find_user_by_email,
    find_user_by_id,
    to_public_user,
)
from app.schemas.auth import LoginRequest, RegisterRequest
from app.security.jwt import create_access_token
from app.security.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_user_indexes_ready = False


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


@router.post("/register", status_code=201)
async def register_user(
    payload: RegisterRequest,
    _: None = Depends(enforce_auth_rate_limit),
) -> dict[str, Any]:
    await _ensure_user_indexes_once()
    database = await get_database()

    existing_user = await find_user_by_email(database, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists",
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
            detail="A user with this email already exists",
        ) from None

    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )

    return success_response(
        {
            "accessToken": access_token,
            "user": to_public_user(user),
        },
        status_code=201,
    )


@router.post("/login")
async def login_user(
    payload: LoginRequest,
    _: None = Depends(enforce_auth_rate_limit),
) -> dict[str, Any]:
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

    access_token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )

    return success_response(
        {
            "accessToken": access_token,
            "user": to_public_user(user),
        }
    )


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
