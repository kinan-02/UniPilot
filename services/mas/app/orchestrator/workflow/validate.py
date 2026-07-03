"""Pre-commit validation phase — delegates to the effector gateway."""

from __future__ import annotations

from app.effectors.gateway import get_effector_gateway
from app.orchestrator.blackboard import Blackboard


def validate_committed_plan(
    *,
    blackboard: Blackboard,
    course_ids: list[str],
) -> tuple[bool, list[str], list[str]]:
    return get_effector_gateway().validate_committed_plan(
        blackboard=blackboard,
        course_ids=course_ids,
    )
