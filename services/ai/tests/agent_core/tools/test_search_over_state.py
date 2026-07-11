"""Unit tests for `search_over_state` (docs/agent/AGENT_VISION.md §5, primitive 8).

`constraints`/`objective` vocabulary, algorithm, and output shape are
defined in docs/agent/SEARCH_OVER_STATE_CONTRACT.md. Every real-data case
below was verified directly against the real engine before writing
assertions, not assumed:
- Course "00440148" requires "00440105"+"00440140" (has_prerequisite,
  reused from earlier primitives' tests); reliable-every-term offering
  pattern (verified in test_extract_temporal_pattern.py already).
- Course "00140008": zero prerequisites (`prerequisites_ast ==
  {"type": "AND", "operands": []}`, confirmed directly, not inferred from a
  falsy "operands" key -- a single-prerequisite course's AST has no
  "operands" key at all and would have false-matched a naive check),
  3 credits, reliable Winter(1)/Spring(2), never Summer(3).
- Track "track-materials-engineering" `contains` course "01040019" (reused
  from test_traverse_relationship.py).
- "track-does-not-exist" resolves to nothing (genuine not-found case).
"""

from __future__ import annotations

import pytest

from app.agent_core.tools.primitives.search_over_state import (
    SearchOverStateInput,
    _aggregate_certainty,
    _course_credits,
    _offering_certainty_for_term,
    run_search_over_state,
)


# -- validation / fail-closed, no real data needed -------------------------


async def test_missing_objective_fails_closed():
    result = await run_search_over_state(SearchOverStateInput(state={}, constraints=[], objective=""))
    assert result.ok is False
    assert "objective_required" in result.error


async def test_unknown_objective_fails_closed():
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[], objective="maximize_fun")
    )
    assert result.ok is False
    assert "unknown_objective: maximize_fun" in result.error


async def test_constraint_missing_type_fails_closed():
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[{"courses": ["00440148"]}], objective="minimize_semesters")
    )
    assert result.ok is False
    assert "constraint_type_required" in result.error


async def test_unknown_constraint_type_fails_closed():
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[{"type": "teleport"}], objective="minimize_semesters")
    )
    assert result.ok is False
    assert "unknown_constraint_type: teleport" in result.error


@pytest.mark.parametrize("bad_value", ["a lot", 0, -5, True])
async def test_max_credits_per_semester_rejects_invalid_value(bad_value):
    result = await run_search_over_state(
        SearchOverStateInput(
            state={},
            constraints=[{"type": "max_credits_per_semester", "value": bad_value}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is False
    assert "max_credits_per_semester_requires_positive_numeric_value" in result.error


async def test_max_semesters_rejects_invalid_value():
    result = await run_search_over_state(
        SearchOverStateInput(
            state={}, constraints=[{"type": "max_semesters", "value": -1}], objective="minimize_semesters"
        )
    )
    assert result.ok is False
    assert "max_semesters_requires_positive_numeric_value" in result.error


async def test_courses_required_by_track_missing_slug_fails_closed():
    result = await run_search_over_state(
        SearchOverStateInput(
            state={}, constraints=[{"type": "courses_required_by_track"}], objective="minimize_semesters"
        )
    )
    assert result.ok is False
    assert "courses_required_by_track_requires_trackSlug" in result.error


async def test_substitute_for_missing_fields_fails_closed():
    result = await run_search_over_state(
        SearchOverStateInput(
            state={}, constraints=[{"type": "substitute_for", "courseId": "00440148"}], objective="find_substitute"
        )
    )
    assert result.ok is False
    assert "substitute_for_requires_courseId_and_trackSlug" in result.error


async def test_find_substitute_objective_requires_substitute_for_constraint():
    result = await run_search_over_state(SearchOverStateInput(state={}, constraints=[], objective="find_substitute"))
    assert result.ok is False
    assert "substitute_for_constraint_required" in result.error


async def test_substitute_for_constraint_rejected_outside_find_substitute():
    result = await run_search_over_state(
        SearchOverStateInput(
            state={},
            constraints=[
                {"type": "substitute_for", "courseId": "00440148", "trackSlug": "track-materials-engineering"}
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is False
    assert "substitute_for_constraint_requires_find_substitute_objective" in result.error


async def test_multiple_substitute_for_constraints_rejected():
    constraint = {"type": "substitute_for", "courseId": "00440148", "trackSlug": "track-materials-engineering"}
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[constraint, dict(constraint)], objective="find_substitute")
    )
    assert result.ok is False
    assert "substitute_for_constraint_must_be_singular" in result.error


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[], objective="minimize_semesters")
    )
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_search_over_state(
        SearchOverStateInput(state={}, constraints=[], objective="minimize_semesters")
    )
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


# -- _aggregate_certainty direct unit coverage ------------------------------


def test_aggregate_certainty_empty_plan_is_official_record():
    tag = _aggregate_certainty({})
    assert tag.basis == "official_record"
    assert tag.confidence == 1.0


# -- real-data: trivial / accounting cases ----------------------------------


async def test_no_constraints_is_a_trivial_success(use_real_academic_data):
    result = await run_search_over_state(
        SearchOverStateInput(
            state={"currentSemesterCode": "2025-1"}, constraints=[], objective="minimize_semesters"
        )
    )
    assert result.ok is True
    assert result.data["requiredCourses"] == []
    assert result.data["plan"] == {}
    assert result.data["semestersUsed"] == 0
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_already_completed_required_course_needs_no_scheduling(use_real_academic_data):
    state = {
        "currentSemesterCode": "2025-1",
        "completedCourses": [{"courseNumber": "00140008", "semester": "2024-1", "status": "completed"}],
        "plannedSemesters": {},
    }
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[{"type": "courses_required", "courses": ["00140008"]}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["satisfiedCourses"] == ["00140008"]
    assert result.data["alreadyPlannedCourses"] == []
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == []


async def test_failed_course_is_not_treated_as_satisfied(use_real_academic_data):
    """A "failed" completedCourses entry must not count as satisfying the
    requirement -- matches mutate_state.fail_course's own semantics."""
    state = {
        "currentSemesterCode": "2025-2",
        "completedCourses": [{"courseNumber": "00140008", "semester": "2024-1", "status": "failed"}],
        "plannedSemesters": {},
    }
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[{"type": "courses_required", "courses": ["00140008"]}, {"type": "max_semesters", "value": 2}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["satisfiedCourses"] == []
    assert "2026-1" in result.data["plan"]


async def test_already_planned_required_course_is_not_rescheduled(use_real_academic_data):
    state = {
        "currentSemesterCode": "2025-1",
        "completedCourses": [],
        "plannedSemesters": {"2025-2": ["00140008"]},
    }
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[{"type": "courses_required", "courses": ["00140008"]}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["alreadyPlannedCourses"] == ["00140008"]
    assert result.data["satisfiedCourses"] == []
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == []


# -- real-data: scheduling with prerequisites -------------------------------


async def test_course_scheduled_once_prerequisites_satisfied(use_real_academic_data):
    state = {
        "currentSemesterCode": "2025-1",
        "completedCourses": [
            {"courseNumber": "00440105", "semester": "2024-1", "status": "completed"},
            {"courseNumber": "00440140", "semester": "2024-1", "status": "completed"},
        ],
        "plannedSemesters": {},
    }
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[{"type": "courses_required", "courses": ["00440148"]}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"]["2025-2"][0]["courseNumber"] == "00440148"
    assert result.data["semestersUsed"] == 1
    assert result.data["unscheduledCourses"] == []
    assert result.certainty.basis == "predicted_pattern"


async def test_course_with_unmet_prerequisites_stays_unscheduled(use_real_academic_data):
    state = {"currentSemesterCode": "2025-1", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00440148"]},
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == ["00440148"]


# -- real-data: offering-pattern exclusion ("never" bucket) -----------------


async def test_course_never_offered_in_only_reachable_term_stays_unscheduled(use_real_academic_data):
    """00140008 has zero prerequisites but is never offered in Summer
    (term 3). Starting from Spring 2025 with max_semesters=1, the only
    reachable semester is Summer 2025 -- must stay unscheduled."""
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},
                {"type": "max_semesters", "value": 1},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == ["00140008"]


async def test_course_scheduled_once_a_viable_term_is_reached(use_real_academic_data):
    """Same course/state as above, but max_semesters=2 reaches Winter 2026
    (term 1, "reliable") after skipping the unviable Summer 2025."""
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"] == {"2026-1": [{"courseNumber": "00140008", "credits": 3.0, "offeringCertainty": {"basis": "predicted_pattern", "confidence": 0.95}}]}
    assert result.data["unscheduledCourses"] == []
    assert result.certainty.confidence == pytest.approx(0.95)


# -- real-data: max_credits_per_semester --------------------------------


async def test_credit_cap_too_low_blocks_scheduling(use_real_academic_data):
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},  # 3 credits
                {"type": "max_credits_per_semester", "value": 1},
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == ["00140008"]


async def test_credit_cap_sufficient_allows_scheduling(use_real_academic_data):
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},  # 3 credits
                {"type": "max_credits_per_semester", "value": 3},
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["unscheduledCourses"] == []


async def test_existing_planned_credits_count_toward_the_cap(use_real_academic_data):
    """An already-planned course's credits must occupy the same semester's
    credit budget, even though it isn't rescheduled itself."""
    state = {
        "currentSemesterCode": "2024-3",  # -> next semester is 2025-1 (Winter)
        "completedCourses": [],
        "plannedSemesters": {"2025-1": ["00140008"]},  # 3 credits already used
    }
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},
                {"type": "max_credits_per_semester", "value": 3},
                {"type": "max_semesters", "value": 1},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    # 00140008 is already planned -- nothing left to schedule at all, but
    # this still confirms the already-planned accounting path is taken
    # instead of raising/mis-tracking credits.
    assert result.data["alreadyPlannedCourses"] == ["00140008"]


# -- real-data: constraint unions and min-wins tie-breaks -------------------


async def test_courses_required_and_by_track_union_together(use_real_academic_data):
    result = await run_search_over_state(
        SearchOverStateInput(
            state={"currentSemesterCode": "2025-1"},
            constraints=[
                {"type": "courses_required", "courses": ["00440148"]},
                {"type": "courses_required_by_track", "trackSlug": "track-materials-engineering"},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert "00440148" in result.data["requiredCourses"]
    assert "01040019" in result.data["requiredCourses"]  # verified track-materials-engineering --contains--> 01040019


async def test_courses_required_by_track_not_found_fails_closed(use_real_academic_data):
    result = await run_search_over_state(
        SearchOverStateInput(
            state={"currentSemesterCode": "2025-1"},
            constraints=[{"type": "courses_required_by_track", "trackSlug": "track-does-not-exist"}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is False
    assert "courses_required_by_track_failed: track-does-not-exist" in result.error


# -- real-data: find_substitute objective -----------------------------------


async def test_find_substitute_excludes_the_course_itself_from_the_pool(use_real_academic_data):
    """track-materials-engineering has 57 required courses (verified in
    test_get_track_requirements.py); substituting for one of them ("00350022",
    verified directly to be a member) should yield a 56-course candidate
    pool that never includes "00350022" itself."""
    state = {"currentSemesterCode": "2025-1", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {
                    "type": "substitute_for",
                    "courseId": "00350022",
                    "trackSlug": "track-materials-engineering",
                }
            ],
            objective="find_substitute",
        )
    )
    assert result.ok is True
    assert len(result.data["requiredCourses"]) == 56
    assert "00350022" not in result.data["requiredCourses"]
    # Verified directly: within the default 8-semester bound, 13 of the 56
    # candidates come out schedulable, the first ("00350053", "01040019")
    # landing in the very next semester (2025-2).
    scheduled = [c["courseNumber"] for courses in result.data["plan"].values() for c in courses]
    assert len(scheduled) == 13
    assert set(result.data["plan"]["2025-2"][i]["courseNumber"] for i in range(2)) == {"00350053", "01040019"}


async def test_find_substitute_pool_from_unknown_track_fails_closed(use_real_academic_data):
    result = await run_search_over_state(
        SearchOverStateInput(
            state={"currentSemesterCode": "2025-1"},
            constraints=[
                {"type": "substitute_for", "courseId": "00350022", "trackSlug": "track-does-not-exist"}
            ],
            objective="find_substitute",
        )
    )
    assert result.ok is False
    assert "substitute_pool_unavailable: track-does-not-exist" in result.error


async def test_multiple_max_semesters_constraints_use_the_minimum(use_real_academic_data):
    """5 and 2 given together -> effectively bounded to 2, same as the
    single-constraint case that also lands on Winter 2026."""
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},
                {"type": "max_semesters", "value": 5},
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["unscheduledCourses"] == []
    assert list(result.data["plan"].keys()) == ["2026-1"]


async def test_multiple_max_credits_constraints_use_the_minimum(use_real_academic_data):
    state = {"currentSemesterCode": "2025-2", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[
                {"type": "courses_required", "courses": ["00140008"]},  # 3 credits
                {"type": "max_credits_per_semester", "value": 10},
                {"type": "max_credits_per_semester", "value": 1},  # the binding one
                {"type": "max_semesters", "value": 2},
            ],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["unscheduledCourses"] == ["00140008"]


# -- targeted branch coverage: helper functions in isolation ----------------


async def test_course_credits_returns_none_for_unknown_course(use_real_academic_data):
    assert await _course_credits("99999999") is None


async def test_course_credits_returns_none_for_non_numeric_credits(monkeypatch):
    import app.agent_core.tools.primitives.search_over_state as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_get_entity(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"credits": "not-a-number"})

    monkeypatch.setattr(module, "run_get_entity", _fake_get_entity)
    assert await _course_credits("00000000") is None


async def test_offering_certainty_undetermined_does_not_block(monkeypatch):
    """When `extract_temporal_pattern` itself fails (no data at all), the
    term must still be treated as schedulable, tagged with 0 confidence --
    a missing prediction is not the same as a negative one."""
    import app.agent_core.tools.primitives.search_over_state as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_extract(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    monkeypatch.setattr(module, "run_extract_temporal_pattern", _fake_extract)
    schedulable, certainty = await _offering_certainty_for_term("00000000", 1)
    assert schedulable is True
    assert certainty == {"basis": "predicted_pattern", "confidence": 0.0}


async def test_unparseable_current_semester_code_yields_no_plan(use_real_academic_data):
    """`_advance_semester_code` returning `None` for an unparseable
    `currentSemesterCode` must stop the search cleanly rather than loop or
    raise -- everything required stays unscheduled."""
    state = {"currentSemesterCode": "not-a-semester-code", "completedCourses": [], "plannedSemesters": {}}
    result = await run_search_over_state(
        SearchOverStateInput(
            state=state,
            constraints=[{"type": "courses_required", "courses": ["00140008"]}],
            objective="minimize_semesters",
        )
    )
    assert result.ok is True
    assert result.data["plan"] == {}
    assert result.data["unscheduledCourses"] == ["00140008"]
