"""Unit tests for the fact-admission layer (the three grounding paths, §3.2).

Pure, no LLM: exercises the const-block, the select filter, and the working-set
mutation each handler performs, over a hand-built working set that simulates a
completed tool round.
"""

from __future__ import annotations

from app.agent_core.loop.fact_admission import (
    apply_compute,
    apply_select,
    apply_surface,
    filter_records,
    numeric_const_operands,
)
from app.agent_core.loop.working_set import Fact, WorkingSet
from app.agent_core.subagents.fact_projection import build_call_handles
from app.agent_core.tools.primitives.expression_tree import ExpressionNode

_COMPLETED = [
    {"courseNumber": "00940224", "creditsEarned": 3.5, "grade": 85},
    {"courseNumber": "00960211", "creditsEarned": 4.0, "grade": 90},
    {"courseNumber": "00110001", "creditsEarned": 2.0, "grade": 70},
]


def _working_set_with_completed() -> WorkingSet:
    result_key = 'get_entity:{"entity_id": "u1", "entity_type": "completed_courses"}'
    ws = WorkingSet(question="q", user_id="u1")
    ws.tool_results = {
        result_key: {
            "ok": True,
            "data": {"completedCourses": _COMPLETED},
            "certainty": {"basis": "official_record", "confidence": 1.0},
        }
    }
    ws.handles = build_call_handles(ws.tool_results)
    return ws


# -- const-block (§16.3) ------------------------------------------------------


def test_numeric_const_in_arithmetic_operand_is_flagged():
    node = ExpressionNode(op="subtract", left={"ref": "total"}, right={"const": 155})
    assert numeric_const_operands(node) == [155]


def test_refs_only_arithmetic_is_not_flagged():
    node = ExpressionNode(op="subtract", left={"ref": "total"}, right={"ref": "earned"})
    assert numeric_const_operands(node) == []


def test_const_inside_aggregate_of_is_not_an_arithmetic_operand():
    node = ExpressionNode(op="sum", of={"ref": "completed"}, field="creditsEarned")
    assert numeric_const_operands(node) == []


def test_compute_rejects_laundered_const_operand():
    ws = _working_set_with_completed()
    ws.facts["earned"] = Fact(9.5, "compute(...)", "computed", 1.0)
    new = apply_compute(ws, {"key": "gap", "expression": {"op": "subtract", "left": {"const": 155}, "right": {"ref": "earned"}}})
    assert new == 0
    assert "gap" not in ws.facts
    assert any("REJECTED" in o and "155" in o for o in ws.observations)


# -- select filter (§16.7) ----------------------------------------------------


def test_filter_records_single_match_field():
    value, count = filter_records(_COMPLETED, {"courseNumber": "00940224"}, "grade")
    assert value == 85
    assert count == 1


def test_filter_records_no_match_is_empty_grounded_answer():
    value, count = filter_records(_COMPLETED, {"courseNumber": "99999999"}, "grade")
    assert value == []
    assert count == 0


def test_filter_records_whole_record_when_no_field():
    value, count = filter_records(_COMPLETED, {"courseNumber": "00960211"}, None)
    assert value == {"courseNumber": "00960211", "creditsEarned": 4.0, "grade": 90}
    assert count == 1


def test_filter_records_stringifies_both_sides():
    records = [{"courseNumber": 111, "grade": 88}]
    value, count = filter_records(records, {"courseNumber": "111"}, "grade")
    assert value == 88
    assert count == 1


# -- end-to-end over the working set ------------------------------------------


def test_surface_then_compute_then_select():
    ws = _working_set_with_completed()

    surfaced = apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"})
    assert surfaced == 1
    assert ws.facts["completed"].basis == "official_record"
    assert ws.facts["completed"].value == _COMPLETED

    computed = apply_compute(ws, {"key": "earned", "expression": {"op": "sum", "of": {"ref": "completed"}, "field": "creditsEarned"}})
    assert computed == 1
    assert ws.facts["earned"].value == 9.5
    assert ws.facts["earned"].basis == "computed"

    selected = apply_select(ws, {"key": "grade_x", "from_fact": "completed", "where": {"courseNumber": "00940224"}, "field": "grade"})
    assert selected == 1
    assert ws.facts["grade_x"].value == 85
    assert ws.facts["grade_x"].basis == "official_record"  # inherits the source fact's basis


def test_surface_re_admitting_same_fact_is_not_progress():
    ws = _working_set_with_completed()
    assert apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"}) == 1
    assert apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"}) == 0


def test_re_deriving_same_path_under_a_new_key_is_not_progress():
    # The wandering fix: re-surfacing a value under a fresh key is NOT progress,
    # but is still stored so a later fact_ref resolves.
    ws = _working_set_with_completed()
    assert apply_surface(ws, {"key": "a", "from": "call_1", "path": "data.completedCourses"}) == 1
    assert apply_surface(ws, {"key": "b", "from": "call_1", "path": "data.completedCourses"}) == 0
    assert ws.facts["b"].value == _COMPLETED


def test_distinct_paths_with_equal_values_both_count_as_progress():
    # Two different fields that happen to share a value (both True) must NOT be
    # collapsed -- the signature identifies the operation, not the value.
    result_key = 'get_entity:{"entity_id": "u1", "entity_type": "x"}'
    ws = WorkingSet(question="q", user_id="u1")
    ws.tool_results = {
        result_key: {
            "ok": True,
            "data": {"eligible": True, "schedulable": True},
            "certainty": {"basis": "official_record", "confidence": 1.0},
        }
    }
    ws.handles = build_call_handles(ws.tool_results)
    n = apply_surface(ws, {"selectors": [
        {"key": "elig", "from": "call_1", "path": "data.eligible"},
        {"key": "sched", "from": "call_1", "path": "data.schedulable"},
    ]})
    assert n == 2


def test_re_selecting_the_same_spec_is_not_progress():
    ws = _working_set_with_completed()
    apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"})
    assert apply_select(ws, {"key": "g1", "from_fact": "completed", "where": {"courseNumber": "00940224"}, "field": "grade"}) == 1
    assert apply_select(ws, {"key": "g2", "from_fact": "completed", "where": {"courseNumber": "00940224"}, "field": "grade"}) == 0
    assert ws.facts["g2"].value == 85


def test_select_on_non_list_fact_fails_closed():
    ws = _working_set_with_completed()
    ws.facts["scalar"] = Fact(42, "src", "computed", 1.0)
    new = apply_select(ws, {"key": "x", "from_fact": "scalar", "where": {"a": "b"}})
    assert new == 0
    assert any("is not a list" in o for o in ws.observations)
