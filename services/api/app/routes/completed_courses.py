"""User-owned completed courses routes (Phase 14)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import (
    create_completed_course,
    delete_completed_course_by_id_and_user_id,
    ensure_completed_course_indexes,
    find_completed_course_by_id_and_user_id,
    find_completed_courses_by_user_id,
    to_public_completed_course,
    update_completed_course_by_id_and_user_id,
)
from app.schemas.completed_course import (
    OBJECT_ID_PATTERN,
    CreateCompletedCourseRequest,
    UpdateCompletedCourseRequest,
)

router = APIRouter(prefix="/completed-courses", tags=["completed-courses"])

_completed_course_indexes_ready = False

LIST_QUERY_ALLOWED = frozenset({"page", "limit"})


def reset_completed_course_indexes_state() -> None:
    global _completed_course_indexes_ready
    _completed_course_indexes_ready = False


async def _ensure_completed_course_indexes_once() -> None:
    global _completed_course_indexes_ready

    if _completed_course_indexes_ready:
        return

    database = await get_database()
    await ensure_completed_course_indexes(database)
    _completed_course_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def validate_record_id_param(record_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(record_id):
        raise HTTPException(status_code=400, detail="Identifier must be a valid ObjectId")
    return record_id


def reject_unknown_list_query_params(request: Request) -> None:
    unknown = set(request.query_params.keys()) - LIST_QUERY_ALLOWED
    if unknown:
        raise HTTPException(status_code=400, detail="Unknown query parameters are not allowed")


def create_payload_from_request(payload: CreateCompletedCourseRequest) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if payload.metadata is not None:
        data["metadata"] = payload.metadata.model_dump(exclude_none=True)
    data["source"] = "manual"
    return data


def update_payload_from_request(payload: UpdateCompletedCourseRequest) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if payload.metadata is not None:
        data["metadata"] = payload.metadata.model_dump(exclude_none=True)
    return data


async def resolve_course_summary(database, course_id: str) -> dict[str, str] | None:
    course = await catalog_repository.find_course_by_id(database, course_id)
    return catalog_repository.course_summary_from_document(course)


@router.post("", status_code=201)
async def create_completed_course_record(
    payload: CreateCompletedCourseRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_completed_course_indexes_once()
    database = await get_database()

    course = await catalog_repository.find_course_by_id(database, payload.courseId)
    if not course:
        raise HTTPException(
            status_code=400,
            detail="Referenced course was not found in the catalog",
        )

    try:
        record = await create_completed_course(
            database,
            auth.user_id,
            create_payload_from_request(payload),
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="A completed course record already exists for this course and attempt",
        ) from None

    course_summary = catalog_repository.course_summary_from_document(course)
    return success_response(
        {
            "completedCourse": to_public_completed_course(record, course_summary),
        }
    )


@router.get("")
async def list_completed_course_records(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    reject_unknown_list_query_params(request)
    database = await get_database()
    list_result = await find_completed_courses_by_user_id(
        database,
        auth.user_id,
        page=page,
        limit=limit,
    )

    completed_courses: list[dict[str, Any]] = []
    for record in list_result["records"]:
        course_summary = await resolve_course_summary(database, str(record["courseId"]))
        public_record = to_public_completed_course(record, course_summary)
        if public_record:
            completed_courses.append(public_record)

    return success_response(
        {
            "completedCourses": completed_courses,
            "pagination": {
                "total": list_result["total"],
                "page": list_result["page"],
                "limit": list_result["limit"],
            },
        }
    )


@router.get("/{record_id}")
async def get_completed_course_record(
    record_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_record_id_param(record_id)
    database = await get_database()
    record = await find_completed_course_by_id_and_user_id(database, record_id, auth.user_id)

    if not record:
        raise HTTPException(status_code=404, detail="Completed course record not found")

    course_summary = await resolve_course_summary(database, str(record["courseId"]))
    return success_response(
        {
            "completedCourse": to_public_completed_course(record, course_summary),
        }
    )


@router.put("/{record_id}")
async def update_completed_course_record(
    record_id: str,
    payload: UpdateCompletedCourseRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_record_id_param(record_id)
    database = await get_database()
    update_result = await update_completed_course_by_id_and_user_id(
        database,
        record_id,
        auth.user_id,
        update_payload_from_request(payload),
    )

    if update_result["status"] == "not_found" or not update_result.get("record"):
        raise HTTPException(status_code=404, detail="Completed course record not found")

    if update_result["status"] == "not_editable":
        raise HTTPException(
            status_code=403,
            detail="Only manual completed course records can be updated",
        )

    record = update_result["record"]
    course_summary = await resolve_course_summary(database, str(record["courseId"]))
    return success_response(
        {
            "completedCourse": to_public_completed_course(record, course_summary),
        }
    )


@router.delete("/{record_id}")
async def delete_completed_course_record(
    record_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    validate_record_id_param(record_id)
    database = await get_database()
    delete_result = await delete_completed_course_by_id_and_user_id(
        database,
        record_id,
        auth.user_id,
    )

    if delete_result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Completed course record not found")

    if delete_result["status"] == "not_editable":
        raise HTTPException(
            status_code=403,
            detail="Only manual completed course records can be deleted",
        )

    return success_response({"deleted": True})
