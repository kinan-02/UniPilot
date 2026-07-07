"""Seed users and student data for agent evaluation runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.completed_course_repository import create_completed_course
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from app.security.password import hash_password

DDS_PROGRAM_CODE = "009216-1-000"
DDS_TRACK_SLUG = "track-data-information-engineering"

# Minimal published-profile seed so course/track workflows pass context validation.
GOLDEN_ANSWER_EVAL_SETUP: dict[str, Any] = {
    "profileTemplate": "dds_track",
    "programCode": "023023-1-000",
    "trackSlug": "track-computer-science-general-4year",
    "catalogYear": 2025,
    "currentSemesterCode": "2025-1",
    "skipIfMissingCatalog": True,
}

# Reuse one bcrypt hash per process for eval user creation — eval-only optimization.
_EVAL_PASSWORD = "AgentEvalPass123!"
_EVAL_PASSWORD_HASH: str | None = None


def eval_password_hash() -> str:
    global _EVAL_PASSWORD_HASH
    if _EVAL_PASSWORD_HASH is None:
        _EVAL_PASSWORD_HASH = hash_password(_EVAL_PASSWORD)
    return _EVAL_PASSWORD_HASH


@dataclass
class EvalUserContext:
    user_id: str
    email: str
    conversation_id: str
    program_id: str | None = None
    seeded_courses: list[str] = field(default_factory=list)


@dataclass
class SetupResult:
    ok: bool
    context: EvalUserContext | None = None
    skip_reason: str | None = None


async def find_published_program(
    database: AsyncIOMotorDatabase,
    *,
    program_code: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    return await database[cfg.degree_programs_collection].find_one(
        {"programCode": program_code, "status": "published"},
        sort=[("catalogYear", -1)],
    )


async def find_published_course_id(
    database: AsyncIOMotorDatabase,
    *,
    course_number: str,
    settings: Settings | None = None,
) -> str | None:
    cfg = settings or get_settings()
    course = await database[cfg.courses_collection].find_one(
        {"courseNumber": course_number, "status": "published"},
        sort=[("catalogYear", -1)],
    )
    if course is None:
        return None
    return str(course["_id"])


async def setup_eval_user(
    database: AsyncIOMotorDatabase,
    *,
    case_id: str,
    setup: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> SetupResult:
    """Create an isolated eval user, optional profile, and conversation."""
    cfg = settings or get_settings()
    setup = setup or {}
    suffix = uuid.uuid4().hex[:10]
    email = f"agent-eval-{case_id}-{suffix}@example.com"

    user = await create_user(
        database,
        email=email,
        password_hash=eval_password_hash(),
    )
    user_id = str(user["_id"])

    conversation = await create_agent_conversation(
        database,
        user_id=user_id,
        title=f"Eval: {case_id}",
    )
    conversation_id = str(conversation["id"])

    context = EvalUserContext(
        user_id=user_id,
        email=email,
        conversation_id=conversation_id,
    )

    profile_template = setup.get("profileTemplate")
    if profile_template == "dds_track":
        program = await find_published_program(
            database,
            program_code=str(setup.get("programCode") or DDS_PROGRAM_CODE),
            settings=cfg,
        )
        if program is None:
            return SetupResult(
                ok=False,
                skip_reason=f"published program {DDS_PROGRAM_CODE!r} not found in MongoDB",
            )

        program_id = str(program["_id"])
        context.program_id = program_id

        await create_student_profile(
            database,
            user_id,
            {
                "institutionId": "technion",
                "programType": "BSc",
                "degreeId": program_id,
                "catalogYear": int(setup.get("catalogYear") or program.get("catalogYear") or 2025),
                "currentSemesterCode": str(setup.get("currentSemesterCode") or "2025-1"),
                "academicPath": {
                    "trackSlug": str(setup.get("trackSlug") or DDS_TRACK_SLUG),
                },
                "preferences": setup.get("preferences") or {},
            },
        )

        completed_numbers = list(setup.get("completedCourseNumbers") or [])
        for course_number in completed_numbers:
            course_id = await find_published_course_id(
                database,
                course_number=str(course_number),
                settings=cfg,
            )
            if course_id is None:
                if setup.get("skipIfMissingCatalog", True):
                    return SetupResult(
                        ok=False,
                        skip_reason=f"course {course_number!r} not found in catalog",
                    )
                continue

            await create_completed_course(
                database,
                user_id,
                {
                    "courseId": course_id,
                    "semesterCode": str(setup.get("completedSemesterCode") or "2024-1"),
                    "grade": 85,
                    "gradePoints": 85,
                    "creditsEarned": 3,
                    "attempt": 1,
                },
                settings=cfg,
            )
            context.seeded_courses.append(str(course_number))

    return SetupResult(ok=True, context=context)
