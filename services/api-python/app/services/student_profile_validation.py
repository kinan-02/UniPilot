"""Validate student profile degree references against production catalog."""

from __future__ import annotations

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

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
