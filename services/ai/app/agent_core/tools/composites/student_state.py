"""Resolve a student's real record without routing it through a model.

Every composite that reasons over "the student's situation" needs the same
thing: `state`, holding `completedCourses` (plus `plannedSemesters` /
`currentSemesterCode`, which are small). Until now only `check_eligibility`
could obtain it honestly -- it takes a `student_id` and reads the record itself.
The rest take `state` and nothing else, so the only way to fill the argument is
for the model to hand-copy the record out of its own prompt.

Measured live (2026-07-16, ise_correctness), same role, same run, same model:

    check_eligibility(course_id, student_id, target_semester)          96 chars   3.1s
    simulate_course_disruption(course_id, ..., state={17 courses})   1775 chars  41.9s

18x the arguments, 13x the latency -- and three sibling `simulate_course_disruption`
attempts died on the 45s subagent ceiling, taking a Planner replan each. The
ceiling was not the defect; it was the only thing detecting it.

The cost is not only time. `completed_entries` below reads BOTH
`completedCourses` and `completed_courses`, because the relay once snake_cased
the key in transit and the camelCase lookup found nothing -- so a student who had
passed 00940224 was told they were ineligible for a course requiring it.
Transcription does not merely slow a call down; it silently reshapes data and
inverts answers. That workaround's own docstring named this module's job:

    "The real defect is upstream -- a `state` argument that makes a model
    hand-copy structured data between two pieces of our own code -- and until
    that contract changes, this tool must not fail on a key the relay reshaped."

This is that contract change. Given a `student_id`, no record crosses a model at
all, so no amount of transcription can reshape it.

`state` still wins whenever it carries completed courses: that is the what-if
path, where a caller has deliberately altered the record (`mutate_state` failing
a course) and a fresh read would defeat the entire simulation. Same precedence
`check_eligibility` already documents.

Deliberately scoped to `completedCourses`. `plannedSemesters` has no
record->state builder anywhere in the codebase (only `mutate_state` writes it),
and inventing one here would be a second derivation to drift -- the exact thing
`resolve_completed_entries` delegates to `get_entity` to avoid.
`currentSemesterCode` is six characters; it was never the problem.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity

__all__ = ["completed_entries", "resolve_completed_entries", "resolve_student_state"]


def completed_entries(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept either spelling of the completed-courses key.

    `get_entity` emits `completedCourses`, but a `state` argument does not arrive
    straight from it: a specialist reads the record, re-types the facts into its
    own output, and a later one re-types them again into the tool's `state`. LLM
    transcription does not preserve key case -- measured live (2026-07-16) the
    agent sent `completed_courses`, snake_cased somewhere in that relay, so the
    camelCase lookup found nothing and every prerequisite came back missing.

    Kept, not deleted, now that `student_id` exists: `state` remains the what-if
    path and is still model-authored, so the relay can still reshape it. The
    self-fetch path never needs this tolerance -- which is the point.
    """
    for key in ("completedCourses", "completed_courses"):
        entries = state.get(key)
        if entries:
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


async def resolve_completed_entries(
    state: dict[str, Any], student_id: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    """Prefer reading the record ourselves over being told what is in it.

    Returns `(entries, error)`. An absent `student_id` with an empty `state` is
    not an error here -- it yields no entries, and each caller decides whether
    that is fatal for what it was asked to do.

    Delegates to `get_entity` rather than hitting the repository directly --
    `courseNumber` is derived there (from `metadata.courseNumber`, falling back
    to a courseId lookup), and a second copy of that derivation would be a second
    thing to drift.
    """
    entries = completed_entries(state)
    if entries:
        return entries, None
    if not student_id:
        return [], None

    result = await run_get_entity(GetEntityInput(entity_type="completed_courses", entity_id=student_id))
    if not result.ok:
        return [], f"completed_courses_unavailable: {result.error}"
    return completed_entries(result.data or {}), None


async def resolve_student_state(
    state: dict[str, Any], student_id: str | None
) -> tuple[dict[str, Any], str | None]:
    """A NEW state whose `completedCourses` came from the record, unless the
    caller supplied their own.

    Never mutates the caller's dict: a what-if state is the caller's own object,
    and a composite that quietly rewrote it would corrupt the baseline half of
    its own before/after comparison.
    """
    entries, error = await resolve_completed_entries(state, student_id)
    if error:
        return state, error
    if not entries:
        return state, None
    return {**state, "completedCourses": entries}, None
