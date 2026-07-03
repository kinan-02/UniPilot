"""Resolve catalog degree programs from student profiles."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.track_registry import program_code_for_track_slug
from app.repositories import catalog_repository


async def resolve_degree_program_for_profile(
    database: AsyncIOMotorDatabase,
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve degree program by profile id, with program-code fallback after catalog promotion."""
    degree_id = profile.get("degreeId")
    if degree_id:
        degree_program = await catalog_repository.find_degree_program_by_id(
            database,
            str(degree_id),
        )
        if degree_program is not None:
            return degree_program

    academic_path = profile.get("academicPath") or {}
    track_slug = academic_path.get("trackSlug")
    program_code = program_code_for_track_slug(str(track_slug)) if track_slug else None
    if not program_code:
        return None
    return await catalog_repository.find_degree_program_by_code(database, program_code)
