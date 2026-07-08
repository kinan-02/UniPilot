"""Shared intent literal for the retrieval package.

Standalone redeclaration of `AgentIntent` (originally
`services/agent/app/agent/schemas.py`) — retrieval only ever needs the type,
never anything else from that module, so it is copied here rather than
pulling in `app.agent` as a dependency.
"""

from __future__ import annotations

from typing import Literal

AgentIntent = Literal[
    "graduation_progress_check",
    "transcript_import",
    "semester_plan_generation",
    "semester_plan_modification",
    "course_question",
    "requirement_explanation",
    "prerequisite_check",
    "catalog_search",
    "completed_courses_update",
    "profile_update",
    "program_minor_lookup",
    "track_structure_lookup",
    "regulation_lookup",
    "general_academic_question",
    "unknown_or_unsupported",
]

__all__ = ["AgentIntent"]
