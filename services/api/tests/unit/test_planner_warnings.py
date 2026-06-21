"""Unit tests for planner prerequisite and credit warnings."""

from app.planning.planner_warnings import assess_prerequisite_warning, build_planner_insights


def test_assess_prerequisite_manual_verification_when_only_text():
    course = {
        "courseNumber": "00940345",
        "prerequisitesText": "קורסים 00940101 ו-00940102",
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={},
    )
    assert result["status"] == "manual_verification"


def test_assess_prerequisite_satisfied_with_explicit_ids():
    course = {
        "courseNumber": "00940345",
        "prerequisites": ["abc123"],
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[{"courseId": "abc123", "courseNumber": "00940101"}],
        courses_by_number={},
        courses_by_id={"abc123": {"courseNumber": "00940101", "titleHebrew": "Algebra"}},
    )
    assert result["status"] == "satisfied"


def test_assess_prerequisite_missing_with_explicit_ids():
    course = {
        "courseNumber": "00940345",
        "prerequisites": ["abc123"],
    }
    result = assess_prerequisite_warning(
        course,
        completed_records=[],
        courses_by_number={},
        courses_by_id={"abc123": {"courseNumber": "00940101", "titleHebrew": "Algebra"}},
    )
    assert result["status"] == "missing"
    assert result["missingPrerequisites"][0]["courseNumber"] == "00940101"


def test_build_planner_insights_total_credits_and_conflicts():
    plan = {
        "semesters": [
            {
                "plannedCourses": [
                    {"courseId": "1", "courseNumber": "00940345", "credits": 3, "isActive": True},
                    {"courseId": "2", "courseNumber": "00940411", "credits": 3.5, "isActive": False},
                ],
                "weeklySchedule": {
                    "status": "conflicts",
                    "entries": [
                        {
                            "courseNumber": "00940345",
                            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
                        },
                        {
                            "courseNumber": "00940411",
                            "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30"}],
                        },
                    ],
                    "conflicts": [
                        {
                            "day": "Sunday",
                            "timeRange": "10:30-12:30",
                            "courseNumbers": ["00940345", "00940411"],
                        }
                    ],
                },
            }
        ]
    }
    insights = build_planner_insights(
        plan,
        profile={"preferences": {"maxCreditsPerSemester": 2}},
        completed_records=[],
        catalog_courses=[],
    )
    assert insights["totalCredits"] == 3
    assert insights["creditsWarning"]["status"] == "over_max"
    assert insights["scheduleConflicts"] == []
