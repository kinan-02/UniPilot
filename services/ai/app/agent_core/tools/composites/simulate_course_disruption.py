"""`simulate_course_disruption` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). This is the flagship composite: it
automates steps 2-5 of the fail-course-X worked example
(AGENT_VISION.md §10) that the whole architecture was pressure-tested
against -- "what does failing/dropping this course actually do," "what does
it block," "when can it be retaken," "how much does this push back
graduation" -- as one call instead of ~6 chained ones.

Composes (all via the primitives' own `run_*` functions, no new data-access
path):
1. `mutate_state` (`drop_course`, then `fail_course` too if `disruption_type
   == "fail"`) to produce the disrupted state.
2. `traverse_relationship(course_id, "has_prerequisite", "backward")` for
   direct dependents.
3. `extract_temporal_pattern("course_offering", course_id)` for the
   retake-timing pattern.
4. `search_over_state` **twice** -- once on the original `state` (the
   baseline plan) and once on the disrupted state -- then `compare_plans`
   (its own composite tool) to turn the two into one `impact` diff, so the
   caller gets a real before/after comparison, not just a mutated state
   with no context for how much it actually changes.

A real correctness fix baked in here, not left to the caller: `mutate_state
.fail_course` never touches `plannedSemesters` (by design -- it only
records completedCourses status). If a course being "failed" was still
listed in `plannedSemesters[semester]` (e.g. currently in progress), a
naive caller that only calls `fail_course` would leave it there too --
`search_over_state._planned_course_numbers` would then wrongly treat it as
already handled and never reschedule it. This composite always calls
`drop_course` first (a safe no-op if the course wasn't planned there),
*then* `fail_course` when disrupting by failure, so the mutated state is
never inconsistent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.composites.compare_plans import ComparePlansInput, run_compare_plans
from app.agent_core.tools.composites.student_state import resolve_student_state
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.extract_temporal_pattern import (
    ExtractTemporalPatternInput,
    run_extract_temporal_pattern,
)
from app.agent_core.tools.primitives.mutate_state import MutateStateInput, run_mutate_state
from app.agent_core.tools.primitives.search_over_state import SearchOverStateInput, run_search_over_state
from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "simulate_course_disruption"

_KNOWN_DISRUPTION_TYPES: frozenset[str] = frozenset({"fail", "drop"})


class SimulateCourseDisruptionInput(BaseModel):
    course_id: str
    disruption_type: str
    # PREFERRED. Given this, the tool reads the student's completed courses
    # itself and `state` is not needed -- see `student_state.resolve_student_state`.
    #
    # This composite applies the disruption ITSELF (`mutate_state` below), so a
    # caller has no reason to pre-mutate anything: it passes the real record and
    # asks for a what-if against it. Measured live (2026-07-16) the model duly
    # hand-copied all 17 of the student's completed courses into `state` --
    # 1775 chars of argument, a 41.9s call, and three siblings dead on the 45s
    # ceiling -- to hand our own database's rows back to our own code.
    student_id: str | None = None
    # Only for a what-if the CALLER built (e.g. a state already altered via
    # `mutate_state`). Wins over `student_id` when it carries completed courses,
    # because a deliberately-altered state is the whole point of passing one.
    state: dict[str, Any] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    objective: str = "minimize_semesters"
    semester: str | None = None


async def run_simulate_course_disruption(payload: SimulateCourseDisruptionInput) -> ToolOutputEnvelope:
    course_id = (payload.course_id or "").strip()
    if not course_id:
        return ToolOutputEnvelope(ok=False, data=None, error="course_id_required")

    disruption_type = (payload.disruption_type or "").strip()
    if disruption_type not in _KNOWN_DISRUPTION_TYPES:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_disruption_type: {disruption_type}")

    # Read the record ourselves when the caller only named the student, so the
    # completed-course list never has to cross a model to get here.
    state, state_error = await resolve_student_state(payload.state, payload.student_id)
    if state_error:
        return ToolOutputEnvelope(ok=False, data=None, error=state_error)

    semester = payload.semester or state.get("currentSemesterCode")
    if not semester:
        return ToolOutputEnvelope(ok=False, data=None, error="semester_required")

    # -- 1. Mutate the state -------------------------------------------
    drop_result = await run_mutate_state(
        MutateStateInput(
            base_state=state,
            change={"type": "drop_course", "courseNumber": course_id, "semester": semester},
        )
    )
    if not drop_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"mutation_failed: {drop_result.error}")
    disrupted_state = drop_result.data["state"]

    if disruption_type == "fail":
        fail_result = await run_mutate_state(
            MutateStateInput(
                base_state=disrupted_state,
                change={"type": "fail_course", "courseNumber": course_id, "semester": semester},
            )
        )
        if not fail_result.ok:
            return ToolOutputEnvelope(ok=False, data=None, error=f"mutation_failed: {fail_result.error}")
        disrupted_state = fail_result.data["state"]

    # -- 2. Baseline and disrupted plans --------------------------------
    baseline_result = await run_search_over_state(
        SearchOverStateInput(state=state, constraints=payload.constraints, objective=payload.objective)
    )
    if not baseline_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"baseline_plan_failed: {baseline_result.error}")

    disrupted_result = await run_search_over_state(
        SearchOverStateInput(state=disrupted_state, constraints=payload.constraints, objective=payload.objective)
    )
    if not disrupted_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"disrupted_plan_failed: {disrupted_result.error}")

    # -- 3. Supplementary facts -- degrade gracefully, never hard-fail -----
    warnings: list[str] = []

    dependents_result = await run_traverse_relationship(
        TraverseRelationshipInput(entity=course_id, relation="has_prerequisite", direction="backward")
    )
    direct_dependents = dependents_result.data["relatedEntities"] if dependents_result.ok else []
    if not dependents_result.ok:
        warnings.append("direct_dependents_unavailable")

    offering_result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity=course_id)
    )
    retake_pattern: dict[str, Any] | None = None
    if offering_result.ok:
        retake_pattern = {
            **offering_result.data,
            "certainty": offering_result.certainty.model_dump(mode="json"),
        }
    else:
        warnings.append("retake_offering_pattern_unavailable")

    confidences = [disrupted_result.certainty.confidence]
    if offering_result.ok:
        confidences.append(offering_result.certainty.confidence)

    compare_result = await run_compare_plans(
        ComparePlansInput(plan_a=baseline_result.data, plan_b=disrupted_result.data, focus_course_id=course_id)
    )
    if not compare_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"plan_comparison_failed: {compare_result.error}")
    impact = {
        "additionalSemestersUsed": compare_result.data["additionalSemestersUsed"],
        "newlyUnscheduledCourses": compare_result.data["newlyUnscheduledCourses"],
        "courseStillUnscheduled": compare_result.data["focusCourseStillUnscheduled"],
    }

    return ToolOutputEnvelope(
        ok=True,
        data={
            "courseId": course_id,
            "disruptionType": disruption_type,
            "semester": semester,
            "directDependents": direct_dependents,
            "retakeOfferingPattern": retake_pattern,
            "baselinePlan": baseline_result.data,
            "disruptedPlan": disrupted_result.data,
            "impact": impact,
        },
        # Always hypothetical_simulation, regardless of how confident the
        # underlying sub-facts are -- the defining characteristic of this
        # composite's entire output is that it describes a hypothetical,
        # never an official record.
        certainty=CertaintyTag(basis="hypothetical_simulation", confidence=min(confidences)),
        warnings=warnings,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Simulate failing or dropping a course: mutates the state, finds what "
    "directly depends on it, predicts retake timing, and compares a before/after "
    "search_over_state plan -- automates the core of the fail-course-X worked example "
    "(AGENT_VISION.md §10) in one call instead of ~6 chained ones.",
    input_model=SimulateCourseDisruptionInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_simulate_course_disruption,
)
