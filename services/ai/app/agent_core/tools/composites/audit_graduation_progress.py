"""`audit_graduation_progress` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). Combines a track's required-course list
(`get_track_requirements`) with a student's completed courses (`state`) into
a completion audit, using `apply_deterministic_rule` for the actual
pass/fail determination rather than hand-rolling that comparison inline --
so a caller can override the default "100% of required courses done" bar
with any `count_threshold` rule of its own (e.g. "at least 40 of the 57
required courses" for an early-progress check, not only a final graduation
check).

Optionally (`include_plan=True`) also runs `search_over_state` to project
how many more semesters the remaining required courses will take, reusing
the track's own required-course set via the `courses_required_by_track`
constraint rather than recomputing it from `remainingRequiredCourses` --
the same underlying `contains` traversal `get_track_requirements` itself
already ran, so `search_over_state` independently re-derives an identical
required-course set and subtracts what's already completed/planned itself.

`apply_deterministic_rule` facts contract this tool builds (documented here
since a caller-supplied `completion_rule` must target it):
`facts["requiredCourses"]` is `[{"courseNumber": str, "completed": bool}, ...]`,
one entry per graph-derived required course. The default rule (used when
`completion_rule` is omitted) is `count_threshold` on that source,
`filter={"completed": True}`, `comparator=">="`,
`threshold=<total required course count>` -- "every required course done."

No credit-sum audit here (e.g. "has 130+ credits total") -- that would
need per-course credit lookups (`get_entity`) for potentially dozens of
courses just to build the fact list, which isn't worth the cost for this
tool's default job of tracking *required-course* completion specifically.
A caller that needs a credit-total check already has `apply_deterministic_rule`
directly available for that, built from whatever facts it has on hand.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.composites.get_track_requirements import (
    GetTrackRequirementsInput,
    run_get_track_requirements,
)
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.apply_deterministic_rule import (
    ApplyDeterministicRuleInput,
    run_apply_deterministic_rule,
)
from app.agent_core.tools.primitives.search_over_state import SearchOverStateInput, run_search_over_state
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "audit_graduation_progress"


class AuditGraduationProgressInput(BaseModel):
    track_slug: str
    state: dict[str, Any] = Field(default_factory=dict)
    completion_rule: dict[str, Any] | None = None
    include_plan: bool = False


def _completed_course_numbers(state: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("courseNumber"))
        # Counts unless FAILED. `status` is absent on everything `get_entity`
        # emits and is only ever written by `mutate_state` as "failed", so
        # demanding "completed" here matched nothing -- reporting every student
        # as having earned zero credits. See `check_eligibility`'s own
        # `_completed_course_numbers` for the full account.
        for entry in state.get("completedCourses") or []
        if entry.get("status") != "failed" and entry.get("courseNumber")
    }


def _default_completion_rule(total_required: int) -> dict[str, Any]:
    return {
        "type": "count_threshold",
        "source": "requiredCourses",
        "filter": {"completed": True},
        "comparator": ">=",
        "threshold": total_required,
    }


async def run_audit_graduation_progress(payload: AuditGraduationProgressInput) -> ToolOutputEnvelope:
    track_slug = (payload.track_slug or "").strip()
    if not track_slug:
        return ToolOutputEnvelope(ok=False, data=None, error="track_slug_required")

    track_result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug=track_slug))
    if not track_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"track_requirements_failed: {track_result.error}")

    required_course_ids = [entry["id"] for entry in track_result.data["requiredCourses"]]
    completed = _completed_course_numbers(payload.state)
    completed_required = sorted(set(required_course_ids) & completed)
    remaining_required = sorted(set(required_course_ids) - completed)

    warnings: list[str] = list(track_result.warnings)

    facts = {
        "requiredCourses": [
            {"courseNumber": course_id, "completed": course_id in completed} for course_id in required_course_ids
        ]
    }
    rule = payload.completion_rule or _default_completion_rule(len(required_course_ids))
    rule_result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts=facts))
    if not rule_result.ok:
        return ToolOutputEnvelope(
            ok=False, data=None, error=f"completion_rule_evaluation_failed: {rule_result.error}"
        )

    data: dict[str, Any] = {
        "trackSlug": track_slug,
        "totalRequiredCourses": len(required_course_ids),
        "completedRequiredCourses": completed_required,
        "remainingRequiredCourses": remaining_required,
        "completionRuleResult": rule_result.data,
        "graduationComplete": rule_result.data["satisfied"],
        "projectedPlan": None,
        "projectedPlanCertainty": None,
    }

    if payload.include_plan and remaining_required:
        plan_result = await run_search_over_state(
            SearchOverStateInput(
                state=payload.state,
                constraints=[{"type": "courses_required_by_track", "trackSlug": track_slug}],
                objective="minimize_semesters",
            )
        )
        if plan_result.ok:
            data["projectedPlan"] = plan_result.data
            data["projectedPlanCertainty"] = plan_result.certainty.model_dump(mode="json")
        else:
            warnings.append("graduation_plan_unavailable")

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
        warnings=warnings,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Audit a student's completion progress against one track's required courses: "
    "which required courses are done/remaining, a pass/fail determination via a customizable "
    "apply_deterministic_rule threshold (default: 100% of required courses), and optionally "
    "(include_plan=True) a projected search_over_state plan for the remaining courses.",
    input_model=AuditGraduationProgressInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_audit_graduation_progress,
)
