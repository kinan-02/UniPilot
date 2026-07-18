"""Unit tests for `check_eligibility` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data facts verified directly before writing assertions, not assumed:
- "00440148" requires {"00440105", "00440140"} (reused throughout this
  suite).
- "00140008" has zero prerequisites, reliable Winter(1)/Spring(2), never
  Summer(3) (reused from test_search_over_state.py).
"""

from __future__ import annotations

from bson import ObjectId

from app.agent_core.tools.composites.check_eligibility import (
    CheckEligibilityInput,
    run_check_eligibility,
)
from app.db.mongo import set_test_database


async def test_empty_course_id_fails_closed():
    result = await run_check_eligibility(CheckEligibilityInput(course_id="  "))
    assert result.ok is False
    assert "course_id_required" in result.error


async def test_unparseable_target_semester_fails_closed():
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", target_semester="not-a-semester")
    )
    assert result.ok is False
    assert "unparseable_target_semester" in result.error


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148"))
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148"))
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


async def test_unknown_course_fails_closed(use_real_academic_engine):
    result = await run_check_eligibility(CheckEligibilityInput(course_id="99999999"))
    assert result.ok is False
    assert "entity_not_found: 99999999" in result.error


async def test_eligible_when_prerequisites_completed(use_real_academic_engine):
    state = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "completed"},
            {"courseNumber": "00440140", "status": "completed"},
        ]
    }
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))
    assert result.ok is True
    assert result.data["eligible"] is True
    assert result.data["missingPrerequisites"] == []
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_not_eligible_when_prerequisites_missing(use_real_academic_engine):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", state={"completedCourses": []})
    )
    assert result.ok is True
    assert result.data["eligible"] is False
    assert set(result.data["missingPrerequisites"]) == {"00440105", "00440140"}


async def test_output_names_the_held_prerequisites(use_real_academic_engine):
    """A clean pass must give the answer something to CITE: the engine reports
    only what is MISSING, so the tool also names the prerequisites the student
    HOLDS (else an 'eligible' answer can name no basis at all)."""
    state = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "completed"},
            {"courseNumber": "00440140", "status": "completed"},
        ]
    }
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))
    assert result.ok is True
    assert result.data["eligible"] is True
    assert result.data["missingPrerequisites"] == []
    assert set(result.data["prerequisiteCourseIds"]) >= {"00440105", "00440140"}
    assert set(result.data["prerequisitesHeld"]) == {"00440105", "00440140"}


async def test_held_prerequisites_are_only_the_ones_actually_completed(use_real_academic_engine):
    result = await run_check_eligibility(
        CheckEligibilityInput(
            course_id="00440148",
            state={"completedCourses": [{"courseNumber": "00440105", "status": "completed"}]},
        )
    )
    assert result.ok is True
    assert result.data["prerequisitesHeld"] == ["00440105"]  # the one held; 00440140 is missing


async def test_eligible_with_the_shape_get_entity_actually_returns(use_real_academic_engine):
    """The regression a green test suite could not see.

    Every other fixture here hand-writes `status: "completed"` -- a key NO
    producer in the codebase emits. `get_entity` returns completed courses
    straight from the record ({courseNumber, creditsEarned, grade, semesterCode,
    source, attempt}) with no `status` at all; the only writer of that field is
    `mutate_state`, stamping "failed". So the old `status == "completed"`
    predicate matched nothing real, and this tool answered `eligible: false` for
    every course with prerequisites, for every student -- while its tests stayed
    green, because they fed it the invented shape it was written against.

    Measured live (2026-07-16): a student who passed 00940224 with grade 85 was
    told they were ineligible for 00960211, whose prerequisite is "00940224 OR
    00940226" -- `missingPrerequisites: ["00940224"]`, the course sitting right
    there in the payload it had been handed.

    This fixture is the real shape. It is the one that would have caught it.
    """
    state = {
        "completedCourses": [
            {
                "courseNumber": "00440105",
                "creditsEarned": 3.5,
                "grade": 85.0,
                "semesterCode": "2025-1",
                "source": "manual",
                "attempt": 1,
            },
            {
                "courseNumber": "00440140",
                "creditsEarned": 4.0,
                "grade": 88.0,
                "semesterCode": "2024-1",
                "source": "manual",
                "attempt": 1,
            },
        ]
    }

    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))

    assert result.ok is True
    assert result.data["eligible"] is True, "a completed course carrying no `status` key must still count"
    assert result.data["missingPrerequisites"] == []


async def test_eligible_with_the_snake_case_key_the_agent_actually_sends(use_real_academic_engine):
    """The half of the bug that a camelCase fixture hides.

    `get_entity` emits `completedCourses`, so it is tempting to test that and
    stop. But this tool's `state` never arrives straight from `get_entity`: a
    specialist re-types the facts into its own output, and a later one re-types
    them again into this argument. Transcription does not preserve key case.

    Measured live (2026-07-16) the agent sent `completed_courses`. With the
    status predicate already fixed and a camelCase fixture passing, the tool
    STILL answered `eligible: false` / `missingPrerequisites: ["00940224"]` on a
    real turn -- because the key it looked up was not the key it was sent.

    This fixture is copied from that payload verbatim, snake_case and all.
    """
    state = {
        "student_profile": {"degreeId": "6a477d511f64e5fd20129b44"},
        "completed_courses": [
            {
                "attempt": 1,
                "courseNumber": "00440105",
                "creditsEarned": 3.5,
                "grade": 85.0,
                "semesterCode": "2025-1",
                "source": "manual",
            },
            {
                "attempt": 1,
                "courseNumber": "00440140",
                "creditsEarned": 4.0,
                "grade": 88.0,
                "semesterCode": "2024-1",
                "source": "manual",
            },
        ],
    }

    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))

    assert result.ok is True
    assert result.data["eligible"] is True, "the key the agent sends must be the key we read"
    assert result.data["missingPrerequisites"] == []


async def test_student_id_lets_the_tool_read_the_record_itself(
    use_real_academic_engine, fake_database_factory
):
    """The point of `student_id`: no completed-course record crosses a model.

    Passing `state` meant a model hand-copied the record out of our database,
    through two rounds of transcription, back into our own code -- measured live
    (2026-07-16) at 3,267 chars (~11s), and the relay snake_cased the key so the
    lookup missed and the answer was wrong. One id in, record read at source,
    and that whole class of failure has nowhere to occur.
    """
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440105", "grade": 85},
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440140", "grade": 88},
                ]
            }
        )
    )

    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", student_id=user_id)
    )

    assert result.ok is True, result.error
    assert result.data["eligible"] is True
    assert result.data["missingPrerequisites"] == []


async def test_student_id_with_a_missing_prerequisite_is_still_not_eligible(
    use_real_academic_engine, fake_database_factory
):
    """Reading the record ourselves must not turn into rubber-stamping it."""
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440105", "grade": 85}
                ]
            }
        )
    )

    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", student_id=user_id)
    )

    assert result.ok is True, result.error
    assert result.data["eligible"] is False
    assert result.data["missingPrerequisites"] == ["00440140"]


async def test_an_explicit_state_overrides_student_id_for_what_ifs(
    use_real_academic_engine, fake_database_factory
):
    """The what-if path must survive. `mutate_state` marks a course failed and
    the caller passes that altered state -- re-reading the real record would
    quietly undo the simulation and answer a question nobody asked."""
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440105", "grade": 85},
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440140", "grade": 88},
                ]
            }
        )
    )
    simulated = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "failed"},
            {"courseNumber": "00440140"},
        ]
    }

    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", student_id=user_id, state=simulated)
    )

    assert result.ok is True, result.error
    assert result.data["eligible"] is False, "the simulated failure must win over the real record"
    assert result.data["missingPrerequisites"] == ["00440105"]


async def test_failed_course_does_not_count_as_satisfying_prerequisite(use_real_academic_engine):
    state = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "failed"},
            {"courseNumber": "00440140", "status": "completed"},
        ]
    }
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))
    assert result.ok is True
    assert result.data["eligible"] is False
    assert result.data["missingPrerequisites"] == ["00440105"]


async def test_no_target_semester_leaves_offering_fields_null(use_real_academic_engine):
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00140008"))
    assert result.ok is True
    assert result.data["offeringPattern"] is None
    assert result.data["schedulable"] is None
    assert result.warnings == []


async def test_target_semester_excluded_by_offering_pattern(use_real_academic_data):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-3")
    )
    assert result.ok is True
    assert result.data["eligible"] is True
    assert result.data["offeringPattern"]["termPatterns"]["3"]["label"] == "never"
    assert result.data["schedulable"] is False


async def test_target_semester_allowed_by_offering_pattern(use_real_academic_data):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-1")
    )
    assert result.ok is True
    assert result.data["schedulable"] is True


async def test_offering_fields_carry_a_predicted_basis(use_real_academic_data):
    """§4.2: schedulable/offeringPattern depend on the offering PREDICTION, so they
    carry their own predicted_pattern basis -- not the envelope's official_record."""
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-1")
    )
    assert result.ok is True
    assert result.certainty.basis == "official_record"  # the envelope default (eligibility verdict)
    assert result.field_certainty["schedulable"].basis == "predicted_pattern"
    assert result.field_certainty["offeringPattern"].basis == "predicted_pattern"


async def test_no_target_semester_leaves_field_certainty_empty(use_real_academic_engine):
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00140008"))
    assert result.ok is True
    assert result.field_certainty == {}  # no offering prediction involved


async def test_offering_pattern_unavailable_degrades_gracefully(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.check_eligibility as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_offering(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    monkeypatch.setattr(module, "run_extract_temporal_pattern", _fake_offering)

    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-1")
    )
    assert result.ok is True
    assert result.data["offeringPattern"] is None
    assert result.data["schedulable"] is None
    assert "offering_pattern_unavailable" in result.warnings
