"""Unit tests for catalog repository (read-only)."""

import pytest
from bson import ObjectId

from app.config import get_settings
from app.repositories import catalog_repository
from app.repositories.catalog_repository import (
    _advisory_record_rank,
    _build_course_search_filter,
    _sanitize_metadata,
    course_summary_from_document,
)
from app.catalog.excluded_courses import EXCLUDED_COURSE, PRODUCTION_EXCLUDED_COURSE_NUMBERS
from tests.fixtures.catalog_production_fixtures import (
    KNOWN_COURSE,
    SEEDED_COURSE_COUNT,
    seed_catalog_production_fixtures,
)


# ---------------------------------------------------------------------------
# Pure helpers — no DB needed
# ---------------------------------------------------------------------------

def test_advisory_record_rank_advisory_requirement_group():
    doc = {"recordType": "advisory_requirement_group", "courseReferences": [1, 2]}
    assert _advisory_record_rank(doc) == (2, 2)


def test_advisory_record_rank_catalog_rule():
    doc = {"recordType": "catalog_rule", "courseReferences": [1]}
    assert _advisory_record_rank(doc) == (1, 1)


def test_advisory_record_rank_unknown_type():
    doc = {"recordType": "other", "courseReferences": []}
    assert _advisory_record_rank(doc) == (0, 0)


def test_dedupe_catalog_rules_skips_documents_with_no_group_id():
    from app.repositories.catalog_repository import _dedupe_catalog_rules_by_group_id

    docs = [
        {"requirementGroupId": "group1", "recordType": "catalog_rule", "courseReferences": []},
        {"requirementGroupId": "", "recordType": "catalog_rule", "courseReferences": []},  # skipped
        {"recordType": "catalog_rule", "courseReferences": []},  # also skipped - no group_id
    ]
    result = _dedupe_catalog_rules_by_group_id(docs)
    assert len(result) == 1
    assert result[0]["requirementGroupId"] == "group1"


def test_sanitize_metadata_returns_default_when_none():
    result = _sanitize_metadata(None)
    assert result == {"degreeRequirementsInferred": False}


def test_sanitize_metadata_overrides_inferred_flag():
    result = _sanitize_metadata({"degreeRequirementsInferred": True, "extra": "data"})
    assert result["degreeRequirementsInferred"] is False
    assert result["extra"] == "data"


def test_build_course_search_filter_base_only_returns_single_filter():
    filt = _build_course_search_filter(
        q=None,
        faculty=None,
        course_number=None,
    )
    assert "$and" in filt
    assert {"courseNumber": {"$nin": sorted(PRODUCTION_EXCLUDED_COURSE_NUMBERS)}} in filt["$and"]


def test_build_course_search_filter_with_course_numbers_min_max():
    filt = _build_course_search_filter(
        q=None,
        faculty=None,
        course_number=None,
        course_numbers=["00940101", "00940201"],
        min_credits=2.0,
        max_credits=5.0,
    )
    assert "$and" in filt
    conditions = filt["$and"]
    has_course_numbers = any("courseNumber" in c and "$in" in c.get("courseNumber", {}) for c in conditions)
    has_min = any("credits" in c and "$gte" in c.get("credits", {}) for c in conditions)
    has_max = any("credits" in c and "$lte" in c.get("credits", {}) for c in conditions)
    assert has_course_numbers
    assert has_min
    assert has_max


def test_build_course_search_filter_with_faculty():
    filt = _build_course_search_filter(
        q=None,
        faculty="Computer Science",
        course_number=None,
    )
    assert "$and" in filt
    conditions = filt["$and"]
    has_faculty = any("faculty" in c for c in conditions)
    assert has_faculty


def test_course_summary_from_document_returns_none_for_falsy_doc():
    assert course_summary_from_document(None) is None
    assert course_summary_from_document({}) is None


def test_course_summary_from_document_returns_none_when_number_and_title_both_none():
    doc = {"someField": "x"}  # no courseNumber, no number, no title, no titleHebrew
    assert course_summary_from_document(doc) is None


def test_course_summary_from_document_returns_summary_with_number_and_title():
    doc = {"courseNumber": "00940101", "title": "Algebra"}
    result = course_summary_from_document(doc)
    assert result is not None
    assert result["number"] == "00940101"
    assert result["title"] == "Algebra"


# ---------------------------------------------------------------------------
# DB-backed tests for uncovered branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_course_numbers_fallback_when_no_exact_match(mongo_database):
    """When no exact academic_year match, falls back to same semesterCode."""
    settings = get_settings()
    await mongo_database[settings.course_offerings_collection].insert_one({
        "courseNumber": "00940101",
        "status": "published",
        "academicYear": 2020,
        "semesterCode": 201,
    })
    numbers = await catalog_repository.list_course_numbers_with_semester_offerings(
        mongo_database,
        academic_year=2025,  # no exact match
        semester_code=201,
        settings=settings,
    )
    assert "00940101" in numbers


@pytest.mark.asyncio
async def test_list_offerings_for_courses_in_semester_empty_course_numbers(mongo_database):
    result = await catalog_repository.list_offerings_for_courses_in_semester(
        mongo_database,
        [],
        academic_year=2025,
        semester_code=201,
    )
    assert result == {}


@pytest.mark.asyncio
async def test_list_offerings_for_courses_in_semester_no_best_when_offerings_empty(mongo_database):
    """When pick_best_offering returns None, course should not appear in summaries."""
    settings = get_settings()
    await mongo_database[settings.course_offerings_collection].insert_one({
        "courseNumber": "00940199",
        "status": "published",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [],
    })
    from unittest.mock import patch
    with patch(
        "app.planning.semester_codes.pick_best_offering",
        return_value=None,
    ):
        result = await catalog_repository.list_offerings_for_courses_in_semester(
            mongo_database,
            ["00940199"],
            academic_year=2025,
            semester_code=201,
            settings=settings,
        )
    assert result == {}


@pytest.mark.asyncio
async def test_list_courses_returns_empty_when_no_semester_offerings(mongo_database):
    """academic_year + semester_code with no matching offerings returns empty list."""
    settings = get_settings()
    result_items, total = await catalog_repository.list_courses(
        mongo_database,
        academic_year=9999,
        semester_code=201,
        settings=settings,
    )
    assert result_items == []
    assert total == 0


@pytest.mark.asyncio
async def test_find_course_by_number_calls_get_settings_when_none(mongo_database, monkeypatch):
    """When settings=None, find_course_by_number calls get_settings()."""
    settings = get_settings()
    # Seed a course
    await mongo_database[settings.courses_collection].insert_one({
        "courseNumber": "00940777",
        "status": "published",
    })
    # Ensure settings=None path is exercised
    result = await catalog_repository.find_course_by_number(
        mongo_database,
        "00940777",
        settings=None,  # triggers get_settings()
    )
    assert result is not None


@pytest.mark.asyncio
async def test_find_course_by_id_returns_none_for_invalid_id(mongo_database):
    result = await catalog_repository.find_course_by_id(mongo_database, "not-an-object-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_offerings_grouped_returns_empty_for_empty_course_numbers(mongo_database):
    result = await catalog_repository.list_offerings_grouped_for_courses(
        mongo_database,
        [],
    )
    assert result == {}


@pytest.mark.asyncio
async def test_list_offerings_grouped_returns_empty_for_all_falsy_course_numbers(mongo_database):
    """course_numbers with only empty strings produces empty unique_numbers → {}."""
    result = await catalog_repository.list_offerings_grouped_for_courses(
        mongo_database,
        ["", None],  # type: ignore[list-item]
    )
    assert result == {}


@pytest.mark.asyncio
async def test_find_courses_by_numbers_returns_empty_for_empty_list(mongo_database):
    result = await catalog_repository.find_courses_by_numbers(mongo_database, [])
    assert result == []


@pytest.mark.asyncio
async def test_find_courses_by_numbers_returns_empty_for_all_falsy(mongo_database):
    result = await catalog_repository.find_courses_by_numbers(mongo_database, ["", None])  # type: ignore[list-item]
    assert result == []


@pytest.mark.asyncio
async def test_find_degree_program_by_id_returns_none_for_invalid_id(mongo_database):
    result = await catalog_repository.find_degree_program_by_id(mongo_database, "not-an-object-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_courses_by_number_prefixes_returns_empty_for_empty_prefixes(mongo_database):
    result = await catalog_repository.list_courses_by_number_prefixes(mongo_database, [])
    assert result == []


@pytest.mark.asyncio
async def test_find_courses_by_ids_skips_invalid_object_ids(mongo_database):
    """Invalid ObjectId strings should be silently skipped."""
    settings = get_settings()
    valid_id = ObjectId()
    await mongo_database[settings.courses_collection].insert_one({
        "_id": valid_id,
        "courseNumber": "00940888",
        "status": "published",
    })
    result = await catalog_repository.find_courses_by_ids(
        mongo_database,
        ["not-an-oid", str(valid_id), "also-invalid"],
    )
    ids = [str(doc["_id"]) for doc in result]
    assert str(valid_id) in ids


@pytest.mark.asyncio
async def test_find_degree_program_does_not_require_course_number(mongo_database):
    settings = get_settings()
    inserted = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "programCode": "009216-1-000",
            "name": "Test Program",
            "status": "published",
        }
    )
    program = await catalog_repository.find_degree_program_by_id(
        mongo_database,
        str(inserted.inserted_id),
    )
    assert program is not None
    assert program["programCode"] == "009216-1-000"


@pytest.mark.asyncio
async def test_repository_list_and_get_course(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)

    items, total = await catalog_repository.list_courses(mongo_database, limit=10, offset=0)
    assert total == SEEDED_COURSE_COUNT
    assert any(item["courseNumber"] == KNOWN_COURSE for item in items)

    course = await catalog_repository.get_course_by_number(mongo_database, KNOWN_COURSE)
    assert course is not None
    assert course["courseNumber"] == KNOWN_COURSE
    assert "productionKey" not in course


@pytest.mark.asyncio
async def test_repository_hides_production_excluded_course(mongo_database):
    settings = get_settings()
    await mongo_database[settings.courses_collection].insert_one(
        {
            "courseNumber": EXCLUDED_COURSE,
            "title": "Excluded course",
            "status": "published",
        }
    )

    assert await catalog_repository.get_course_by_number(mongo_database, EXCLUDED_COURSE) is None
    assert await catalog_repository.find_course_by_number(mongo_database, EXCLUDED_COURSE) is None

    items, total = await catalog_repository.list_courses(mongo_database, limit=50, offset=0)
    assert all(item["courseNumber"] != EXCLUDED_COURSE for item in items)


@pytest.mark.asyncio
async def test_repository_prefers_advisory_requirement_group_over_legacy_catalog_rule(mongo_database):
    settings = get_settings()
    group_id = "009216-1-000:semester-1-matrix"
    await mongo_database[settings.catalog_rules_collection].insert_many(
        [
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "recordType": "catalog_rule",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [{"courseNumber": KNOWN_COURSE, "titleHint": "legacy"}],
                "status": "published",
            },
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "recordType": "advisory_requirement_group",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [],
                "status": "published",
            },
        ]
    )

    rules = await catalog_repository.list_advisory_rules_for_program(mongo_database, "009216-1-000")
    semester_one = [rule for rule in rules if rule["requirementGroupId"] == group_id]
    assert len(semester_one) == 1


@pytest.mark.asyncio
async def test_repository_dedupes_duplicate_advisory_rules(mongo_database):
    settings = get_settings()
    group_id = "009216-1-000:semester-1-matrix"
    await mongo_database[settings.catalog_rules_collection].insert_many(
        [
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [],
                "status": "published",
            },
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [{"courseNumber": KNOWN_COURSE, "titleHint": "מתמטיקה דיסקרטית"}],
                "status": "published",
            },
        ]
    )

    rules = await catalog_repository.list_advisory_rules_for_program(mongo_database, "009216-1-000")
    semester_one = [rule for rule in rules if rule["requirementGroupId"] == group_id]
    assert len(semester_one) == 1
    assert semester_one[0]["courseReferences"][0]["courseNumber"] == KNOWN_COURSE

    matrices = await catalog_repository.list_semester_matrix_rules_for_program(
        mongo_database, "009216-1-000"
    )
    assert len(matrices) == 1
    assert matrices[0]["courseReferences"][0]["courseNumber"] == KNOWN_COURSE


@pytest.mark.asyncio
async def test_repository_never_writes_during_reads(mongo_database, monkeypatch):
    await seed_catalog_production_fixtures(mongo_database)

    async def fail_write(*_args, **_kwargs):
        raise AssertionError("catalog repository must not write during GET flows")

    monkeypatch.setattr(mongo_database.courses, "insert_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "update_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "replace_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "delete_one", fail_write)

    await catalog_repository.list_courses(mongo_database)
    await catalog_repository.get_course_by_number(mongo_database, KNOWN_COURSE)
    await catalog_repository.list_degree_programs(mongo_database)


@pytest.mark.asyncio
async def test_list_best_offerings_for_courses_batch(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)

    best = await catalog_repository.list_best_offerings_for_courses(
        mongo_database,
        [KNOWN_COURSE],
        academic_year=2025,
        semester_code=201,
    )

    assert KNOWN_COURSE in best
    assert best[KNOWN_COURSE]["courseNumber"] == KNOWN_COURSE


@pytest.mark.asyncio
async def test_to_public_degree_program_maps_name_hebrew_from_metadata(mongo_database):
    settings = get_settings()
    program_id = ObjectId()
    await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "_id": program_id,
            "programCode": "009216-1-000",
            "status": "published",
            "metadata": {"nameHe": "הנדסת נתונים ומידע", "facultyId": "faculty-dds"},
        }
    )
    programs = await catalog_repository.list_degree_programs(
        mongo_database,
        faculty_id="faculty-dds",
        settings=settings,
    )
    match = next((program for program in programs if program.get("id") == str(program_id)), None)
    assert match is not None
    assert match["nameHebrew"] == "הנדסת נתונים ומידע"


@pytest.mark.asyncio
async def test_list_degree_programs_filters_by_study_level(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    settings = get_settings()
    await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "programCode": "grad-test",
            "status": "published",
            "metadata": {"programKind": "graduate_program"},
        }
    )
    graduate_programs = await catalog_repository.list_degree_programs(
        mongo_database,
        study_level="MSc",
        settings=settings,
    )
    assert any(program.get("programCode") == "grad-test" for program in graduate_programs)
    bsc_programs = await catalog_repository.list_degree_programs(
        mongo_database,
        study_level="BSc",
        settings=settings,
    )
    assert all(
        (program.get("metadata") or {}).get("programKind") != "graduate_program"
        for program in bsc_programs
    )
    await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "programCode": "027027-1-000",
            "status": "published",
            "metadata": {"wikiPage": "track-medicine-md"},
            "studyLevels": ["MD"],
        }
    )
    md_programs = await catalog_repository.list_degree_programs(
        mongo_database,
        study_level="MD",
        settings=settings,
    )
    assert any(program.get("programCode") == "027027-1-000" for program in md_programs)
    bsc_after_md = await catalog_repository.list_degree_programs(
        mongo_database,
        study_level="BSc",
        settings=settings,
    )
    assert not any(program.get("programCode") == "027027-1-000" for program in bsc_after_md)


@pytest.mark.asyncio
async def test_find_path_option_by_id_rejects_invalid_object_id(mongo_database):
    result = await catalog_repository.find_path_option_by_id(mongo_database, "not-an-object-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_catalog_faculties_returns_empty_when_no_path_options_for_level(
    mongo_database,
):
    settings = get_settings()
    await mongo_database[settings.catalog_faculties_collection].insert_one(
        {
            "facultyId": "faculty-dds",
            "institutionId": "technion",
            "status": "published",
            "nameHe": "הנדסת נתונים",
        }
    )
    faculties = await catalog_repository.list_catalog_faculties(
        mongo_database,
        study_level="PhD",
        settings=settings,
    )
    assert faculties == []


@pytest.mark.asyncio
async def test_list_path_options_filters_by_kind(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    settings = get_settings()
    tracks = await catalog_repository.list_path_options(
        mongo_database,
        faculty_id="faculty-dds",
        kind="bsc_track",
        settings=settings,
    )
    assert tracks
    assert all(option.get("kind") == "bsc_track" for option in tracks)


@pytest.mark.asyncio
async def test_list_path_options_supports_non_primary_filter(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    settings = get_settings()
    supplemental = await catalog_repository.list_path_options(
        mongo_database,
        faculty_id="faculty-dds",
        primary_only=False,
        settings=settings,
    )
    assert any(option.get("selectableAsPrimary") is False for option in supplemental)
