"""Unit tests for course question analysis."""

from unittest.mock import patch

from app.agent.schemas import AgentContextPack, ContextValidation
from app.services.course_question_service import (
    analyze_course_question,
    classify_question_focus,
)


def test_classify_offering_question():
    assert classify_question_focus("Is 00940139 offered next semester?") == "offering"


def test_classify_contribution_question():
    assert classify_question_focus("Does 00940411 count toward my track?") == "contribution"


def test_analyze_missing_course_number():
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
    )
    analysis = analyze_course_question(context=context, user_message="Can I take it?")
    assert analysis.verdict == "unknown"
    assert "course number" in analysis.headline.lower()


def test_analyze_contribution_when_matched():
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "00940411"},
        academic_context={
            "course": {
                "courseNumber": "00940411",
                "title": "Intro to Data Science",
                "credits": 3.5,
            },
            "requirementContribution": {
                "countsTowardDegree": True,
                "summary": "Course 00940411 is eligible for: Data science elective pool.",
            },
        },
        validation=ContextValidation(status="valid"),
    )
    analysis = analyze_course_question(
        context=context,
        user_message="Does 00940411 count toward my degree?",
    )
    assert analysis.focus == "contribution"
    assert analysis.verdict == "yes"
    assert "00940411" in analysis.headline


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_analyze_prerequisites_missing(mock_course_by_code):
    mock_course_by_code.return_value = {
        "courseNumber": "00940219",
        "sourcePath": "wiki/courses/x.md",
        "prerequisites": [{"courseNumber": "01040031"}],
    }
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="prerequisite_check",
        entities={"courseNumber": "00940219"},
        user_context={"completedCourses": []},
        academic_context={
            "course": {"courseNumber": "00940219", "title": "Data Structures"},
            "prerequisiteResult": {
                "eligible": False,
                "missingPrerequisites": [{"courseNumber": "01040031", "courseTitle": "Intro CS"}],
                "reason": "Blocked",
            },
        },
        validation=ContextValidation(status="valid"),
    )
    analysis = analyze_course_question(
        context=context,
        user_message="What prerequisites am I missing for 00940219?",
    )
    assert analysis.verdict == "no"
    assert "01040031" in analysis.headline
    assert analysis.use_eligibility_validation is True
