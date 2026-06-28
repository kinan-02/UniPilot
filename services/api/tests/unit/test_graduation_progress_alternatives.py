"""Graduation progress tests for parallel/alternative matrix courses."""

from __future__ import annotations

from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress

PROGRAM = "009009-1-000"


def _program(**overrides):
    base = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "IE",
        "totalCredits": 155.0,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
    }
    base.update(overrides)
    return base


def _bucket(suffix: str, min_credits: float, *, mandatory: bool | None = None, req_type: str | None = None):
    is_mandatory = suffix == "core-mandatory" if mandatory is None else mandatory
    requirement_type = "core" if suffix == "core-mandatory" else "elective"
    if req_type is not None:
        requirement_type = req_type
    return {
        "_id": ObjectId(),
        "requirementGroupId": f"{PROGRAM}:{suffix}",
        "title": suffix,
        "requirementType": requirement_type,
        "minCredits": min_credits,
        "isMandatory": is_mandatory,
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
    }


def _catalog_entry(course_id: str, number: str, credits: float):
    return {
        course_id: {
            "_id": ObjectId(course_id),
            "courseNumber": number,
            "title": number,
            "credits": credits,
        }
    }


def _completion(course_id: str, grade: int, credits: float):
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": "2024-1",
    }


def test_parallel_matrix_course_counts_toward_core_mandatory():
    alt_course = str(ObjectId())
    catalog = _catalog_entry(alt_course, "1040016", 5.0)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("core-mandatory", 108.0)],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(alt_course, 82, 5.0)],
        semester_matrix_documents=[
            {
                "courseReferences": [
                    {"courseNumber": "1040065", "alternatives": ["1040016"]},
                ]
            }
        ],
    )
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert core["creditsCompleted"] == 5.0
    assert any(course["courseNumber"] == "1040016" for course in core["completedCourses"])
    assert progress["ineligibleCredits"] == []
    remaining_numbers = {
        course["courseNumber"] for course in progress["remainingMandatoryCourses"]
    }
    assert "1040065" not in remaining_numbers
    assert "1040016" not in remaining_numbers


def test_completed_ise_ecommerce_code_satisfies_dne_transcript_number():
    completed_id = str(ObjectId())
    catalog = _catalog_entry(completed_id, "00960211", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(programCode="009118-1-000"),
        hard_requirements=[_bucket("core-mandatory", 108.0, req_type="core")],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(completed_id, 85, 3.5)],
        semester_matrix_documents=[
            {
                "courseReferences": [
                    {"courseNumber": "00960221", "titleHint": "E-commerce models"},
                ]
            }
        ],
    )
    remaining_numbers = {
        course["courseNumber"] for course in progress["remainingMandatoryCourses"]
    }
    assert "00960221" not in remaining_numbers
    assert "00960211" not in remaining_numbers


def test_focus_chain_pool_accepts_parallel_substitute_course():
    is_program = "009118-1-000"
    substitute = str(ObjectId())
    catalog = _catalog_entry(substitute, "0980413", 3.5)
    progress = calculate_graduation_progress(
        degree_program=_program(programCode=is_program),
        hard_requirements=[
            {
                **_bucket("elective-faculty", 24.5),
                "requirementGroupId": f"{is_program}:elective-faculty",
            }
        ],
        pool_documents=[
            {
                "requirementGroupId": f"{is_program}:is-focus-chain-performance",
                "linkedCreditBucketId": f"{is_program}:elective-faculty",
                "ruleExpression": {
                    "type": "course_pool",
                    "operator": "choose_chain",
                    "chooseCount": 3,
                },
                "courseReferences": [
                    {"courseNumber": "00960327"},
                    {"courseNumber": "00960324", "alternatives": ["0980413"]},
                ],
            }
        ],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(substitute, 85, 3.5)],
    )
    faculty = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":elective-faculty")
    )
    assert faculty["creditsCompleted"] == 3.5
    entry = faculty["completedCourses"][0]
    assert entry["courseNumber"] == "0980413"
    assert entry["assignedPoolGroupId"] == f"{is_program}:is-focus-chain-performance"


def test_mandatory_courses_beyond_credit_min_stay_assigned_not_ineligible():
    catalog: dict[str, dict] = {}
    completions = []
    matrix_refs = []
    for index in range(28):
        course_id = str(ObjectId())
        course_number = f"00940{index:03d}"
        catalog[course_id] = {
            "_id": ObjectId(course_id),
            "courseNumber": course_number,
            "title": course_number,
            "credits": 4.0,
        }
        completions.append(
            {
                "courseId": ObjectId(course_id),
                "grade": 88,
                "creditsEarned": 4.0,
                "semesterCode": "2024-1",
            }
        )
        matrix_refs.append({"courseNumber": course_number})

    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("core-mandatory", 108.0, req_type="core")],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=completions,
        semester_matrix_documents=[{"courseReferences": matrix_refs}],
    )
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert len(core["completedCourses"]) == 28
    assert core["creditsCompleted"] == 108.0
    assert core["status"] == "satisfied"
    assert progress["ineligibleCredits"] == []


def test_remaining_mandatory_courses_list_unsatisfied_matrix_slots():
    completed_id = str(ObjectId())
    catalog = _catalog_entry(completed_id, "00940101", 5.0)
    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[_bucket("core-mandatory", 108.0, req_type="core")],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(completed_id, 88, 5.0)],
        semester_matrix_documents=[
            {"courseReferences": [{"courseNumber": "00940101"}]},
            {"courseReferences": [{"courseNumber": "00940102", "titleHint": "Missing course"}]},
        ],
    )
    remaining_numbers = {
        course["courseNumber"] for course in progress["remainingMandatoryCourses"]
    }
    assert "00940102" in remaining_numbers
    assert "00940101" not in remaining_numbers
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert any(course["courseNumber"] == "00940102" for course in core["remainingCourses"])


def test_matrix_mandatory_assigns_to_technion_faculty_bucket_when_no_core_mandatory():
    civil_program = "001401-1-000"
    course_id = str(ObjectId())
    catalog = {
        course_id: {
            "_id": ObjectId(course_id),
            "courseNumber": "00140102",
            "title": "00140102",
            "credits": 4.0,
        }
    }
    progress = calculate_graduation_progress(
        degree_program=_program(programCode=civil_program),
        hard_requirements=[
            {
                **_bucket(
                    "mandatory-technion-and-faculty-courses",
                    89.0,
                    mandatory=True,
                    req_type="core",
                ),
                "requirementGroupId": f"{civil_program}:mandatory-technion-and-faculty-courses",
            },
            {
                **_bucket("track-mandatory-courses", 45.5, mandatory=True, req_type="core"),
                "requirementGroupId": f"{civil_program}:track-mandatory-courses",
            },
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[_completion(course_id, 88, 4.0)],
        semester_matrix_documents=[{"courseReferences": [{"courseNumber": "00140102"}]}],
    )
    technion = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":mandatory-technion-and-faculty-courses")
    )
    track = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":track-mandatory-courses")
    )
    assert technion["creditsCompleted"] == 4.0
    assert any(course["courseNumber"] == "00140102" for course in technion["completedCourses"])
    assert track["creditsCompleted"] == 0
    assert progress["ineligibleCredits"] == []
