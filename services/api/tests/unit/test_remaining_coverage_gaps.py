"""Targeted tests for remaining 100% coverage gaps."""

from __future__ import annotations

from bson import ObjectId
import pytest
from pydantic import ValidationError

from app.curriculum.graph_overlay import (
    _completed_numbers,
    _completed_via_alternative,
    _register_number,
    build_equivalence_groups,
)
from app.planning.semester_planner import (
    _course_matches_pool,
    _pool_course_numbers,
    _resolve_matrix_course,
)
from app.repositories import catalog_repository
from app.schemas.transcript_import import CommitTranscriptCourseInput
from app.services.course_pool_classification import (
    is_explicit_catalog_pool,
    pool_specificity_rank,
    resolve_claiming_pool,
)
from app.services.graduation_progress_calculator import calculate_graduation_progress
from app.services.graduation_requirement_links import (
    collect_eligibility_pools_for_bucket,
    resolve_pool_for_bucket,
)
from app.services.transcript_import_normalization import resolve_import_credits

PROGRAM = "009216-1-000"


def test_completed_numbers_ignores_blank_course_numbers():
    assert _completed_numbers([{"courseNumber": "", "grade": 90}]) == set()


def test_register_number_ignores_none():
    numbers: set[str] = set()
    _register_number(numbers, None)
    assert numbers == set()


def test_build_equivalence_groups_reuses_existing_member_groups():
    groups = build_equivalence_groups(
        [
            {"courseNumber": "1040065", "alternatives": ["1040016"]},
            {"courseNumber": "1040016", "alternatives": []},
        ]
    )
    assert groups["1040065"] == groups["1040016"]


def test_completed_via_alternative_returns_none_when_primary_already_completed():
    groups = build_equivalence_groups(
        [{"courseNumber": "1040065", "alternatives": ["1040016"]}],
    )
    assert (
        _completed_via_alternative(
            primary="1040065",
            completed={"1040065"},
            groups=groups,
        )
        is None
    )


def test_completed_via_alternative_returns_none_when_only_primary_variants_passed(monkeypatch):
    class _PrimaryCanonicalSentinel:
        def __ne__(self, other: object) -> bool:
            return False

    sentinel = _PrimaryCanonicalSentinel()
    monkeypatch.setattr(
        "app.curriculum.graph_overlay._canonical_or_raw",
        lambda _primary: sentinel,
    )
    assert (
        _completed_via_alternative(
            primary="1040065",
            completed={"1040016"},
            groups=build_equivalence_groups(
                [{"courseNumber": "1040065", "alternatives": ["1040016"]}],
            ),
        )
        is None
    )


def test_pool_course_numbers_skips_null_reference():
    pool = {"courseReferences": [{"courseNumber": None}, {"courseNumber": "00940101"}]}
    assert _pool_course_numbers(pool) == {"00940101"}


def test_course_matches_pool_by_explicit_number_list():
    course = {"number": "00940101"}
    pool = {"courseReferences": [{"courseNumber": "00940101"}], "ruleExpression": {}}
    assert _course_matches_pool(course, pool) is True


def test_course_matches_pool_by_allowed_prefix():
    course = {"number": "09400101"}
    pool = {
        "courseReferences": [],
        "ruleExpression": {"allowedPrefixes": ["094"]},
    }
    assert _course_matches_pool(course, pool) is True


def test_resolve_matrix_course_matches_canonical_catalog_number(monkeypatch):
    monkeypatch.setattr(
        "app.services.course_reference_keys.course_reference_number_keys",
        lambda _reference: {"960401"},
    )
    resolved = _resolve_matrix_course(
        {"courseNumber": "960401"},
        courses_by_id={},
        courses_by_number={"00960401": {"_id": "abc", "number": "00960401", "credits": 3}},
    )
    assert resolved is not None
    assert resolved["number"] == "00960401"


@pytest.mark.asyncio
async def test_get_course_by_number_returns_none_for_invalid_number(mongo_database):
    assert await catalog_repository.get_course_by_number(mongo_database, "bad-number") is None


def test_commit_course_input_validator_rejects_invalid_number():
    with pytest.raises(ValidationError):
        CommitTranscriptCourseInput(
            courseNumber="123",
            semesterCode="2024-1",
            grade=85,
            creditsEarned=3,
        )


def test_resolve_import_credits_returns_zero_when_unresolved():
    credits = resolve_import_credits(
        CommitTranscriptCourseInput(
            courseNumber="01040031",
            semesterCode="2024-1",
            grade=85,
            creditsEarned=0,
        ),
        None,
    )
    assert credits == 0.0


def test_pool_specificity_rank_covers_chain_and_suffix_pools():
    choose_n = {
        "requirementGroupId": f"{PROGRAM}:statistics-elective",
        "ruleExpression": {"operator": "choose_n"},
    }
    focus = {
        "requirementGroupId": f"{PROGRAM}:is-focus-chain-performance",
        "ruleExpression": {"operator": "choose_credits"},
    }
    behavior = {
        "requirementGroupId": f"{PROGRAM}:ie-behavior-science-chain",
        "ruleExpression": {"operator": "choose_credits"},
    }
    enrichment = {
        "requirementGroupId": f"{PROGRAM}:enrichment-pool",
        "ruleExpression": {"operator": "choose_credits"},
    }
    ds_pool = {
        "requirementGroupId": f"{PROGRAM}:elective-ds-pool",
        "ruleExpression": {"operator": "choose_credits"},
    }
    assert pool_specificity_rank(choose_n, PROGRAM) == 90
    assert pool_specificity_rank(focus, PROGRAM) == 80
    assert pool_specificity_rank(behavior, PROGRAM) == 70
    assert pool_specificity_rank(enrichment, PROGRAM) == 60
    assert pool_specificity_rank(ds_pool, PROGRAM) == 30
    generic = {
        "requirementGroupId": f"{PROGRAM}:custom-requirement",
        "ruleExpression": {"operator": "choose_credits"},
    }
    assert pool_specificity_rank(generic, PROGRAM) == 10


def test_resolve_claiming_pool_returns_none_when_no_eligible_match():
    pool = {
        "requirementGroupId": f"{PROGRAM}:elective-ds-pool",
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [{"courseNumber": "00940411"}],
    }
    assert resolve_claiming_pool("99999999", [pool], program_code=PROGRAM) is None


def test_is_explicit_catalog_pool_recognizes_choose_n():
    pool = {
        "requirementGroupId": f"{PROGRAM}:statistics-elective",
        "ruleExpression": {"operator": "choose_n"},
    }
    assert is_explicit_catalog_pool(pool, PROGRAM) is True


def test_collect_eligibility_pools_skips_other_program_documents():
    pools, _, _ = collect_eligibility_pools_for_bucket(
        program_code=PROGRAM,
        bucket_suffix="elective-ds",
        pools_by_group_id={},
        pools_by_linked_bucket={},
        pool_documents=[
            {
                "requirementGroupId": "009999-1-000:elective-ds-pool",
                "ruleExpression": {"type": "course_pool"},
            }
        ],
    )
    assert pools == []


def test_resolve_pool_for_bucket_returns_none_without_pools():
    pool, group, strict = resolve_pool_for_bucket(
        program_code=PROGRAM,
        bucket_suffix="unknown-bucket",
        pools_by_group_id={},
        pools_by_linked_bucket={},
        pool_documents=[],
    )
    assert pool is None
    assert strict is False


def test_resolve_pool_for_bucket_falls_back_to_first_linked_pool():
    linked = {
        f"{PROGRAM}:elective-faculty": [
            {
                "requirementGroupId": f"{PROGRAM}:is-focus-chain-performance",
                "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            }
        ]
    }
    pool, group, strict = resolve_pool_for_bucket(
        program_code=PROGRAM,
        bucket_suffix="elective-faculty",
        pools_by_group_id={},
        pools_by_linked_bucket=linked,
        pool_documents=linked[f"{PROGRAM}:elective-faculty"],
    )
    assert pool is not None
    assert group == f"{PROGRAM}:is-focus-chain-performance"
    assert strict is True


def test_resolve_pool_for_bucket_falls_back_when_primary_group_missing():
    linked = {
        f"{PROGRAM}:elective-faculty": [
            {
                "requirementGroupId": "",
                "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            },
            {
                "requirementGroupId": f"{PROGRAM}:is-focus-chain-performance",
                "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            },
        ]
    }
    pool, group, strict = resolve_pool_for_bucket(
        program_code=PROGRAM,
        bucket_suffix="elective-faculty",
        pools_by_group_id={},
        pools_by_linked_bucket=linked,
        pool_documents=linked[f"{PROGRAM}:elective-faculty"],
    )
    assert pool is not None
    assert group == f"{PROGRAM}:is-focus-chain-performance"
    assert strict is True


def _mandatory_progress(completed_records, matrix_documents):
    program = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "DDS",
        "totalCredits": 155.0,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
    }
    bucket = {
        "_id": ObjectId(),
        "requirementGroupId": f"{PROGRAM}:core-mandatory",
        "title": "core-mandatory",
        "requirementType": "core",
        "minCredits": 108.0,
        "isMandatory": True,
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
    }
    return calculate_graduation_progress(
        degree_program=program,
        hard_requirements=[bucket],
        pool_documents=[],
        catalog_courses_by_id={
            str(record["courseId"]): {
                "_id": record["courseId"],
                "courseNumber": record["courseNumber"],
                "title": record["courseNumber"],
                "credits": record["creditsEarned"],
            }
            for record in completed_records
        },
        completed_course_records=completed_records,
        semester_matrix_documents=matrix_documents,
    )


def test_mandatory_bucket_skips_non_mandatory_transcript_courses():
    elective_id = ObjectId()
    progress = _mandatory_progress(
        [
            {
                "courseId": elective_id,
                "grade": 88,
                "creditsEarned": 3.5,
                "semesterCode": "2024-1",
                "courseNumber": "00940411",
            }
        ],
        [{"courseReferences": [{"courseNumber": "1040065"}]}],
    )
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert core["completedCourses"] == []


def test_mandatory_bucket_counts_only_one_course_per_equivalence_group():
    first_id = ObjectId()
    second_id = ObjectId()
    progress = _mandatory_progress(
        [
            {
                "courseId": first_id,
                "grade": 85,
                "creditsEarned": 5.0,
                "semesterCode": "2024-1",
                "courseNumber": "1040065",
            },
            {
                "courseId": second_id,
                "grade": 90,
                "creditsEarned": 5.0,
                "semesterCode": "2024-2",
                "courseNumber": "1040016",
            },
        ],
        [{"courseReferences": [{"courseNumber": "1040065", "alternatives": ["1040016"]}]}],
    )
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert len(core["completedCourses"]) == 1
