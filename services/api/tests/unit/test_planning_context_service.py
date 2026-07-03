"""Unit tests for Progress-aligned planning context helpers."""

from __future__ import annotations

from app.services.planning_context_service import (
    build_full_transcript_course_numbers,
    build_path_priority_course_numbers,
    build_planning_context,
)


def test_build_full_transcript_includes_bucket_mandatory_and_ineligible() -> None:
    numbers = build_full_transcript_course_numbers(
        {
            "requirementProgress": [
                {
                    "completedCourses": [
                        {"courseNumber": "00940345"},
                    ],
                },
            ],
            "completedMandatoryCourses": [{"courseNumber": "00140008"}],
            "ineligibleCredits": [{"courseNumber": "02340117", "reason": "overlap_no_additional_credit"}],
        }
    )

    assert numbers == ["00140008", "00940345", "02340117"]


def test_build_path_priority_orders_mandatory_then_bucket_remainders() -> None:
    priorities = build_path_priority_course_numbers(
        {
            "remainingMandatoryCourses": [{"courseNumber": "00140102"}],
            "requirementProgress": [
                {
                    "status": "in_progress",
                    "isMandatory": False,
                    "minCredits": 6,
                    "creditsCompleted": 0,
                    "remainingCourses": [{"courseNumber": "00940411"}],
                },
                {
                    "status": "satisfied",
                    "remainingCourses": [{"courseNumber": "00999999"}],
                },
            ],
        }
    )

    assert priorities == ["00140102", "00940411"]


def test_build_planning_context_structures_unavailable_graduation() -> None:
    payload = build_planning_context(graduation_progress=None)

    assert payload["status"] == "graduation_unavailable"
    assert payload["transcriptCourseNumbers"] == []
    assert payload["pathPriorityCourseNumbers"] == []


def test_build_planning_context_ok_snapshot() -> None:
    graduation = {
        "creditsRemaining": 42.0,
        "completionPercentage": 55.0,
        "remainingMandatoryCourses": [{"courseNumber": "00140102"}],
        "requirementProgress": [
            {
                "status": "in_progress",
                "completedCourses": [{"courseNumber": "00940139"}],
                "remainingCourses": [{"courseNumber": "00940411"}],
            }
        ],
        "completedMandatoryCourses": [],
        "ineligibleCredits": [],
    }
    payload = build_planning_context(graduation_progress=graduation)

    assert payload["status"] == "ok"
    assert payload["transcriptCourseNumbers"] == ["00940139"]
    assert payload["pathPriorityCourseNumbers"] == ["00140102", "00940411"]
    assert payload["creditsRemaining"] == 42.0
    assert payload["remainingMandatoryCount"] == 1
    assert payload["requirementBucketCount"] == 1
