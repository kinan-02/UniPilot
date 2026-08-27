"""Tests for `subagents/fact_projection.py`.

The specification here is the 2026-07-16 ise_correctness live run. Two failures
from that run are encoded directly as tests: the honest citation that got its
facts deleted (`presupposition_conflict` step 1a), and the fabricated credit
total that got published (`credits_remaining`). Projection has to fix the first
and make the second unexpressible.
"""

from __future__ import annotations

from app.agent_core.subagents.fact_projection import (
    available_paths,
    build_call_handles,
    describe_call,
    project_facts,
    resolve_path,
)

# The real recorded envelope shape: `ToolOutputEnvelope.model_dump(mode="json")`,
# keyed by tool_round's `f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"`.
_PROFILE_KEY = 'get_entity:{"entity_id": "6a58b4a0c24b4bfb42aa27f3", "entity_type": "student_profile"}'
_COURSES_KEY = 'get_entity:{"entity_id": "6a58b4a0c24b4bfb42aa27f3", "entity_type": "completed_courses"}'

_PROFILE_ENVELOPE = {
    "ok": True,
    "data": {
        "programSlug": "track-information-systems-engineering",
        "catalogYear": 2025,
        "academicPath": {"trackSlug": "track-information-systems-engineering", "minors": []},
    },
    "certainty": {"basis": "official_record", "confidence": 1.0, "source_ref": None},
    "error": None,
    "warnings": [],
}

_COURSES_ENVELOPE = {
    "ok": True,
    "data": {
        "completedCourses": [
            {"courseNumber": "00940345", "grade": 88.0, "creditsEarned": 4.0},
            {"courseNumber": "00940224", "grade": 85.0, "creditsEarned": 4.0},
        ]
    },
    "certainty": {"basis": "official_record", "confidence": 1.0, "source_ref": None},
    "error": None,
    "warnings": [],
}

_TOOL_RESULTS = {_PROFILE_KEY: _PROFILE_ENVELOPE, _COURSES_KEY: _COURSES_ENVELOPE}
_HANDLES = build_call_handles(_TOOL_RESULTS)


def test_the_live_false_positive_now_projects_instead_of_dropping():
    """CAUGHT LIVE (2026-07-16, `presupposition_conflict` step 1a).

    The model emitted three real facts citing `student_profile.programSlug` --
    the entity and field, not the function -- so `_drop_ungrounded_facts`
    matched no tool name and deleted all three. The step published `facts: {}`
    at confidence 0.9 and still reported `succeeded`.

    Under projection there is no citation to misjudge: the value is read out of
    the recorded envelope, so the phrasing that broke it cannot exist.
    """
    outcome = project_facts(
        [
            {"key": "degree_program", "from": "call_1", "path": "data.programSlug"},
            {"key": "catalog_year", "from": "call_1", "path": "data.catalogYear"},
            {"key": "academic_path", "from": "call_1", "path": "data.academicPath"},
        ],
        _TOOL_RESULTS,
        _HANDLES,
    )

    assert outcome.errors == []
    assert outcome.facts["degree_program"]["value"] == "track-information-systems-engineering"
    assert outcome.facts["catalog_year"]["value"] == 2025
    # `academicPath` is a real nested object on the profile document
    # (StudentAcademicPath), so grouping it needs no composite selector -- one
    # fact, one path holds.
    assert outcome.facts["academic_path"]["value"] == {
        "trackSlug": "track-information-systems-engineering",
        "minors": [],
    }


def test_a_fabricated_total_is_unexpressible():
    """CAUGHT LIVE (2026-07-16, `credits_remaining`).

    Retrieval published `{"key": "totalCreditsEarned", "value": 63.0, "source":
    "sum of creditsEarned across all 17 completed courses"}`. The real total is
    62.5. The old guard caught it only because the model confessed to the
    arithmetic in its citation; the same 63.0 citing `get_entity(...)` would
    have passed.

    A selector has no value field. The number cannot be written down at all --
    the only way to name a credit total is to point at one a tool returned, and
    no tool returns a summed total. Deriving one is `calculation_validation`'s
    job (`expression_tree` has `sum`).
    """
    outcome = project_facts(
        [{"key": "totalCreditsEarned", "from": "call_2", "path": "data.totalCreditsEarned"}],
        _TOOL_RESULTS,
        _HANDLES,
    )

    assert outcome.facts == {}
    assert len(outcome.errors) == 1
    assert "does not exist" in outcome.errors[0]
    # Every projected value is one a tool actually returned.
    grounded = project_facts(
        [{"key": "completedCourses", "from": "call_2", "path": "data.completedCourses"}],
        _TOOL_RESULTS,
        _HANDLES,
    )
    assert grounded.facts["completedCourses"]["value"] == _COURSES_ENVELOPE["data"]["completedCourses"]


def test_source_and_confidence_are_generated_from_the_call_that_ran():
    """`source` is a record, not a claim -- the model never writes it.

    Live (2026-07-16, `presupposition_conflict` step 1a) the retrieval result
    omitted `certainty_basis` entirely, so `result_normalizer`'s defaults
    backfilled `"llm_interpretation"` -- tagging a plain
    `get_entity(student_profile)` read as model guesswork while the tool that
    served it had already declared `official_record` at confidence 1.0. `bases`
    exists so the caller can tag the step from the envelope instead.
    """
    outcome = project_facts(
        [{"key": "catalog_year", "from": "call_1", "path": "data.catalogYear"}], _TOOL_RESULTS, _HANDLES
    )

    fact = outcome.facts["catalog_year"]
    assert fact["source"] == "get_entity(entity_id=6a58b4a0c24b4bfb42aa27f3, entity_type=student_profile)"
    assert fact["confidence"] == 1.0
    assert outcome.bases == ["official_record"]


def test_an_unknown_path_names_the_paths_that_do_exist():
    """An error a model cannot act on gets retried verbatim -- live,
    `non_numeric_operand: subtract` named neither operand and the identical
    failing expression came back twice.
    """
    outcome = project_facts(
        [{"key": "catalog_year", "from": "call_1", "path": "data.catalogyear"}], _TOOL_RESULTS, _HANDLES
    )

    assert outcome.facts == {}
    assert len(outcome.errors) == 1
    error = outcome.errors[0]
    assert "data.catalogyear" in error
    assert "call_1" in error
    assert "data.catalogYear" in error, "the repair message must show the path that would have worked"


def test_an_unknown_handle_lists_the_recorded_calls():
    outcome = project_facts(
        [{"key": "catalog_year", "from": "call_9", "path": "data.catalogYear"}], _TOOL_RESULTS, _HANDLES
    )

    assert outcome.facts == {}
    assert "call_1" in outcome.errors[0] and "call_2" in outcome.errors[0]


def test_a_legitimately_empty_value_is_projected_not_treated_as_missing():
    """`semester_plan` returning `[]` is the answer, not the absence of one --
    live, an empty plan was the whole basis of the `presupposition_conflict`
    turn. `resolve_path` reports found/not-found separately so an empty list, a
    zero, or a null projects cleanly.
    """
    envelope = {"ok": True, "data": {"plans": [], "total": 0, "note": None}, "certainty": None}
    tool_results = {"get_entity:{}": envelope}
    handles = build_call_handles(tool_results)

    outcome = project_facts(
        [
            {"key": "plans", "from": "call_1", "path": "data.plans"},
            {"key": "total", "from": "call_1", "path": "data.total"},
            {"key": "note", "from": "call_1", "path": "data.note"},
        ],
        tool_results,
        handles,
    )

    assert outcome.errors == []
    assert outcome.facts["plans"]["value"] == []
    assert outcome.facts["total"]["value"] == 0
    assert outcome.facts["note"]["value"] is None


def test_every_bad_selector_is_reported_never_silently_skipped():
    """Dropping data without saying so is what let a step publish `facts: {}` at
    confidence 0.9 for an entire live run."""
    outcome = project_facts(
        [
            {"key": "good", "from": "call_1", "path": "data.catalogYear"},
            {"key": "bad_path", "from": "call_1", "path": "data.nope"},
            {"key": "bad_handle", "from": "call_7", "path": "data.catalogYear"},
            {"from": "call_1", "path": "data.catalogYear"},
            "not-an-object",
        ],
        _TOOL_RESULTS,
        _HANDLES,
    )

    assert set(outcome.facts) == {"good"}
    assert len(outcome.errors) == 4


def test_handles_are_assigned_in_call_order():
    assert _HANDLES == {"call_1": _PROFILE_KEY, "call_2": _COURSES_KEY}


def test_resolve_path_rejects_a_non_dict_intermediate():
    assert resolve_path({"data": {"catalogYear": 2025}}, "data.catalogYear") == (2025, True)
    assert resolve_path({"data": {"catalogYear": 2025}}, "data.catalogYear.nested") == (None, False)
    assert resolve_path({"data": None}, "data.catalogYear") == (None, False)
    assert resolve_path({"data": {}}, "") == (None, False)


def test_available_paths_walks_nested_objects_but_stays_bounded():
    paths = available_paths(_PROFILE_ENVELOPE)

    assert "data.programSlug" in paths
    assert "data.academicPath.trackSlug" in paths
    assert all(path.count(".") <= 3 for path in paths)


def test_describe_call_renders_a_citation_and_survives_a_malformed_key():
    assert describe_call('get_entity:{"entity_type": "student_profile"}') == "get_entity(entity_type=student_profile)"
    assert describe_call("get_current_semester:{}") == "get_current_semester"
    assert describe_call("get_current_semester") == "get_current_semester"
    assert describe_call("weird:not-json") == "weird"


def test_a_non_list_facts_payload_is_an_error_not_a_crash():
    outcome = project_facts({"key": "x"}, _TOOL_RESULTS, _HANDLES)

    assert outcome.facts == {}
    assert "must be a list" in outcome.errors[0]
