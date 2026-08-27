"""Unit tests for argument binding -- {"ref": factKey} in a tool arg (§17.3)."""

from __future__ import annotations

from app.agent_core.loop.arg_refs import resolve_arg_refs
from app.agent_core.loop.working_set import Fact

_COMPLETED = [{"courseNumber": "00940224", "creditsEarned": 3.5}]


def _facts(**kw: object) -> dict[str, Fact]:
    return {k: Fact(v, "src", "official_record", 1.0) for k, v in kw.items()}


def test_top_level_ref_is_substituted():
    resolved, errors = resolve_arg_refs({"state": {"ref": "altered"}}, _facts(altered={"x": 1}))
    assert resolved == {"state": {"x": 1}}
    assert errors == []


def test_nested_ref_inside_a_literal_wrapper():
    resolved, errors = resolve_arg_refs(
        {"base_state": {"completedCourses": {"ref": "completed"}}}, _facts(completed=_COMPLETED)
    )
    assert resolved == {"base_state": {"completedCourses": _COMPLETED}}
    assert errors == []


def test_ref_in_a_list_is_substituted():
    resolved, errors = resolve_arg_refs({"items": [{"ref": "a"}, {"ref": "b"}]}, _facts(a=1, b=2))
    assert resolved == {"items": [1, 2]}
    assert errors == []


def test_unresolved_ref_is_reported_and_left_in_place():
    resolved, errors = resolve_arg_refs({"state": {"ref": "missing"}}, _facts(other=1))
    assert resolved == {"state": {"ref": "missing"}}
    assert len(errors) == 1
    assert "missing" in errors[0]


def test_dict_with_extra_keys_is_not_treated_as_a_ref():
    # A dict is a ref ONLY if it is exactly {"ref": <str>}. This one is data.
    args = {"ref": "not_a_fact", "semester": "2024-1"}
    resolved, errors = resolve_arg_refs(args, _facts())
    assert resolved == args
    assert errors == []


def test_plain_arguments_pass_through_untouched():
    args = {"course_id": "00960211", "student_id": "u1", "count": 2}
    resolved, errors = resolve_arg_refs(args, _facts())
    assert resolved == args
    assert errors == []
