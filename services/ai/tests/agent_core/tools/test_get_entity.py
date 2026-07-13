"""Unit tests for `get_entity` (docs/agent/AGENT_VISION.md §5, primitive 1).

Course/track/program/minor/faculty/wiki_page cases run against the real wiki
+ semester-catalog data (`use_real_academic_engine`) using ids verified to
exist in that data:
- course "00440148" (has both a catalog entry and a wiki page -- reused from
  `tests/test_academic_graph_engine.py`'s own eligibility/syllabus cases)
- track "track-biomedical-engineering" (entities/tracks/)
- program "program-alonim" (entities/programs/, `program-` prefix)
- minor "minor-economics" (entities/programs/, `minor-` prefix)
- faculty "faculty-chemistry" (entities/faculties/ -- plural directory)
- generic wiki_page "student-rights" (a concept-ish page, not course/track/
  program/minor/faculty)

Mongo-backed cases (`student_profile`/`completed_courses`/`semester_plan`)
use `FakeDatabase`, never a real database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from app.agent_core.tools.primitives.get_entity import (
    GetEntityInput,
    _classify_wiki_path,
    _sanitize_value,
    run_get_entity,
)
from app.db.mongo import set_test_database


async def test_unknown_entity_type_fails_closed():
    result = await run_get_entity(GetEntityInput(entity_type="does_not_exist", entity_id="x"))
    assert result.ok is False
    assert result.data is None
    assert "unknown_entity_type" in result.error


async def test_empty_entity_id_fails_closed():
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="   "))
    assert result.ok is False
    assert "entity_id_required" in result.error


async def test_course_entity_merges_catalog_and_wiki(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="00440148"))
    assert result.ok is True
    assert result.data["entityType"] == "course"
    assert result.data["entityId"] == "00440148"
    assert result.data["name"]
    assert result.data["wikiSlug"] is not None
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_unknown_course_fails_closed(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="99999999"))
    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_course_entity_resolves_a_completed_courses_object_id(
    use_real_academic_engine, fake_database_factory
):
    """A live-eval run found the model reliably passing a completed_courses
    record's own `courseId` (a Mongo _id reference, not a course code) as
    entity_id for entity_type="course" -- this must still resolve rather
    than fail closed."""
    course_object_id = ObjectId()
    set_test_database(
        fake_database_factory({"courses": [{"_id": course_object_id, "courseNumber": "00440148"}]})
    )

    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id=str(course_object_id)))

    assert result.ok is True
    assert result.data["entityId"] == "00440148"


async def test_course_entity_with_unresolvable_object_id_fails_closed(
    use_real_academic_engine, fake_database_factory
):
    set_test_database(fake_database_factory({"courses": []}))

    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id=str(ObjectId())))

    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_track_entity(use_real_academic_engine):
    result = await run_get_entity(
        GetEntityInput(entity_type="track", entity_id="track-biomedical-engineering")
    )
    assert result.ok is True
    assert result.data["slug"] == "track-biomedical-engineering"
    assert result.data["path"].startswith("entities/tracks/")
    assert result.certainty.basis == "wiki_derived"


async def test_program_entity(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="program", entity_id="program-alonim"))
    assert result.ok is True
    assert result.data["slug"] == "program-alonim"


async def test_program_entity_resolves_a_student_profile_degree_id_object_id(
    use_real_academic_engine, fake_database_factory
):
    """A live-eval run found the model reliably passing a student_profile's
    `degreeId` (a Mongo _id reference into degree_programs, not a wiki slug)
    as entity_id for entity_type="program" -- this must still resolve."""
    degree_object_id = ObjectId()
    set_test_database(
        fake_database_factory(
            {"degree_programs": [{"_id": degree_object_id, "metadata": {"wikiPage": "program-alonim"}}]}
        )
    )

    result = await run_get_entity(GetEntityInput(entity_type="program", entity_id=str(degree_object_id)))

    assert result.ok is True
    assert result.data["slug"] == "program-alonim"


async def test_program_entity_with_unresolvable_degree_id_fails_closed(
    use_real_academic_engine, fake_database_factory
):
    set_test_database(fake_database_factory({"degree_programs": []}))

    result = await run_get_entity(GetEntityInput(entity_type="program", entity_id=str(ObjectId())))

    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_wiki_page_entity_type_never_attempts_object_id_resolution(
    use_real_academic_engine, fake_database_factory
):
    """entity_type="wiki_page" has no database-id form to confuse with its
    own entity_id -- an ObjectId-shaped slug should just fail closed as an
    unknown slug, never trigger a degree_programs lookup."""
    set_test_database(fake_database_factory({"degree_programs": []}))
    object_id_shaped_slug = str(ObjectId())

    result = await run_get_entity(GetEntityInput(entity_type="wiki_page", entity_id=object_id_shaped_slug))

    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_minor_entity(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="minor", entity_id="minor-economics"))
    assert result.ok is True
    assert result.data["slug"] == "minor-economics"


async def test_faculty_entity(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="faculty", entity_id="faculty-chemistry"))
    assert result.ok is True
    assert result.data["slug"] == "faculty-chemistry"


async def test_generic_wiki_page_entity(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="wiki_page", entity_id="student-rights"))
    assert result.ok is True
    assert result.data["slug"] == "student-rights"


async def test_requesting_track_entity_type_for_a_program_slug_fails_closed(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="track", entity_id="program-alonim"))
    assert result.ok is False
    assert "entity_type_mismatch" in result.error


async def test_unknown_wiki_slug_fails_closed(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="wiki_page", entity_id="does-not-exist-slug"))
    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_wrong_order_slug_resolves_via_the_alias_index(use_real_academic_engine):
    # The model guessed 'robotics-minor'; the real page is 'minor-robotics'
    # (which lists 'robotics minor' among its frontmatter aliases). On the
    # exact-slug miss, get_entity resolves it via the alias index rather than
    # dead-ending, so the retrieval agent doesn't burn a round on a wrong guess.
    result = await run_get_entity(GetEntityInput(entity_type="wiki_page", entity_id="robotics-minor"))
    assert result.ok is True
    assert result.data["slug"] == "minor-robotics"


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="00440148"))
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_student_profile_found(fake_database_factory):
    user_id = str(ObjectId())
    profile = {"_id": ObjectId(), "userId": ObjectId(user_id), "degreeProgram": "CS"}
    set_test_database(fake_database_factory({"student_profiles": [profile]}))

    result = await run_get_entity(GetEntityInput(entity_type="student_profile", entity_id=user_id))
    assert result.ok is True
    assert result.data["degreeProgram"] == "CS"
    assert isinstance(result.data["_id"], str)
    assert isinstance(result.data["userId"], str)
    assert result.certainty.basis == "official_record"


async def test_student_profile_not_found(fake_database_factory):
    set_test_database(fake_database_factory({}))
    result = await run_get_entity(
        GetEntityInput(entity_type="student_profile", entity_id=str(ObjectId()))
    )
    assert result.ok is False
    assert "entity_not_found" in result.error


async def test_completed_courses_returns_empty_list_not_a_failure(fake_database_factory):
    set_test_database(fake_database_factory({}))
    result = await run_get_entity(
        GetEntityInput(entity_type="completed_courses", entity_id=str(ObjectId()))
    )
    assert result.ok is True
    assert result.data["completedCourses"] == []


async def test_completed_courses_returns_sanitized_docs(fake_database_factory):
    user_id = str(ObjectId())
    doc = {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00440148", "grade": 90}
    set_test_database(fake_database_factory({"completed_courses": [doc]}))

    result = await run_get_entity(GetEntityInput(entity_type="completed_courses", entity_id=user_id))
    assert result.ok is True
    assert len(result.data["completedCourses"]) == 1
    assert result.data["completedCourses"][0]["courseNumber"] == "00440148"
    assert isinstance(result.data["completedCourses"][0]["_id"], str)


async def test_semester_plan_returns_plans_and_total(fake_database_factory):
    user_id = str(ObjectId())
    plan = {"_id": ObjectId(), "userId": ObjectId(user_id), "semesterCode": "2025-2"}
    set_test_database(fake_database_factory({"semester_plans": [plan]}))

    result = await run_get_entity(GetEntityInput(entity_type="semester_plan", entity_id=user_id))
    assert result.ok is True
    assert result.data["total"] == 1
    assert result.data["plans"][0]["semesterCode"] == "2025-2"


# -- _sanitize_value: direct unit coverage for every branch -----------------


def test_sanitize_value_converts_datetime():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _sanitize_value(now) == now.isoformat()


def test_sanitize_value_recurses_into_nested_dict():
    value = {"outer": {"id": ObjectId()}}
    sanitized = _sanitize_value(value)
    assert isinstance(sanitized["outer"]["id"], str)


def test_sanitize_value_recurses_into_list():
    ids = [ObjectId(), ObjectId()]
    sanitized = _sanitize_value(ids)
    assert all(isinstance(item, str) for item in sanitized)


def test_sanitize_value_passes_through_plain_values():
    assert _sanitize_value("plain") == "plain"
    assert _sanitize_value(42) == 42
    assert _sanitize_value(None) is None


# -- _classify_wiki_path: direct unit coverage for every branch -------------
# (the "course" and program-without-prefix branches have no real slug in the
# actual wiki data to exercise them through `get_entity` end-to-end -- every
# real file under entities/programs/ starts with `minor-`/`program-`,
# verified directly -- so these are covered as a pure-function unit test.)


def test_classify_wiki_path_course():
    assert _classify_wiki_path("courses/010-math/00124507-x.md", "00124507-x") == "course"


def test_classify_wiki_path_program_directory_without_known_prefix():
    assert _classify_wiki_path("entities/programs/something-else.md", "something-else") == "wiki_page"


# -- get_entity: entity_type_mismatch against a course-classified slug ------


async def test_requesting_track_entity_type_for_a_course_wiki_slug_fails_closed(use_real_academic_engine):
    """Exercises `_classify_wiki_path`'s `courses/` branch through the real
    tool path -- 00440148's wiki slug (verified directly against
    `engine.slug_to_course_code`) is a real "courses/" page; requesting
    entity_type="track" against it must mismatch, not silently succeed."""
    result = await run_get_entity(
        GetEntityInput(entity_type="track", entity_id="00440148-waves-distributed-systems")
    )
    assert result.ok is False
    assert "entity_type_mismatch: requested track" in result.error
    assert "is course" in result.error


# -- get_entity: course present in only one of {catalog, wiki} --------------
# Verified directly against the real engine before writing these (not
# guessed): 02080353 is in the active semester catalog with no matching
# wiki page; 02360861 has a wiki page but is absent from this semester's
# catalog JSON.


async def test_course_in_catalog_only_warns_missing_wiki_page(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="02080353"))
    assert result.ok is True
    assert "wikiSlug" not in result.data
    assert result.certainty.basis == "official_record"
    assert result.warnings == ["no_wiki_page_found_for_course"]


async def test_course_in_wiki_only_warns_missing_catalog_entry(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="02360861"))
    assert result.ok is True
    assert "name" not in result.data
    assert "wikiSlug" in result.data
    assert result.certainty.basis == "wiki_derived"
    assert result.warnings == ["course_not_in_active_semester_catalog"]


async def test_course_in_both_catalog_and_wiki_has_no_warnings(use_real_academic_engine):
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="00440148"))
    assert result.ok is True
    assert result.warnings == []


# -- get_entity: exception paths, never propagate -----------------------


async def test_academic_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_get_entity(GetEntityInput(entity_type="course", entity_id="00440148"))
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


async def test_mongo_lookup_failure_fails_closed(monkeypatch):
    import app.agent_core.tools.primitives.get_entity as get_entity_module

    async def _raise():
        raise RuntimeError("connection lost")

    monkeypatch.setattr(get_entity_module, "get_database", _raise)
    result = await run_get_entity(
        GetEntityInput(entity_type="student_profile", entity_id=str(ObjectId()))
    )
    assert result.ok is False
    assert "mongo_lookup_failed" in result.error
