"""Extensive unit tests for graduation progress calculator (Phases 15.0 + 15.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.services.grade_evaluation import is_passing_grade
from app.services.graduation_progress_calculator import (
    build_effective_completions,
    calculate_graduation_progress,
    is_course_eligible_for_pool,
    round_credits,
    round_percentage,
)
from app.services.graduation_requirement_links import (
    index_pools_by_linked_bucket,
    resolve_pool_for_bucket,
)

PROGRAM = "009216-1-000"


def _program(**overrides):
    base = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "DDS",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "totalCredits": 155.0,
    }
    base.update(overrides)
    return base


def _bucket(suffix: str, min_credits: float, *, mandatory: bool = True, req_type: str = "elective"):
    return {
        "_id": ObjectId(),
        "requirementGroupId": f"{PROGRAM}:{suffix}",
        "title": suffix,
        "requirementType": req_type,
        "minCredits": min_credits,
        "isMandatory": mandatory,
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
    }


def _pool(group_suffix: str, *, linked_bucket: str | None = None, **kwargs):
    doc = {
        "requirementGroupId": f"{PROGRAM}:{group_suffix}",
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [],
        "enforceInGraduationProgress": True,
    }
    if linked_bucket:
        doc["linkedCreditBucketId"] = linked_bucket
    doc.update(kwargs)
    return doc


def _catalog_entry(course_id: str, number: str, credits: float, title: str = "Course"):
    return {
        course_id: {
            "_id": course_id,
            "courseNumber": number,
            "title": title,
            "credits": credits,
        }
    }


def _completion(course_id: str, grade: int | float, credits: float, **extra):
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": extra.get("semesterCode", "2024-1"),
        "recordedAt": extra.get("recordedAt", datetime(2024, 6, 1, tzinfo=timezone.utc)),
    }


# --- Passing grades (Technion 0–100, minimum pass grade is 55) ---


@pytest.mark.parametrize(
    "record,expected",
    [
        ({"grade": 0}, False),
        ({"grade": 55}, True),
        ({"grade": 56}, True),
        ({"grade": 82}, True),
        ({"grade": 100}, True),
        ({"grade": 40, "gradePoints": 82}, False),
        ({"grade": 82, "gradePoints": 50}, True),
        ({"grade": "82"}, True),
        ({"grade": "55"}, True),
        ({"grade": "A+"}, False),
    ],
)
def test_passing_grade_matrix(record, expected):
    assert is_passing_grade(record) is expected


# --- Effective completions ---


def test_effective_completions_picks_higher_credits_on_retry():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            _completion(cid, 70, 3.0, recordedAt=datetime(2024, 1, 1, tzinfo=timezone.utc)),
            _completion(cid, 82, 3.5, recordedAt=datetime(2024, 6, 1, tzinfo=timezone.utc)),
        ]
    )
    assert result[cid]["creditsEarned"] == 3.5


def test_effective_completions_uses_latest_retake_even_when_grade_is_lower():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            {
                "courseId": ObjectId(cid),
                "grade": 90,
                "creditsEarned": 3.5,
                "attempt": 1,
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(cid),
                "grade": 62,
                "creditsEarned": 3.5,
                "attempt": 2,
                "recordedAt": "2024-06-01T00:00:00Z",
            },
        ]
    )
    assert result[cid]["grade"] == 62
    assert result[cid]["attempt"] == 2


def test_effective_completions_excludes_course_when_latest_retake_fails():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            {
                "courseId": ObjectId(cid),
                "grade": 88,
                "creditsEarned": 3.5,
                "attempt": 1,
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(cid),
                "grade": 40,
                "creditsEarned": 0,
                "attempt": 2,
                "recordedAt": "2024-08-01T00:00:00Z",
            },
        ]
    )
    assert cid not in result


def test_effective_completions_tie_breaks_on_later_recorded_at_iso_strings():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            {
                "courseId": ObjectId(cid),
                "grade": 70,
                "creditsEarned": 3.0,
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(cid),
                "grade": 82,
                "creditsEarned": 3.0,
                "recordedAt": "2024-08-01T00:00:00Z",
            },
        ]
    )
    assert result[cid]["recordedAt"] == "2024-08-01T00:00:00Z"


def test_effective_completions_prefers_later_semester_pass_over_earlier_fail_with_higher_attempt():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            {
                "courseId": ObjectId(cid),
                "grade": 88,
                "creditsEarned": 3.5,
                "attempt": 1,
                "semesterCode": "2024-2",
                "recordedAt": "2024-06-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(cid),
                "grade": 40,
                "creditsEarned": 0,
                "attempt": 2,
                "semesterCode": "2023-1",
                "recordedAt": "2025-01-01T00:00:00Z",
            },
        ]
    )
    assert cid in result
    assert result[cid]["grade"] == 88
    assert result[cid]["semesterCode"] == "2024-2"


def test_effective_completions_ignores_all_failing_attempts():
    cid = str(ObjectId())
    result = build_effective_completions(
        [
            _completion(cid, 40, 0),
            _completion(cid, 54, 0),
        ]
    )
    assert result == {}


def test_effective_completions_deduplicates_multiple_courses():
    c1, c2 = str(ObjectId()), str(ObjectId())
    result = build_effective_completions(
        [_completion(c1, 88, 3.0), _completion(c2, 82, 4.0)]
    )
    assert len(result) == 2
    assert round_credits(sum(v["creditsEarned"] for v in result.values())) == 7.0


# --- Pool eligibility ---


def test_pool_eligibility_empty_pool_rejects_all():
    pool = {"ruleExpression": {"type": "course_pool"}, "courseReferences": []}
    assert is_course_eligible_for_pool("00940411", pool) is False


def test_pool_eligibility_matches_canonical_number_aliases():
    pool = {
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [{"courseNumber": "0960324"}],
    }
    assert is_course_eligible_for_pool("00960324", pool) is True
    assert is_course_eligible_for_pool("0960324", pool) is True


def test_pool_eligibility_multiple_prefixes():
    pool = {
        "ruleExpression": {"type": "course_pool", "allowedPrefixes": ["094", "097"]},
        "courseReferences": [],
    }
    assert is_course_eligible_for_pool("09400101", pool) is True
    assert is_course_eligible_for_pool("09700101", pool) is True
    assert is_course_eligible_for_pool("00940411", pool) is False


def test_pool_eligibility_wrong_rule_type():
    pool = {"ruleExpression": {"type": "semester_matrix"}, "courseReferences": [{"courseNumber": "00940411"}]}
    assert is_course_eligible_for_pool("00940411", pool) is False


# --- Phase 15.0 naming convention ---


def test_phase_15_0_ds_pool_rejects_non_listed_course():
    in_pool = str(ObjectId())
    out_pool = str(ObjectId())
    catalog = {
        **_catalog_entry(in_pool, "00940411", 3.5),
        **_catalog_entry(out_pool, "01040031", 5.0),
    }
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[
            _pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}]),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(in_pool, 88, 3.5),
            _completion(out_pool, 90, 5.0),
        ],
    )
    ds = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":elective-ds"))
    assert ds["creditsCompleted"] == 3.5
    assert ds["eligibilityEnforcement"] == "strict_pool"
    assert progress["completedCredits"] == 3.5
    assert progress["transcriptCreditsTotal"] == 8.5
    assert len(progress["ineligibleCredits"]) == 1
    assert progress["ineligibleCredits"][0]["courseNumber"] == "01040031"


def test_phase_15_0_faculty_prefix_pool():
    faculty_course = str(ObjectId())
    ds_course = str(ObjectId())
    catalog = {
        **_catalog_entry(faculty_course, "09400101", 3.0),
        **_catalog_entry(ds_course, "00940411", 3.5),
    }
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-faculty", 10.5)],
        pool_documents=[
            _pool("elective-faculty-pool", ruleExpression={"type": "course_pool", "allowedPrefixes": ["094"]}),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(faculty_course, 80, 3.0),
            _completion(ds_course, 85, 3.5),
        ],
    )
    faculty = next(r for r in progress["requirementProgress"] if "faculty" in r["requirementGroupId"])
    assert faculty["creditsCompleted"] == 3.0


# --- Phase 15.1 explicit linkedCreditBucketId ---


def test_phase_15_1_explicit_link_overrides_naming_convention():
    """Custom pool group id linked via linkedCreditBucketId — not elective-ds-pool suffix."""
    eligible = str(ObjectId())
    catalog = _catalog_entry(eligible, "00940411", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[
            _pool(
                "custom-ds-pool",
                linked_bucket=f"{PROGRAM}:elective-ds",
                courseReferences=[{"courseNumber": "00940411"}],
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(eligible, 88, 3.5)],
    )
    ds = progress["requirementProgress"][0]
    assert ds["linkedPoolGroupId"] == f"{PROGRAM}:custom-ds-pool"
    assert ds["creditsCompleted"] == 3.5


def test_phase_15_1_explicit_link_always_enforces_even_when_flag_false():
    eligible = str(ObjectId())
    catalog = _catalog_entry(eligible, "00940411", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 3.5)],
        pool_documents=[
            _pool(
                "custom-ds-pool",
                linked_bucket=f"{PROGRAM}:elective-ds",
                enforceInGraduationProgress=False,
                courseReferences=[{"courseNumber": "00940411"}],
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(eligible, 88, 3.5)],
    )
    ds = progress["requirementProgress"][0]
    assert ds["eligibilityEnforcement"] == "strict_pool"
    assert ds["creditsCompleted"] == 3.5


def test_resolve_pool_for_bucket_prefers_explicit_link():
    pools_by_group = {f"{PROGRAM}:elective-ds-pool": {"requirementGroupId": f"{PROGRAM}:elective-ds-pool"}}
    explicit = {
        f"{PROGRAM}:elective-ds": [
            {
                "requirementGroupId": f"{PROGRAM}:explicit-pool",
                "linkedCreditBucketId": f"{PROGRAM}:elective-ds",
            }
        ]
    }
    pool, group, strict = resolve_pool_for_bucket(
        program_code=PROGRAM,
        bucket_suffix="elective-ds",
        pools_by_group_id=pools_by_group,
        pools_by_linked_bucket=explicit,
    )
    assert group == f"{PROGRAM}:explicit-pool"
    assert strict is True


def test_index_pools_by_linked_bucket():
    docs = [
        {"linkedCreditBucketId": f"{PROGRAM}:elective-ds", "requirementGroupId": "x"},
        {"requirementGroupId": f"{PROGRAM}:elective-ds-pool"},
    ]
    indexed = index_pools_by_linked_bucket(docs)
    assert f"{PROGRAM}:elective-ds" in indexed
    assert len(indexed) == 1
    assert len(indexed[f"{PROGRAM}:elective-ds"]) == 1


def test_faculty_bucket_union_eligibility_across_linked_pools():
    focus_course = str(ObjectId())
    prefix_course = str(ObjectId())
    catalog = {
        **_catalog_entry(focus_course, "00960324", 3.5),
        **_catalog_entry(prefix_course, "09400101", 3.0),
    }
    faculty_bucket_id = f"{PROGRAM}:elective-faculty"
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-faculty", 6.0)],
        pool_documents=[
            _pool(
                "elective-faculty-pool",
                ruleExpression={"type": "course_pool", "allowedPrefixes": ["094"]},
            ),
            _pool(
                "is-focus-chain-performance",
                linked_bucket=faculty_bucket_id,
                courseReferences=[{"courseNumber": "00960324"}],
                ruleExpression={"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
            ),
            _pool(
                "is-additional-faculty-electives",
                linked_bucket=faculty_bucket_id,
                ruleExpression={"type": "course_pool", "operator": "min_credits", "allowedPrefixes": ["094"]},
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(focus_course, 80, 3.5),
            _completion(prefix_course, 82, 3.0),
        ],
    )
    faculty = next(
        entry for entry in progress["requirementProgress"] if entry["requirementGroupId"].endswith(":elective-faculty")
    )
    assert faculty["eligibilityEnforcement"] == "strict_pool"
    assert faculty["creditsCompleted"] == 6.0
    assert len(faculty["completedCourses"]) == 2
    assert progress["ineligibleCredits"] == []
    focus_entry = next(
        course for course in faculty["completedCourses"] if course["courseNumber"] == "00960324"
    )
    prefix_entry = next(
        course for course in faculty["completedCourses"] if course["courseNumber"] == "09400101"
    )
    assert focus_entry["assignedPoolGroupId"] == f"{PROGRAM}:is-focus-chain-performance"
    assert prefix_entry["assignedPoolGroupId"] == f"{PROGRAM}:is-additional-faculty-electives"


def test_is_track_faculty_bucket_strict_with_explorer_mapped_chain_pools():
    is_program = "009118-1-000"
    focus_course = str(ObjectId())
    catalog = _catalog_entry(focus_course, "00960327", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(programCode=is_program),
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": f"{is_program}:elective-faculty",
                "title": "Faculty electives",
                "requirementType": "elective",
                "minCredits": 3.5,
                "isMandatory": True,
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            }
        ],
        pool_documents=[
            {
                "requirementGroupId": f"{is_program}:is-focus-chain-performance",
                "ruleExpression": {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
                "courseReferences": [{"courseNumber": "00960327"}],
                "enforceInGraduationProgress": True,
            },
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(focus_course, 88, 3.5)],
    )
    faculty = progress["requirementProgress"][0]
    assert faculty["eligibilityEnforcement"] == "strict_pool"
    assert faculty["creditsCompleted"] == 3.5


# --- Bucket allocation / no double-count ---


def test_course_assigned_to_at_most_one_bucket():
    c1, c2 = str(ObjectId()), str(ObjectId())
    catalog = {**_catalog_entry(c1, "00940411", 3.5), **_catalog_entry(c2, "00940345", 4.0)}
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            _bucket("elective-ds", 24.5),
            _bucket("core-mandatory", 108.0, req_type="core"),
        ],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(c1, 88, 3.5), _completion(c2, 82, 4.0)],
    )
    assigned_ids = []
    for entry in progress["requirementProgress"]:
        for course in entry["completedCourses"]:
            assigned_ids.append(course["courseId"])
    assert len(assigned_ids) == len(set(assigned_ids))


def test_core_mandatory_greedy_fill_after_strict_pools():
    ds = str(ObjectId())
    core = str(ObjectId())
    catalog = {**_catalog_entry(ds, "00940411", 3.5), **_catalog_entry(core, "00940345", 4.0)}
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            _bucket("elective-ds", 24.5),
            _bucket("core-mandatory", 4.0, req_type="core"),
        ],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(ds, 88, 3.5), _completion(core, 82, 4.0)],
    )
    core_bucket = next(r for r in progress["requirementProgress"] if "core-mandatory" in r["requirementGroupId"])
    assert core_bucket["creditsCompleted"] == 4.0
    assert core_bucket["status"] == "satisfied"


def test_mandatory_matrix_course_reserved_for_core_not_elective_pool():
    mandatory = str(ObjectId())
    catalog = _catalog_entry(mandatory, "00940345", 4.0)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            _bucket("elective-ds", 24.5),
            _bucket("core-mandatory", 108.0, req_type="core"),
        ],
        pool_documents=[
            _pool(
                "elective-ds-pool",
                courseReferences=[{"courseNumber": "00940345"}, {"courseNumber": "00940411"}],
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(mandatory, 88, 4.0)],
        semester_matrix_documents=[
            {
                "courseReferences": [{"courseNumber": "00940345"}],
            }
        ],
    )
    ds = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":elective-ds"))
    core = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":core-mandatory"))
    assert ds["creditsCompleted"] == 0
    assert core["creditsCompleted"] == 4.0
    assert any(course["courseNumber"] == "00940345" for course in core["completedCourses"])


# --- Status summary ---


def test_status_not_started_with_zero_credits():
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[],
        catalog_courses_by_id={},
        completed_course_records=[],
    )
    assert progress["statusSummary"] == "not_started"
    assert progress["completedCredits"] == 0


def test_status_complete_when_all_buckets_satisfied():
    c1 = str(ObjectId())
    catalog = _catalog_entry(c1, "00940411", 5.0)
    progress = calculate_graduation_progress(
        degree_program=_program(totalCredits=5.0),
        hard_requirements=[_bucket("elective-ds", 5.0, mandatory=False)],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(c1, 88, 5.0)],
    )
    assert progress["statusSummary"] == "complete"
    assert progress["missingRequirements"] == []


def test_status_in_progress_with_partial_credits():
    c1 = str(ObjectId())
    catalog = _catalog_entry(c1, "00940411", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(c1, 88, 3.5)],
    )
    assert progress["statusSummary"] == "in_progress"


# --- Fractional credits & percentages ---


def test_fractional_credits_and_percentage():
    c1 = str(ObjectId())
    catalog = _catalog_entry(c1, "00940411", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(totalCredits=10.0),
        hard_requirements=[_bucket("elective-ds", 10.0)],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(c1, 88, 3.5)],
    )
    assert progress["completedCredits"] == 3.5
    assert progress["creditsRemaining"] == 6.5
    assert progress["completionPercentage"] == round_percentage(35.0)


def test_completion_percentage_capped_at_100():
    c1 = str(ObjectId())
    catalog = _catalog_entry(c1, "00940411", 200.0)
    progress = calculate_graduation_progress(
        degree_program=_program(totalCredits=10.0),
        hard_requirements=[_bucket("elective-ds", 10.0)],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(c1, 88, 200.0)],
    )
    assert progress["completionPercentage"] == 100.0


# --- Missing catalog entry ---


def test_completion_without_catalog_records_ineligible_and_does_not_assign_credits():
    unknown = str(ObjectId())
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id={},
        completed_course_records=[_completion(unknown, 88, 3.5)],
    )
    assert progress["completedCredits"] == 0
    assert progress["transcriptCreditsTotal"] == 3.5
    ds = progress["requirementProgress"][0]
    assert ds["creditsCompleted"] == 0
    assert len(progress["ineligibleCredits"]) == 1
    assert progress["ineligibleCredits"][0]["reason"] == "missing_catalog"


def test_not_assigned_credits_excluded_from_degree_total():
    in_pool = str(ObjectId())
    out_pool = str(ObjectId())
    catalog = {
        **_catalog_entry(in_pool, "00940411", 3.5),
        **_catalog_entry(out_pool, "99999999", 5.0),
    }
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 24.5)],
        pool_documents=[_pool("elective-ds-pool", courseReferences=[{"courseNumber": "00940411"}])],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(in_pool, 88, 3.5),
            _completion(out_pool, 90, 5.0),
        ],
    )
    assert progress["completedCredits"] == 3.5
    assert progress["transcriptCreditsTotal"] == 8.5
    assert any(row["reason"] == "not_assigned_to_requirement" for row in progress["ineligibleCredits"])
    assert progress["assumptionKeys"]


def test_pool_eligibility_accepts_prefix_when_explicit_list_also_present():
    pool = {
        "ruleExpression": {
            "type": "course_pool",
            "operator": "choose_credits",
            "allowedPrefixes": ["094"],
        },
        "courseReferences": [{"courseNumber": "00960324"}],
    }
    assert is_course_eligible_for_pool("00960324", pool) is True
    assert is_course_eligible_for_pool("09400101", pool) is True
    assert is_course_eligible_for_pool("00940411", pool) is False


def test_strict_pool_stops_assigning_after_min_credits_reached():
    first = str(ObjectId())
    second = str(ObjectId())
    catalog = {
        **_catalog_entry(first, "00940411", 3.5),
        **_catalog_entry(second, "00940345", 4.0),
    }
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-ds", 3.5)],
        pool_documents=[
            _pool(
                "elective-ds-pool",
                courseReferences=[
                    {"courseNumber": "00940411"},
                    {"courseNumber": "00940345"},
                ],
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(first, 88, 3.5),
            _completion(second, 82, 4.0),
        ],
    )
    ds = progress["requirementProgress"][0]
    assert ds["creditsCompleted"] == 3.5
    assert len(ds["completedCourses"]) == 1


def test_bucket_credits_completed_capped_at_min_credits():
    first = str(ObjectId())
    second = str(ObjectId())
    catalog = {
        **_catalog_entry(first, "00940411", 3.5),
        **_catalog_entry(second, "00940345", 3.0),
    }
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("elective-faculty", 6.0)],
        pool_documents=[
            _pool(
                "elective-faculty-pool",
                ruleExpression={"type": "course_pool", "allowedPrefixes": ["0094", "0096"]},
            ),
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(first, 88, 3.5),
            _completion(second, 82, 3.0),
        ],
    )
    faculty = progress["requirementProgress"][0]
    assert faculty["creditsCompleted"] == 6.0
    assert len(faculty["completedCourses"]) == 2
    assert progress["completedCredits"] == 6.5
    assert progress["transcriptCreditsTotal"] == 6.5


# --- Non-credit_bucket requirements ignored ---


def test_non_credit_bucket_requirements_excluded_from_progress():
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": f"{PROGRAM}:track-a",
                "title": "Track",
                "minCredits": 30.0,
                "isMandatory": True,
                "ruleExpression": {"type": "track_requirement"},
            },
            _bucket("elective-ds", 24.5),
        ],
        pool_documents=[],
        catalog_courses_by_id={},
        completed_course_records=[],
    )
    assert len(progress["requirementProgress"]) == 1
    assert progress["requirementProgress"][0]["requirementGroupId"].endswith(":elective-ds")
