from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.repositories.student_profile_repository import (
    create_student_profile,
    delete_student_profile_by_user_id,
    ensure_student_profile_indexes,
    find_student_profile_by_user_id,
    to_public_student_profile,
    update_student_profile_by_user_id,
)
from app.services.student_profile_validation import (
    validate_academic_path_for_profile,
    validate_degree_id_for_profile,
)
from app.schemas.student_profile import (
    CreateStudentProfileRequest,
    UpdateStudentProfileRequest,
)

router = APIRouter(prefix="/student-profile", tags=["student-profile"])

_student_profile_indexes_ready = False


async def _ensure_student_profile_indexes_once() -> None:
    global _student_profile_indexes_ready

    if _student_profile_indexes_ready:
        return

    database = await get_database()
    await ensure_student_profile_indexes(database)
    _student_profile_indexes_ready = True


def reset_student_profile_indexes_state() -> None:
    global _student_profile_indexes_ready
    _student_profile_indexes_ready = False


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def profile_payload_from_create_request(payload: CreateStudentProfileRequest) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if payload.preferences is not None:
        data["preferences"] = payload.preferences.model_dump(exclude_none=True)
    if payload.academicPath is not None:
        data["academicPath"] = payload.academicPath.model_dump(exclude_none=True)
    return data


def profile_payload_from_update_request(payload: UpdateStudentProfileRequest) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if payload.preferences is not None:
        data["preferences"] = payload.preferences.model_dump(exclude_none=True)
    if payload.academicPath is not None:
        data["academicPath"] = payload.academicPath.model_dump(exclude_none=True)
    return data


@router.post("", status_code=201)
async def create_profile(
    payload: CreateStudentProfileRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_student_profile_indexes_once()
    database = await get_database()

    existing_profile = await find_student_profile_by_user_id(database, auth.user_id)
    if existing_profile:
        raise HTTPException(
            status_code=409,
            detail="Student profile already exists for this user",
        )

    await validate_degree_id_for_profile(database, payload.degreeId)
    if payload.academicPath is not None:
        await validate_academic_path_for_profile(
            database,
            payload.degreeId,
            payload.academicPath.model_dump(exclude_none=True),
        )

    try:
        profile = await create_student_profile(
            database,
            auth.user_id,
            profile_payload_from_create_request(payload),
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Student profile already exists for this user",
        ) from None

    return success_response({"profile": to_public_student_profile(profile)})


@router.get("")
async def get_profile(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    database = await get_database()
    profile = await find_student_profile_by_user_id(database, auth.user_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    return success_response({"profile": to_public_student_profile(profile)})


@router.put("")
async def update_profile(
    payload: UpdateStudentProfileRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    existing_profile = await find_student_profile_by_user_id(database, auth.user_id)

    if not existing_profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    degree_id = payload.degreeId if payload.degreeId is not None else (
        str(existing_profile["degreeId"]) if existing_profile.get("degreeId") else None
    )
    if payload.degreeId is not None:
        await validate_degree_id_for_profile(database, payload.degreeId)
    if payload.academicPath is not None:
        await validate_academic_path_for_profile(
            database,
            degree_id,
            payload.academicPath.model_dump(exclude_none=True),
        )

    updated_profile = await update_student_profile_by_user_id(
        database,
        auth.user_id,
        profile_payload_from_update_request(payload),
    )

    if not updated_profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    from app.services.watchdog_enqueue import maybe_enqueue_watchdog_scan

    await maybe_enqueue_watchdog_scan(database, auth.user_id, "profile_change")

    return success_response({"profile": to_public_student_profile(updated_profile)})


@router.delete("")
async def delete_profile(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    database = await get_database()
    deleted_count = await delete_student_profile_by_user_id(database, auth.user_id)

    if not deleted_count:
        raise HTTPException(status_code=404, detail="Student profile not found")

    return success_response({"deleted": True})
