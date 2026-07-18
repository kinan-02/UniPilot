"""Unit tests for `simulate_course_disruption` (docs/agent/HIGHER_LEVEL_TOOLS.md).

The real end-to-end scenario below was verified directly against the real
engine before writing assertions, not assumed -- including catching my own
test-setup mistake along the way (passing the wrong `semester`, which
silently dropped the course from the wrong `plannedSemesters` entry and
would have made a wrong test pass for the wrong reason).

Facts reused from earlier test suites: "00440148" requires
{"00440105", "00440140"}, has 9 real direct dependents, is reliably offered
in every term (confidence 0.95, 7 semesters of history).
"""

from __future__ import annotations

from typing import Any

from app.agent_core.certainty import CertaintyTag
from app.agent_core.tools.composites.simulate_course_disruption import (
    SimulateCourseDisruptionInput,
    run_simulate_course_disruption,
)
from app.agent_core.tools.envelope import ToolOutputEnvelope


def _base_state(planned_semester: str = "2025-2") -> dict[str, Any]:
    return {
        "currentSemesterCode": "2025-1",
        "completedCourses": [
            {"courseNumber": "00440105", "semester": "2024-1", "status": "completed"},
            {"courseNumber": "00440140", "semester": "2024-1", "status": "completed"},
        ],
        "plannedSemesters": {planned_semester: ["00440148"]},
    }


def _fake_plan_envelope() -> ToolOutputEnvelope:
    """A minimal, but *complete* (matching the real `search_over_state`
    contract, including always-populated `certainty`), fake plan result --
    used wherever a test needs `run_search_over_state` mocked out entirely
    rather than actually reaching the real engine."""
    return ToolOutputEnvelope(
        ok=True,
        data={
            "objective": "minimize_semesters",
            "requiredCourses": [],
            "satisfiedCourses": [],
            "alreadyPlannedCourses": [],
            "plan": {},
            "semestersUsed": 0,
            "unscheduledCourses": [],
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


_CONSTRAINTS = [
    {"type": "courses_required", "courses": ["00440148"]},
    {"type": "max_semesters", "value": 3},
]


async def test_empty_course_id_fails_closed():
    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(course_id="  ", disruption_type="fail", state={}, constraints=[])
    )
    assert result.ok is False
    assert "course_id_required" in result.error


async def test_unknown_disruption_type_fails_closed():
    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(course_id="00440148", disruption_type="explode", state={}, constraints=[])
    )
    assert result.ok is False
    assert "unknown_disruption_type: explode" in result.error


async def test_missing_semester_fails_closed():
    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(course_id="00440148", disruption_type="fail", state={}, constraints=[])
    )
    assert result.ok is False
    assert "semester_required" in result.error


async def test_full_fail_scenario_with_real_data(use_real_academic_data):
    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="fail",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is True
    assert result.data["semester"] == "2025-2"

    dependent_ids = {entry["id"] for entry in result.data["directDependents"]}
    assert {"00450100", "01140035", "01160210"} <= dependent_ids

    assert result.data["retakeOfferingPattern"]["termPatterns"]["2"]["label"] == "reliable"

    baseline = result.data["baselinePlan"]
    assert baseline["alreadyPlannedCourses"] == ["00440148"]
    assert baseline["semestersUsed"] == 0

    disrupted = result.data["disruptedPlan"]
    assert disrupted["alreadyPlannedCourses"] == []
    assert disrupted["plan"]["2025-2"][0]["courseNumber"] == "00440148"
    assert disrupted["semestersUsed"] == 1

    assert result.data["impact"] == {
        "additionalSemestersUsed": 1,
        "newlyUnscheduledCourses": [],
        "courseStillUnscheduled": False,
    }
    assert result.certainty.basis == "hypothetical_simulation"
    assert result.warnings == []


async def test_drop_disruption_does_not_add_a_failed_completed_course_entry(monkeypatch):
    """Spy on `run_mutate_state` to confirm "drop" issues exactly one
    `drop_course` change and never a `fail_course` one -- the real behavioral
    difference between the two disruption types."""
    import app.agent_core.tools.composites.simulate_course_disruption as module

    calls: list[dict[str, Any]] = []
    original = module.run_mutate_state

    async def _spy(payload):
        calls.append(payload.change)
        return await original(payload)

    monkeypatch.setattr(module, "run_mutate_state", _spy)

    async def _fake_search(*_a, **_k):
        return _fake_plan_envelope()

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="drop",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is True
    assert len(calls) == 1
    assert calls[0]["type"] == "drop_course"


async def test_fail_disruption_issues_drop_then_fail(monkeypatch):
    import app.agent_core.tools.composites.simulate_course_disruption as module

    calls: list[dict[str, Any]] = []
    original = module.run_mutate_state

    async def _spy(payload):
        calls.append(payload.change)
        return await original(payload)

    monkeypatch.setattr(module, "run_mutate_state", _spy)

    async def _fake_search(*_a, **_k):
        return _fake_plan_envelope()

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="fail",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is True
    assert [change["type"] for change in calls] == ["drop_course", "fail_course"]


async def test_mutation_failure_propagates(monkeypatch):
    import app.agent_core.tools.composites.simulate_course_disruption as module

    async def _fake_mutate(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="delay_semester_requires_nonnegative_integer_count")

    monkeypatch.setattr(module, "run_mutate_state", _fake_mutate)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148", disruption_type="drop", semester="2025-2", state=_base_state(), constraints=[]
        )
    )
    assert result.ok is False
    assert "mutation_failed" in result.error


async def test_second_mutation_failure_propagates(monkeypatch):
    """`disruption_type="fail"` issues two `mutate_state` calls
    (`drop_course` then `fail_course`) -- this specifically covers the
    second one failing after the first succeeds."""
    import app.agent_core.tools.composites.simulate_course_disruption as module

    original = module.run_mutate_state
    call_count = {"n": 0}

    async def _fake_mutate(payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await original(payload)
        return ToolOutputEnvelope(ok=False, data=None, error="change_track_requires_trackSlug")

    monkeypatch.setattr(module, "run_mutate_state", _fake_mutate)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148", disruption_type="fail", semester="2025-2", state=_base_state(), constraints=[]
        )
    )
    assert result.ok is False
    assert "mutation_failed" in result.error
    assert call_count["n"] == 2


async def test_baseline_plan_failure_propagates(monkeypatch):
    import app.agent_core.tools.composites.simulate_course_disruption as module

    async def _fake_search(payload, *_a, **_k):
        # Fail only the first (baseline) call -- distinguish via the input state.
        if payload.state == _base_state():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        return _fake_plan_envelope()

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="drop",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is False
    assert "baseline_plan_failed" in result.error


async def test_disrupted_plan_failure_propagates(monkeypatch, use_real_academic_data):
    import app.agent_core.tools.composites.simulate_course_disruption as module

    call_count = {"n": 0}
    original = module.run_search_over_state

    async def _fake_search(payload, *_a, **_k):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await original(payload)
        return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_unavailable: boom")

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="drop",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is False
    assert "disrupted_plan_failed" in result.error


async def test_supplementary_facts_degrade_gracefully(monkeypatch):
    import app.agent_core.tools.composites.simulate_course_disruption as module

    async def _fake_search(*_a, **_k):
        return _fake_plan_envelope()

    async def _fake_traverse(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="entity_not_found: X")

    async def _fake_offering(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)
    monkeypatch.setattr(module, "run_traverse_relationship", _fake_traverse)
    monkeypatch.setattr(module, "run_extract_temporal_pattern", _fake_offering)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="drop",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is True
    assert result.data["directDependents"] == []
    assert result.data["retakeOfferingPattern"] is None
    assert set(result.warnings) == {"direct_dependents_unavailable", "retake_offering_pattern_unavailable"}
    # Certainty confidence falls back to just the disrupted plan's own
    # confidence when the offering pattern is unavailable to blend in.
    assert result.certainty.basis == "hypothetical_simulation"


async def test_plan_comparison_failure_propagates(monkeypatch):
    """`compare_plans` is now a real sub-call (extracted from this file's
    former private `_diff_plans` helper) -- this covers it failing, which
    should never happen with real `search_over_state` output (always
    well-formed) but is still handled fail-closed rather than assumed."""
    import app.agent_core.tools.composites.simulate_course_disruption as module

    async def _fake_search(*_a, **_k):
        return _fake_plan_envelope()

    async def _fake_compare(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="malformed_plan_a: missing ['semestersUsed']")

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)
    monkeypatch.setattr(module, "run_compare_plans", _fake_compare)

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00440148",
            disruption_type="drop",
            semester="2025-2",
            state=_base_state(),
            constraints=_CONSTRAINTS,
        )
    )
    assert result.ok is False
    assert "plan_comparison_failed" in result.error
