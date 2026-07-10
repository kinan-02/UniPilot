"""`search_over_state` -- constrained search/optimization (docs/agent/AGENT_VISION.md
§5, primitive 8). Powers both semester-plan generation and what-if simulation
off the same engine (§3.3) -- and requirement-substitute search as the same
search with a different objective.

`constraints`'/`objective`'s vocabulary, the algorithm, and the output shape
are all defined in docs/agent/SEARCH_OVER_STATE_CONTRACT.md -- the single
source of truth for this primitive's contract (confirmed with the user
before implementing, after an initial draft wrongly hardcoded one scenario
into the tool's fixed fields). Update that doc whenever this file's
vocabulary or algorithm changes.

Fully standalone: composes only already-implemented, already-tested
primitives (`get_entity`, `traverse_relationship`, `extract_temporal_pattern`)
plus `AcademicGraphEngine.evaluate_eligibility` directly (the one place that
already gets AND/OR prerequisite logic right -- `traverse_relationship`'s
`has_prerequisite` edges are a flattened set that would incorrectly treat
OR-alternatives as all-required). Zero dependency on `interpret_text` or any
other not-yet-built primitive.
"""

from __future__ import annotations

from numbers import Number
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.extract_temporal_pattern import (
    ExtractTemporalPatternInput,
    run_extract_temporal_pattern,
)
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity
from app.agent_core.tools.primitives.mutate_state import _advance_semester_code
from app.agent_core.tools.primitives.traverse_relationship import (
    TraverseRelationshipInput,
    run_traverse_relationship,
)
from app.agent_core.tools.registry import ToolDescriptor
from app.retrieval.graph_engine.graph_registry import graph_registry

TOOL_NAME = "search_over_state"

_KNOWN_OBJECTIVES: frozenset[str] = frozenset({"minimize_semesters"})
_KNOWN_CONSTRAINT_TYPES: frozenset[str] = frozenset(
    {"courses_required", "courses_required_by_track", "max_credits_per_semester", "max_semesters"}
)
_DEFAULT_MAX_SEMESTERS = 8

_HandlerResult = tuple[dict[str, Any] | None, str | None]


class SearchOverStateInput(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    objective: str = ""


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _validate_constraint_types(constraints: list[dict[str, Any]]) -> str | None:
    """`constraints` is already guaranteed a `list[dict]` by
    `SearchOverStateInput`'s own Pydantic schema -- only each entry's
    `type` value (a plain `str`, deliberately not a `Literal`, same
    extensibility rationale as every other primitive's vocabulary field)
    needs runtime validation. Also validates `courses_required_by_track`'s
    `trackSlug` presence here (pure input shape, no graph access) rather
    than inside `_resolve_required_courses` -- that check must fail fast
    regardless of whether the academic graph is even configured, not get
    masked behind the later graph-availability check.
    """
    for constraint in constraints:
        ctype = constraint.get("type")
        if not ctype:
            return "constraint_type_required"
        if ctype not in _KNOWN_CONSTRAINT_TYPES:
            return f"unknown_constraint_type: {ctype}"
        if ctype == "courses_required_by_track" and not constraint.get("trackSlug"):
            return "courses_required_by_track_requires_trackSlug"
    return None


def _resolve_numeric_bound(
    constraints: list[dict[str, Any]], ctype: str, default: float
) -> tuple[float | None, str | None]:
    values: list[float] = []
    for constraint in constraints:
        if constraint.get("type") != ctype:
            continue
        value = constraint.get("value")
        if not _is_number(value) or value <= 0:
            return None, f"{ctype}_requires_positive_numeric_value"
        values.append(value)
    return (min(values) if values else default), None


async def _resolve_required_courses(constraints: list[dict[str, Any]]) -> _HandlerResult:
    required: set[str] = set()
    for constraint in constraints:
        ctype = constraint.get("type")
        if ctype == "courses_required":
            for course in constraint.get("courses") or []:
                required.add(str(course))
        elif ctype == "courses_required_by_track":
            track_slug = constraint["trackSlug"]  # presence already validated by _validate_constraint_types
            result = await run_traverse_relationship(
                TraverseRelationshipInput(entity=track_slug, relation="contains", direction="forward")
            )
            if not result.ok:
                return None, f"courses_required_by_track_failed: {track_slug}: {result.error}"
            for entry in result.data["relatedEntities"]:
                if entry.get("nodeType") == "course":
                    required.add(entry["id"])
    return {"required": required}, None


def _completed_course_numbers(state: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("courseNumber"))
        for entry in state.get("completedCourses") or []
        if entry.get("status") == "completed" and entry.get("courseNumber")
    }


def _planned_course_numbers(state: dict[str, Any]) -> set[str]:
    planned: set[str] = set()
    for courses in (state.get("plannedSemesters") or {}).values():
        planned.update(str(course) for course in courses or [])
    return planned


async def _course_credits(course_number: str) -> float | None:
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id=course_number))
    if not result.ok:
        return None
    credits = result.data.get("credits")
    try:
        return float(credits)
    except (TypeError, ValueError):
        return None


async def _offering_certainty_for_term(course_number: str, term_index: int) -> tuple[bool, dict[str, Any]]:
    """Returns (schedulable_this_term, certainty_dict). Never blocks a
    semester just because the prediction itself is undetermined -- only a
    positive "never" bucket excludes a term.
    """
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity=course_number)
    )
    if not result.ok:
        return True, {"basis": "predicted_pattern", "confidence": 0.0}

    term_pattern = result.data["termPatterns"].get(str(term_index))
    if term_pattern is not None and term_pattern["label"] == "never":
        return False, {"basis": "predicted_pattern", "confidence": result.certainty.confidence}
    return True, {"basis": result.certainty.basis, "confidence": result.certainty.confidence}


async def _minimize_semesters(
    state: dict[str, Any], required: set[str], max_credits: float | None, max_semesters: float
) -> dict[str, Any]:
    satisfied = _completed_course_numbers(state)
    already_scheduled = _planned_course_numbers(state)
    remaining = sorted(required - satisfied - already_scheduled)

    plan: dict[str, list[dict[str, Any]]] = {}
    semester_credit_totals: dict[str, float] = {}
    for semester_code, courses in (state.get("plannedSemesters") or {}).items():
        total = 0.0
        for course in courses or []:
            credits = await _course_credits(str(course))
            total += credits or 0.0
        semester_credit_totals[semester_code] = total

    eligible_pool = set(satisfied) | already_scheduled
    current_semester = state.get("currentSemesterCode")
    semesters_used = 0

    while remaining and current_semester and semesters_used < int(max_semesters):
        current_semester = _advance_semester_code(str(current_semester), 1)
        if current_semester is None:
            break
        semesters_used += 1
        term_index = int(current_semester.split("-")[1])
        scheduled_this_pass: list[str] = []

        for course_number in list(remaining):
            engine = graph_registry.get_engine()
            eligible, _missing = engine.evaluate_eligibility(course_number, eligible_pool)
            if not eligible:
                continue

            schedulable, offering_certainty = await _offering_certainty_for_term(course_number, term_index)
            if not schedulable:
                continue

            credits = await _course_credits(course_number) or 0.0
            projected_total = semester_credit_totals.get(current_semester, 0.0) + credits
            if max_credits is not None and projected_total > max_credits:
                continue

            plan.setdefault(current_semester, []).append(
                {"courseNumber": course_number, "credits": credits, "offeringCertainty": offering_certainty}
            )
            semester_credit_totals[current_semester] = projected_total
            scheduled_this_pass.append(course_number)

        for course_number in scheduled_this_pass:
            remaining.remove(course_number)
            eligible_pool.add(course_number)

    return {
        "plan": plan,
        "semestersUsed": len(plan),
        "unscheduledCourses": remaining,
    }


def _aggregate_certainty(plan: dict[str, list[dict[str, Any]]]) -> CertaintyTag:
    entries = [course["offeringCertainty"] for courses in plan.values() for course in courses]
    if not entries:
        return CertaintyTag(basis="official_record", confidence=1.0)
    weakest = min(entries, key=lambda entry: entry["confidence"])
    basis = "predicted_pattern" if any(entry["basis"] == "predicted_pattern" for entry in entries) else "official_record"
    return CertaintyTag(basis=basis, confidence=weakest["confidence"])


async def run_search_over_state(payload: SearchOverStateInput) -> ToolOutputEnvelope:
    objective = (payload.objective or "").strip()
    if not objective:
        return ToolOutputEnvelope(ok=False, data=None, error="objective_required")
    if objective not in _KNOWN_OBJECTIVES:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_objective: {objective}")

    type_error = _validate_constraint_types(payload.constraints)
    if type_error:
        return ToolOutputEnvelope(ok=False, data=None, error=type_error)

    max_credits, error = _resolve_numeric_bound(payload.constraints, "max_credits_per_semester", default=None)
    if error:
        return ToolOutputEnvelope(ok=False, data=None, error=error)
    max_semesters, error = _resolve_numeric_bound(
        payload.constraints, "max_semesters", default=_DEFAULT_MAX_SEMESTERS
    )
    if error:
        return ToolOutputEnvelope(ok=False, data=None, error=error)

    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        graph_registry.get_engine()
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_graph_unavailable: {exc}")

    resolved, error = await _resolve_required_courses(payload.constraints)
    if error:
        return ToolOutputEnvelope(ok=False, data=None, error=error)
    required = resolved["required"]

    satisfied = sorted(_completed_course_numbers(payload.state) & required)
    already_planned = sorted(_planned_course_numbers(payload.state) & required)

    search_result = await _minimize_semesters(payload.state, required, max_credits, max_semesters)

    return ToolOutputEnvelope(
        ok=True,
        data={
            "objective": objective,
            "requiredCourses": sorted(required),
            "satisfiedCourses": satisfied,
            "alreadyPlannedCourses": already_planned,
            "plan": search_result["plan"],
            "semestersUsed": search_result["semestersUsed"],
            "unscheduledCourses": search_result["unscheduledCourses"],
        },
        certainty=_aggregate_certainty(search_result["plan"]),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Constrained search/optimization over a state object given a typed constraint "
    "list and an objective -- the same engine for plan generation, what-if simulation, and "
    "(later) requirement-substitute search, parameterized differently each time. "
    "See docs/agent/SEARCH_OVER_STATE_CONTRACT.md for the constraint/objective vocabulary.",
    input_model=SearchOverStateInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_search_over_state,
)
