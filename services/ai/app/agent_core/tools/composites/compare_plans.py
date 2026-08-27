"""`compare_plans` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). A pure, deterministic diff over two
`search_over_state`-shaped plan results (`semestersUsed` +
`unscheduledCourses`) -- no new primitive calls, no data access of its own.

Extracted from `simulate_course_disruption.py`'s private `_diff_plans`
helper (which now delegates here) so any caller holding two independently
produced plans -- not just a disrupted-vs-baseline pair from that one
composite -- can compare them the same way: two different track choices,
two different constraint sets, a "before" plan against a re-run "after" a
student's actual semester results came in, etc. Generic on purpose: this
tool has no opinion about *why* the two plans differ, only about what the
delta is.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.identifiers import COURSE_ID_DESCRIPTION
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "compare_plans"

_REQUIRED_PLAN_FIELDS = ("semestersUsed", "unscheduledCourses")


class ComparePlansInput(BaseModel):
    plan_a: dict[str, Any]
    plan_b: dict[str, Any]
    focus_course_id: str | None = Field(default=None, description=COURSE_ID_DESCRIPTION)


def _missing_fields(plan: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_PLAN_FIELDS if field not in plan]


async def run_compare_plans(payload: ComparePlansInput) -> ToolOutputEnvelope:
    for label, plan in (("plan_a", payload.plan_a), ("plan_b", payload.plan_b)):
        missing = _missing_fields(plan)
        if missing:
            return ToolOutputEnvelope(ok=False, data=None, error=f"malformed_{label}: missing {missing}")

    plan_a, plan_b = payload.plan_a, payload.plan_b
    unscheduled_a = set(plan_a["unscheduledCourses"])
    unscheduled_b = set(plan_b["unscheduledCourses"])
    focus_course_id = payload.focus_course_id

    data: dict[str, Any] = {
        "additionalSemestersUsed": plan_b["semestersUsed"] - plan_a["semestersUsed"],
        "newlyUnscheduledCourses": sorted(unscheduled_b - unscheduled_a),
        "newlyScheduledCourses": sorted(unscheduled_a - unscheduled_b),
        "focusCourseId": focus_course_id,
        "focusCourseStillUnscheduled": (focus_course_id in unscheduled_b) if focus_course_id else None,
    }

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        # A pure, exact computation over whatever two plans were handed in --
        # same deterministic-compute classification apply_deterministic_rule
        # uses, not a claim about the certainty of the plans themselves.
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Pure deterministic diff between two search_over_state-shaped plan results "
    "(semestersUsed + unscheduledCourses): additional semesters used, newly "
    "scheduled/unscheduled courses, and optionally whether one focus course is still "
    "unscheduled in the second plan. No new data access -- just a comparison.",
    input_model=ComparePlansInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_compare_plans,
)
