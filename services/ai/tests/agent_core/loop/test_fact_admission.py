"""Unit tests for the fact-admission layer (the three grounding paths, §3.2).

Pure, no LLM: exercises the const-block, the select filter, and the working-set
mutation each handler performs, over a hand-built working set that simulates a
completed tool round.
"""

from __future__ import annotations

from app.agent_core.loop.fact_admission import (
    _grain_hint,
    _normalize_by,
    _resolve_field_certainty,
    apply_compute,
    apply_select,
    apply_surface,
    filter_records,
    numeric_const_operands,
    project_mapped_records,
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


# -- select comparison operators (§16.7 follow-up) ----------------------------


def test_filter_records_gt_keeps_only_records_above_threshold():
    value, count = filter_records(_COMPLETED, {"grade": {"gt": 85}}, "courseNumber")
    assert value == "00960211"  # only the grade-90 record clears > 85
    assert count == 1


def test_filter_records_gte_includes_the_boundary():
    value, count = filter_records(_COMPLETED, {"grade": {"gte": 85}}, "courseNumber")
    assert set(value) == {"00940224", "00960211"}
    assert count == 2


def test_filter_records_symbol_operator_lt():
    value, count = filter_records(_COMPLETED, {"grade": {"<": 85}}, "courseNumber")
    assert value == "00110001"  # grade 70
    assert count == 1


def test_filter_records_ne_operator():
    value, count = filter_records(_COMPLETED, {"courseNumber": {"ne": "00940224"}}, "courseNumber")
    assert set(value) == {"00960211", "00110001"}


def test_filter_records_comparison_on_non_numeric_fails_closed():
    records = [{"courseNumber": "X", "grade": "not-a-number"}]
    value, count = filter_records(records, {"grade": {"gt": 85}}, "courseNumber")
    assert count == 0
    assert value == []


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


# -- per-field certainty attribution (§4.2) -----------------------------------


def _mixed_provenance_ws() -> WorkingSet:
    """A check_eligibility-shaped result: envelope basis official_record, but the
    offering-derived fields carry their own predicted_pattern basis."""
    result_key = 'check_eligibility:{"course_id": "X"}'
    ws = WorkingSet(question="q", user_id="u1")
    ws.tool_results = {
        result_key: {
            "ok": True,
            "data": {"eligible": True, "schedulable": True, "offeringPattern": {"termPatterns": {"2": {"label": "reliable"}}}},
            "certainty": {"basis": "official_record", "confidence": 1.0},
            "field_certainty": {
                "schedulable": {"basis": "predicted_pattern", "confidence": 0.8},
                "offeringPattern": {"basis": "predicted_pattern", "confidence": 0.8},
            },
        }
    }
    ws.handles = build_call_handles(ws.tool_results)
    return ws


def test_surface_attributes_each_field_its_own_basis():
    ws = _mixed_provenance_ws()
    n = apply_surface(ws, {"selectors": [
        {"key": "elig", "from": "call_1", "path": "data.eligible"},
        {"key": "sched", "from": "call_1", "path": "data.schedulable"},
    ]})
    assert n == 2
    assert ws.facts["elig"].basis == "official_record"  # envelope default
    assert ws.facts["sched"].basis == "predicted_pattern"  # per-field override
    assert ws.facts["sched"].confidence == 0.8


def test_surface_field_certainty_matches_a_path_prefix():
    ws = _mixed_provenance_ws()
    apply_surface(ws, {"key": "label", "from": "call_1", "path": "data.offeringPattern.termPatterns.2.label"})
    assert ws.facts["label"].basis == "predicted_pattern"  # nested under the overridden prefix
    assert ws.facts["label"].confidence == 0.8


def test_surface_without_field_certainty_uses_the_envelope_basis():
    # The common case (no overrides) must be unchanged: envelope basis for all.
    ws = _working_set_with_completed()  # certainty official_record, no field_certainty
    apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"})
    assert ws.facts["completed"].basis == "official_record"


def test_resolve_field_certainty_longest_prefix_wins():
    field_certainty = {
        "offeringPattern": {"basis": "predicted_pattern", "confidence": 0.7},
        "offeringPattern.termPatterns": {"basis": "wiki_derived", "confidence": 0.9},
    }
    assert _resolve_field_certainty("data.offeringPattern.termPatterns.2", field_certainty, "official_record", 1.0) == ("wiki_derived", 0.9)
    assert _resolve_field_certainty("data.offeringPattern.label", field_certainty, "official_record", 1.0) == ("predicted_pattern", 0.7)
    assert _resolve_field_certainty("data.eligible", field_certainty, "official_record", 1.0) == ("official_record", 1.0)
    assert _resolve_field_certainty("data.eligible", {}, "official_record", 1.0) == ("official_record", 1.0)


# -- grain hint: self-healing the "surfaced an object, got stuck" dead-end -----


def test_grain_hint_on_object_names_the_scalar_leaf():
    hint = _grain_hint("data.offeringPattern.termPatterns.3", {"label": "never", "observed": 0, "total": 2})
    assert "OBJECT" in hint
    assert "data.offeringPattern.termPatterns.3.label" in hint  # first key alphabetically


def test_grain_hint_on_record_list_points_to_select():
    hint = _grain_hint("data.completedCourses", [{"courseNumber": "X", "grade": 90}])
    assert "LIST OF RECORDS" in hint
    assert "select" in hint


def test_grain_hint_silent_for_answer_usable_values():
    assert _grain_hint("data.x", ["00940224", "00960211"]) == ""  # list of scalars slots fine
    assert _grain_hint("data.x", 92.5) == ""  # scalar
    assert _grain_hint("data.x", "never") == ""  # scalar string
    assert _grain_hint("data.x", []) == ""  # empty list


def test_surface_of_an_object_appends_the_drill_in_hint():
    ws = _working_set_with_completed()
    apply_surface(ws, {"key": "whole", "from": "call_1", "path": "data"})  # data is a dict
    assert any("OBJECT" in o and "scalar leaf" in o for o in ws.observations)


def test_surface_of_a_record_list_appends_the_select_hint():
    ws = _working_set_with_completed()
    apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"})
    assert any("LIST OF RECORDS" in o for o in ws.observations)


def test_compute_over_a_qualified_fact_inherits_its_basis():
    # §4.2: a computed value is only as authoritative as its weakest input. A gap
    # computed from an INTERPRETED total must carry the interpretation's basis so
    # the answer renders it hedged, not as a flat official number.
    ws = _working_set_with_completed()
    ws.facts["total"] = Fact(158.0, "interpret(...)", "llm_interpretation", 0.9)
    apply_surface(ws, {"key": "completed", "from": "call_1", "path": "data.completedCourses"})
    apply_compute(ws, {"key": "earned", "expression": {"op": "sum", "of": {"ref": "completed"}, "field": "creditsEarned"}})
    apply_compute(ws, {"key": "gap", "expression": {"op": "subtract", "left": {"ref": "total"}, "right": {"ref": "earned"}}})
    assert ws.facts["earned"].basis == "computed"  # pure official inputs stay computed
    assert ws.facts["gap"].basis == "llm_interpretation"  # inherits the weakest input
    assert ws.facts["gap"].confidence == 0.9


# -- select `by` argmax/argmin reduce (§19, the reduce a `map` feeds) ----------

_COUNTS = [
    {"entity": "00940224", "value": 5},
    {"entity": "00960211", "value": 7},
    {"entity": "00110001", "value": 2},
]


def test_filter_records_by_max_returns_the_argmax_record_field():
    value, count = filter_records(_COUNTS, {}, "entity", {"max": "value"})
    assert value == "00960211"  # the one with value 7
    assert count == 1


def test_filter_records_by_min_returns_the_argmin_record_field():
    value, _ = filter_records(_COUNTS, {}, "entity", {"min": "value"})
    assert value == "00110001"  # the one with value 2


def test_filter_records_by_whole_record_when_no_field():
    value, _ = filter_records(_COUNTS, {}, None, {"max": "value"})
    assert value == {"entity": "00960211", "value": 7}


def test_filter_records_by_composes_with_where():
    # First filter to a subset, THEN argmax within it: exclude the top, max of the rest.
    value, _ = filter_records(_COUNTS, {"entity": {"ne": "00960211"}}, "entity", {"max": "value"})
    assert value == "00940224"  # 5 is the max once 7 is filtered out


def test_filter_records_by_ignores_non_numeric_and_missing_fields():
    records = [{"entity": "A", "value": "n/a"}, {"entity": "B", "value": 3}, {"entity": "C"}]
    value, count = filter_records(records, {}, "entity", {"max": "value"})
    assert value == "B"  # only B has a numeric value
    assert count == 1


def test_filter_records_by_with_no_numeric_candidate_selects_nothing():
    records = [{"entity": "A", "value": "x"}, {"entity": "B"}]
    value, count = filter_records(records, {}, "entity", {"max": "value"})
    assert value == []  # empty is itself a grounded answer, not a crash
    assert count == 0


def test_normalize_by_accepts_max_and_min():
    assert _normalize_by({"max": "value"}) == ({"max": "value"}, None)
    assert _normalize_by({"min": "score"}) == ({"min": "score"}, None)
    assert _normalize_by(None) == (None, None)


def test_normalize_by_rejects_malformed_reducers():
    for bad in ({"max": "a", "min": "b"}, {"avg": "value"}, {"max": 3}, {"max": ""}, "max", []):
        by, err = _normalize_by(bad)
        assert by is None and err  # fail closed with a repair message


def test_apply_select_by_max_over_a_grounded_list_fact():
    ws = WorkingSet(question="q", user_id="u1")
    ws.facts["counts"] = Fact(_COUNTS, "map(...)", "predicted_pattern", 0.9)
    admitted = apply_select(ws, {"key": "winner", "from_fact": "counts", "by": {"max": "value"}, "field": "entity"})
    assert admitted == 1
    assert ws.facts["winner"].value == "00960211"
    assert ws.facts["winner"].basis == "predicted_pattern"  # inherits the source list's basis


def test_apply_select_malformed_by_fails_closed_without_admitting():
    ws = WorkingSet(question="q", user_id="u1")
    ws.facts["counts"] = Fact(_COUNTS, "map(...)", "predicted_pattern", 0.9)
    admitted = apply_select(ws, {"key": "winner", "from_fact": "counts", "by": {"top": "value"}, "field": "entity"})
    assert admitted == 0
    assert "winner" not in ws.facts
    assert any("by" in o for o in ws.observations)


# -- map projection core (§19) ------------------------------------------------


def _offering_envelope(count: int) -> dict:
    return {
        "ok": True,
        "data": {"semestersOffered": count},
        "certainty": {"basis": "predicted_pattern", "confidence": 0.9},
    }


def test_project_mapped_records_builds_entity_value_records():
    elements = ["00940224", "00960211", "00110001"]
    envelopes = [_offering_envelope(5), _offering_envelope(7), _offering_envelope(2)]
    records, basis, confidence, errors = project_mapped_records(elements, envelopes, "data.semestersOffered")
    assert records == [
        {"entity": "00940224", "value": 5},
        {"entity": "00960211", "value": 7},
        {"entity": "00110001", "value": 2},
    ]
    assert basis == "predicted_pattern"  # weakest (only) input basis, so the aggregate hedges
    assert confidence == 0.9
    assert errors == []


def test_project_mapped_records_skips_failed_and_missing_never_guesses():
    elements = ["A", "B", "C"]
    envelopes = [
        _offering_envelope(5),
        {"ok": False, "error": "insufficient_history"},
        {"ok": True, "data": {"other": 1}, "certainty": {"basis": "predicted_pattern", "confidence": 0.9}},
    ]
    records, _, _, errors = project_mapped_records(elements, envelopes, "data.semestersOffered")
    assert records == [{"entity": "A", "value": 5}]  # only the one that resolved
    assert any("insufficient_history" in e for e in errors)
    assert any("path 'data.semestersOffered' not found" in e for e in errors)


def test_project_mapped_records_weakest_input_drives_the_basis():
    # A mix of official + predicted collapses to the qualified (predicted) basis, at
    # the lowest confidence -- the aggregate can be no firmer than its softest member.
    elements = ["A", "B"]
    envelopes = [
        {"ok": True, "data": {"v": 3}, "certainty": {"basis": "official_record", "confidence": 1.0}},
        {"ok": True, "data": {"v": 9}, "certainty": {"basis": "predicted_pattern", "confidence": 0.7}},
    ]
    records, basis, confidence, _ = project_mapped_records(elements, envelopes, "data.v")
    assert [r["value"] for r in records] == [3, 9]
    assert basis == "predicted_pattern"
    assert confidence == 0.7


def test_project_mapped_records_all_authoritative_stays_computed():
    envelopes = [
        {"ok": True, "data": {"v": 3}, "certainty": {"basis": "official_record", "confidence": 1.0}},
        {"ok": True, "data": {"v": 9}, "certainty": {"basis": "official_record", "confidence": 1.0}},
    ]
    _, basis, _, _ = project_mapped_records(["A", "B"], envelopes, "data.v")
    assert basis == "computed"  # a collection purely of official records is authoritative
