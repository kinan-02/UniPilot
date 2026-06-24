from app.planning.prerequisite_resolver import extract_course_numbers_from_text
from app.planning.semester_planner import (
    generate_deterministic_semester_plan,
    prerequisites_met,
)
from tests.fixtures.semester_planner_fixtures import (
    ALGORITHMS,
    DATA_STRUCTURES,
    DISCRETE_MATH,
    FOUNDATIONS,
    MACHINE_LEARNING,
    build_catalog_course,
    build_completed_record,
    build_seed_like_context,
)


def test_extract_course_numbers_from_prerequisites_text():
    numbers = extract_course_numbers_from_text("00940345 and 00940411 required")
    assert numbers == ["00940345", "00940411"]


def test_prerequisites_met_requires_all_prerequisite_courses():
    course = build_catalog_course(
        DATA_STRUCTURES,
        number="02340201",
        title="Data Structures",
        prerequisites=[FOUNDATIONS],
    )
    assert prerequisites_met(course, {FOUNDATIONS}) is True
    assert prerequisites_met(course, set()) is False


def test_recommends_mandatory_courses_without_prerequisites_on_empty_transcript():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=6,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert FOUNDATIONS in recommended_ids
    assert DISCRETE_MATH in recommended_ids
    assert ALGORITHMS not in recommended_ids
    assert plan["explanation"]["emptyPlan"] is False


def test_does_not_recommend_completed_mandatory_courses():
    context = build_seed_like_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert FOUNDATIONS not in recommended_ids


def test_blocks_courses_with_unsatisfied_prerequisites():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=3,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert recommended_ids == [FOUNDATIONS]

    blocked_entry = next(
        entry
        for entry in plan["explanation"]["blockedByPrerequisites"]
        if entry["courseId"] == ALGORITHMS
    )
    assert blocked_entry is not None
    assert any(
        missing["courseId"] == DATA_STRUCTURES
        for missing in blocked_entry["missingPrerequisites"]
    )


def test_scheduled_courses_satisfy_prerequisites_for_later_recommendations():
    context = build_seed_like_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert DATA_STRUCTURES in recommended_ids


def test_includes_electives_when_mandatory_capacity_allows():
    context = build_seed_like_context(
        completed_course_records=[
            build_completed_record(FOUNDATIONS),
            build_completed_record(DISCRETE_MATH),
            build_completed_record(DATA_STRUCTURES),
            build_completed_record(ALGORITHMS),
        ],
    )
    context["graduationProgress"]["remainingMandatoryCourses"] = []
    context["graduationProgress"]["remainingElectiveCredits"] = 6.0
    context["graduationProgress"]["requirementProgress"] = [
        {
            "requirementType": "elective",
            "status": "not_started",
            "remainingCourses": [
                {
                    "courseId": MACHINE_LEARNING,
                    "courseNumber": "02360363",
                    "courseTitle": "Machine Learning",
                }
            ],
        }
    ]

    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert MACHINE_LEARNING in recommended_ids


def test_respects_max_credits_workload_limit():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=3,
    )

    assert plan["explanation"]["totalRecommendedCredits"] <= 3
    assert len(plan["explanation"]["skippedDueToWorkload"]) >= 1


# ---------------------------------------------------------------------------
# Missing coverage for semester_planner helper functions
# ---------------------------------------------------------------------------

from app.planning.semester_planner import (
    _mandatory_from_course_references,
    _matrix_semester_number,
    _resolve_matrix_course,
    build_candidate_pools,
    normalize_planner_course,
)
from tests.fixtures.semester_planner_fixtures import build_catalog_course


def test_matrix_semester_number_uses_rule_semester():
    doc = {"requirementGroupId": "x", "ruleExpression": {"semester": 3}}
    assert _matrix_semester_number(doc) == 3


def test_matrix_semester_number_handles_invalid_rule_semester():
    """TypeError/ValueError when semester is non-numeric."""
    doc = {"requirementGroupId": "x", "ruleExpression": {"semester": "not-a-number"}}
    # Raises ValueError → except block → fallback to regex
    result = _matrix_semester_number(doc)
    assert isinstance(result, int)


def test_matrix_semester_number_uses_group_id_regex():
    doc = {"requirementGroupId": "009216:semester-5-matrix", "ruleExpression": {}}
    assert _matrix_semester_number(doc) == 5


def test_matrix_semester_number_returns_999_for_unknown():
    doc = {"requirementGroupId": "no-match-at-all", "ruleExpression": {}}
    assert _matrix_semester_number(doc) == 999


def test_resolve_matrix_course_returns_none_when_no_id_or_number():
    result = _resolve_matrix_course(
        {},
        courses_by_id={},
        courses_by_number={},
    )
    assert result is None


def test_resolve_matrix_course_uses_course_id():
    from bson import ObjectId
    course_id = str(ObjectId())
    course = {
        "_id": course_id,
        "number": "00940101",
        "title": "Algebra",
        "credits": 3.0,
        "prerequisites": [],
    }
    courses_by_id = {course_id: course}
    result = _resolve_matrix_course(
        {"courseId": course_id},
        courses_by_id=courses_by_id,
        courses_by_number={},
    )
    assert result is not None
    assert result["_id"] == course_id


def test_resolve_matrix_course_uses_course_number_when_no_course_id():
    from bson import ObjectId
    raw = build_catalog_course(str(ObjectId()), number="00940101", title="Algebra")
    courses_by_number = {"00940101": raw}
    result = _resolve_matrix_course(
        {"courseNumber": "00940101"},
        courses_by_id={},
        courses_by_number=courses_by_number,
    )
    assert result is not None
    assert result["number"] == "00940101"


def test_resolve_matrix_course_returns_none_when_course_number_not_in_catalog():
    result = _resolve_matrix_course(
        {"courseNumber": "99999999"},
        courses_by_id={},
        courses_by_number={},
    )
    assert result is None


def test_mandatory_from_course_references_uses_course_id():
    from bson import ObjectId
    course_id = str(ObjectId())
    course = {
        "_id": course_id,
        "number": "00940101",
        "title": "Algebra",
        "credits": 3.0,
        "prerequisites": [],
    }
    hard_requirements = [
        {
            "isMandatory": True,
            "courseReferences": [{"courseId": course_id}],
        }
    ]
    courses_by_id = {course_id: course}
    results = _mandatory_from_course_references(
        hard_requirements,
        courses_by_id=courses_by_id,
        courses_by_number={},
        completed_course_ids=set(),
    )
    assert any(c["_id"] == course_id for c in results)


def test_mandatory_from_course_references_skips_non_mandatory():
    hard_requirements = [{"isMandatory": False, "courseReferences": [{"courseId": "x"}]}]
    results = _mandatory_from_course_references(
        hard_requirements,
        courses_by_id={},
        courses_by_number={},
        completed_course_ids=set(),
    )
    assert results == []


def test_build_candidate_pools_falls_back_to_graduation_progress_when_no_matrix():
    from bson import ObjectId
    course_id = str(ObjectId())
    catalog = [
        {
            "_id": course_id,
            "courseNumber": "00940101",
            "title": "Algebra",
            "credits": 3.0,
            "prerequisites": [],
            "status": "published",
        }
    ]
    graduation_progress = {
        "remainingMandatoryCourses": [{"courseId": course_id}],
        "remainingElectiveCredits": 0,
        "requirementProgress": [],
    }
    pools = build_candidate_pools(
        catalog_courses=catalog,
        graduation_progress=graduation_progress,
        hard_requirements=None,
        pool_documents=None,
        semester_matrix_documents=None,
        program_code=None,
        completed_course_ids=set(),
    )
    # Falls back to graduation_progress remainingMandatoryCourses
    mandatory = pools["mandatoryCandidates"]
    assert any(str(c["_id"]) == course_id for c in mandatory)


def test_course_matches_pool_returns_false_for_empty_number():
    from app.planning.semester_planner import _course_matches_pool

    course = {"number": ""}
    pool = {"courseReferences": [{"courseNumber": "00940101"}], "ruleExpression": {}}
    assert _course_matches_pool(course, pool) is False


def test_course_matches_pool_returns_false_when_no_numbers_and_no_prefixes():
    from app.planning.semester_planner import _course_matches_pool

    course = {"number": "00940101"}
    pool = {"courseReferences": [], "ruleExpression": {}}
    assert _course_matches_pool(course, pool) is False


def test_has_remaining_elective_need_returns_true_for_remaining_credits():
    from app.planning.semester_planner import _has_remaining_elective_need

    progress = {"remainingElectiveCredits": 12.0, "requirementProgress": []}
    assert _has_remaining_elective_need(progress, "CS") is True


def test_elective_from_pools_returns_empty_when_no_elective_need():
    from app.planning.semester_planner import _elective_from_pools

    progress = {"remainingElectiveCredits": 0, "requirementProgress": []}
    result = _elective_from_pools(
        graduation_progress=progress,
        pool_documents=[],
        hard_requirements=[],
        program_code="CS",
        catalog_courses=[],
        completed_course_ids=set(),
    )
    assert result == []


def test_elective_from_pools_continues_when_no_pool_for_bucket():
    """Line 283: continue when pool_document is None for an unsatisfied elective bucket."""
    from app.planning.semester_planner import _elective_from_pools

    # unsatisfied elective bucket with no matching pool
    progress = {
        "remainingElectiveCredits": 0,
        "requirementProgress": [
            {
                "status": "not_started",
                "requirementGroupId": "CS:elective-general",
                "requirementType": "elective",
            }
        ],
    }
    hard_requirements = [
        {
            "requirementGroupId": "CS:elective-general",
            "requirementType": "elective",
            "minCredits": 6.0,
        }
    ]
    result = _elective_from_pools(
        graduation_progress=progress,
        pool_documents=[],  # no pools → pool_document = None → continue (line 283)
        hard_requirements=hard_requirements,
        program_code="CS",
        catalog_courses=[],
        completed_course_ids=set(),
    )
    assert result == []


def test_unsatisfied_elective_bucket_suffixes_skips_satisfied():
    from app.planning.semester_planner import _unsatisfied_elective_bucket_suffixes

    progress = {
        "requirementProgress": [
            {"status": "satisfied", "requirementGroupId": "CS:elective-ds", "requirementType": "elective"},
            {"status": "not_started", "requirementGroupId": "CS:elective-general", "requirementType": "elective"},
        ]
    }
    result = _unsatisfied_elective_bucket_suffixes(progress, "CS")
    # satisfied entry is skipped
    assert "elective-ds" not in result
    assert "elective-general" in result


def test_can_add_another_course_returns_true_when_eligible():
    from app.planning.semester_planner import can_add_another_course
    from bson import ObjectId

    course_id = str(ObjectId())
    candidates = [
        {"_id": course_id, "number": "00940101", "credits": 3.0, "prerequisites": []}
    ]
    result = can_add_another_course(
        candidates=candidates,
        satisfied_course_ids=set(),
        remaining_credits=10.0,
        selected_course_ids=set(),
    )
    assert result is True


def test_build_plan_summary_empty_no_blocked():
    from app.planning.semester_planner import build_plan_summary

    result = build_plan_summary(
        empty_plan=True,
        partial_plan=False,
        semester_code="2025-2",
        selected_count=0,
        min_credits_target=0,
        total_credits=0,
        max_credits_limit=18,
        blocked_count=0,
        skipped_workload_count=0,
    )
    assert "No eligible courses are available for the requested semester workload" in result


def test_append_graduation_mandatory_candidates_merges_with_matrix_mandatory():
    from bson import ObjectId
    from app.planning.semester_planner import append_graduation_mandatory_candidates

    matrix_course_id = str(ObjectId())
    graduation_course_id = str(ObjectId())
    mandatory = [
        {
            "_id": matrix_course_id,
            "number": "00940345",
            "title": "Matrix course",
            "credits": 4.0,
            "prerequisites": [],
        }
    ]
    courses_by_id = {
        matrix_course_id: mandatory[0],
        graduation_course_id: {
            "_id": graduation_course_id,
            "number": "00940411",
            "title": "Graduation mandatory",
            "credits": 3.5,
            "prerequisites": [],
        },
    }
    graduation_progress = {
        "remainingMandatoryCourses": [{"courseId": graduation_course_id}],
    }

    merged = append_graduation_mandatory_candidates(
        mandatory,
        graduation_progress=graduation_progress,
        courses_by_id=courses_by_id,
        completed_course_ids=set(),
    )

    numbers = sorted(course["number"] for course in merged)
    assert numbers == ["00940345", "00940411"]


def test_matrix_semesters_for_planning_limits_brand_new_students_to_first_semester():
    from app.planning.semester_planner import matrix_semesters_for_planning

    mandatory_by_semester = {
        1: [{"_id": "a", "number": "10001"}],
        2: [{"_id": "b", "number": "10002"}],
    }

    assert matrix_semesters_for_planning(
        mandatory_by_semester,
        active_semester=1,
        completed_course_ids=set(),
    ) == [1]

    assert matrix_semesters_for_planning(
        mandatory_by_semester,
        active_semester=1,
        completed_course_ids={"completed"},
    ) == [1, 2]


def test_build_matrix_course_semester_index_ignores_missing_course_number():
    from app.planning.semester_planner import build_matrix_course_semester_index

    index = build_matrix_course_semester_index(
        [
            {
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": None}, {"courseNumber": "10001"}],
            }
        ]
    )
    assert index == {"10001": 1}


def test_resolve_active_matrix_semester_returns_none_without_documents():
    from app.planning.semester_planner import resolve_active_matrix_semester

    assert (
        resolve_active_matrix_semester(
            [],
            courses_by_id={},
            courses_by_number={},
            completed_course_ids=set(),
        )
        is None
    )


def test_resolve_active_matrix_semester_skips_unknown_course_references():
    from app.planning.semester_planner import resolve_active_matrix_semester

    result = resolve_active_matrix_semester(
        [
            {
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": "missing"}],
            }
        ],
        courses_by_id={},
        courses_by_number={},
        completed_course_ids=set(),
    )
    assert result is None


def test_partition_mandatory_by_matrix_semester_splits_unmapped():
    from app.planning.semester_planner import partition_mandatory_by_matrix_semester

    mandatory = [
        {"_id": "a", "number": "10001"},
        {"_id": "b", "number": "99999"},
    ]
    unmapped, by_semester = partition_mandatory_by_matrix_semester(
        mandatory,
        {"10001": 1},
    )
    assert len(unmapped) == 1
    assert by_semester[1][0]["number"] == "10001"


def test_append_graduation_mandatory_candidates_skips_unknown_course_refs():
    from app.planning.semester_planner import append_graduation_mandatory_candidates

    merged = append_graduation_mandatory_candidates(
        [{"_id": "a", "number": "10001"}],
        graduation_progress={"remainingMandatoryCourses": [{"courseId": "missing"}]},
        courses_by_id={},
        completed_course_ids=set(),
    )
    assert len(merged) == 1


def test_matrix_semesters_for_planning_returns_empty_when_no_active_semester():
    from app.planning.semester_planner import matrix_semesters_for_planning

    assert (
        matrix_semesters_for_planning({1: []}, active_semester=None, completed_course_ids=set())
        == []
    )


def test_matrix_semesters_for_planning_returns_empty_when_no_available_semesters():
    from app.planning.semester_planner import matrix_semesters_for_planning

    assert (
        matrix_semesters_for_planning(
            {1: []},
            active_semester=2,
            completed_course_ids={"done"},
        )
        == []
    )
