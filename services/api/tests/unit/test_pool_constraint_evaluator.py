"""Unit tests for pool sub-requirement evaluation."""

from __future__ import annotations

from app.services.pool_constraint_evaluator import (
    DNE_STARRED_COURSE_NUMBERS,
    build_advisory_warnings,
    evaluate_bucket_pool_constraints,
    evaluate_pool_constraint,
    evaluate_science_supplement,
)


def _pool(
    *,
    program_code: str,
    suffix: str,
    operator: str,
    choose_count: int = 1,
    course_numbers: list[str] | None = None,
    min_credits: float | None = None,
) -> dict:
    refs = [
        {"courseNumber": number, "titleHint": number}
        for number in (course_numbers or [])
    ]
    rule: dict = {"type": "course_pool", "operator": operator}
    if operator == "choose_n":
        rule["chooseCount"] = choose_count
    if min_credits is not None:
        rule["minCredits"] = min_credits
    return {
        "requirementGroupId": f"{program_code}:{suffix}",
        "title": suffix,
        "minCredits": min_credits,
        "courseReferences": refs,
        "ruleExpression": rule,
    }


def _completed(*course_numbers: str) -> list[dict]:
    return [
        {
            "courseNumber": number,
            "creditsEarned": 3.5,
            "grade": 85,
            "semesterCode": "2025-1",
        }
        for number in course_numbers
    ]


def test_dne_starred_pool_requires_two_project_courses() -> None:
    pool = _pool(
        program_code="009216-1-000",
        suffix="dne-starred-project-pool",
        operator="choose_n",
        choose_count=2,
        course_numbers=sorted(DNE_STARRED_COURSE_NUMBERS)[:5],
    )
    one_star = evaluate_pool_constraint(pool, _completed(next(iter(DNE_STARRED_COURSE_NUMBERS))))
    assert one_star["satisfied"] is False

    two_stars = evaluate_pool_constraint(
        pool,
        _completed("0960222", "0960231"),
    )
    assert two_stars["satisfied"] is True


def test_iem_faculty_bucket_requires_mandatory_chains_and_one_focus_chain() -> None:
    program_code = "009009-1-000"
    pools = [
        _pool(
            program_code=program_code,
            suffix="ie-statistics-elective-chain",
            operator="choose_n",
            choose_count=1,
            course_numbers=["0960311", "0960335"],
        ),
        _pool(
            program_code=program_code,
            suffix="ie-behavior-science-chain",
            operator="choose_n",
            choose_count=1,
            course_numbers=["0960600", "0960620"],
        ),
        _pool(
            program_code=program_code,
            suffix="ie-focus-chain-game-theory",
            operator="choose_chain",
            choose_count=3,
            course_numbers=["0960226", "0960606", "0960211"],
        ),
    ]
    incomplete = evaluate_bucket_pool_constraints(
        program_code=program_code,
        bucket_suffix="elective-faculty",
        pool_documents=pools,
        completed_courses=_completed("0960311"),
    )
    assert incomplete["constraintsSatisfied"] is False

    complete = evaluate_bucket_pool_constraints(
        program_code=program_code,
        bucket_suffix="elective-faculty",
        pool_documents=pools,
        completed_courses=_completed("0960311", "0960600", "0960226", "0960606", "0960211"),
    )
    assert complete["constraintsSatisfied"] is True


def test_science_supplement_uses_physics_1m_branch() -> None:
    pool = _pool(
        program_code="009216-1-000",
        suffix="science-elective-supplement-pool",
        operator="min_credits",
        min_credits=5.5,
        course_numbers=["0940290", "0940300"],
    )
    pool["ruleExpression"] = {
        **pool["ruleExpression"],
        "physics1CourseNumber": "01140051",
        "physics1mCourseNumber": "01140071",
        "supplementCreditsIfPhysics1m": 4.5,
    }
    result = evaluate_science_supplement(pool, _completed("01140071", "0940290"))
    assert result["usedPhysics1mRule"] is True
    assert result["creditsRequired"] == 4.5
    assert result["satisfied"] is False


def test_english_deadline_warning_when_not_completed_by_semester_five() -> None:
    warnings = build_advisory_warnings(
        program_code="009216-1-000",
        completed_course_records=[
            {
                "courseNumber": "00940311",
                "semesterCode": "2025-1",
                "creditsEarned": 3.5,
            }
        ],
        current_semester_code="2027-1",
    )
    assert any(item["code"] == "english_deadline_overdue" for item in warnings)
