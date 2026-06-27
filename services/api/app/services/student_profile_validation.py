"""Validate student profile degree references against production catalog."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.track_registry import resolve_track_slug_from_program
from app.repositories import catalog_repository


async def validate_degree_id_for_profile(
    database: AsyncIOMotorDatabase,
    degree_id: str | None,
) -> None:
    if degree_id is None:
        return

    program = await catalog_repository.find_degree_program_by_id(database, degree_id)
    if program:
        return

    path_option = await catalog_repository.find_path_option_by_id(database, degree_id)
    if path_option and path_option.get("selectableAsPrimary"):
        return

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

    if degree_id is None:
        raise HTTPException(
            status_code=400,
            detail="A degree must be selected before setting an academic track",
        )

    program = await catalog_repository.find_degree_program_by_id(database, degree_id)
    if not program:
        path_option = await catalog_repository.find_path_option_by_id(database, degree_id)
        if path_option and path_option.get("selectableAsPrimary"):
            linked_degree_id = path_option.get("linkedDegreeProgramId")
            if linked_degree_id:
                program = await catalog_repository.find_degree_program_by_id(
                    database,
                    str(linked_degree_id),
                )
            else:
                return
        if not program:
            raise HTTPException(
                status_code=400,
                detail="Referenced degree program was not found in the catalog",
            )

    resolved_slug = resolve_track_slug_from_program(program)
    if resolved_slug is None:
        raise HTTPException(
            status_code=400,
            detail="Unknown track slug for the selected degree program",
        )
    if resolved_slug != track_slug:
        program_code = program.get("programCode")
        path_option = await catalog_repository.find_primary_path_option_for_track(
            database,
            track_slug=str(track_slug),
            program_code=str(program_code) if program_code else None,
        )
        if path_option is None:
            raise HTTPException(
                status_code=400,
                detail="Selected track does not match the chosen degree program",
            )
