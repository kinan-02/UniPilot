"""Validate student profile degree references against production catalog."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.track_registry import (
    program_code_for_track_slug,
    resolve_track_slug_from_program,
)
from app.repositories import catalog_repository


async def validate_degree_id_for_profile(
    database: AsyncIOMotorDatabase,
    degree_id: str | None,
) -> None:
    if degree_id is None:
        return

    program = await catalog_repository.find_degree_program_by_id(database, degree_id)
    if not program:
        raise HTTPException(
            status_code=400,
            detail="Referenced degree program was not found in the catalog",
        )


async def validate_academic_path_for_profile(
    database: AsyncIOMotorDatabase,
    degree_id: str | None,
    academic_path: dict[str, Any] | None,
) -> None:
    if not academic_path:
        return

    track_slug = academic_path.get("trackSlug")
    if not track_slug:
        return

    expected_program_code = program_code_for_track_slug(track_slug)
    if expected_program_code is None:
        raise HTTPException(
            status_code=400,
            detail="Unknown DDS track slug",
        )

    if degree_id is None:
        raise HTTPException(
            status_code=400,
            detail="A degree must be selected before setting an academic track",
        )

    program = await catalog_repository.find_degree_program_by_id(database, degree_id)
    if not program:
        raise HTTPException(
            status_code=400,
            detail="Referenced degree program was not found in the catalog",
        )

    program_code = program.get("programCode")
    resolved_slug = resolve_track_slug_from_program(program)
    if program_code != expected_program_code and resolved_slug != track_slug:
        raise HTTPException(
            status_code=400,
            detail="Selected track does not match the chosen degree program",
        )
