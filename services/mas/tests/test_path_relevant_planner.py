"""Tests for path-relevant planner course ranking."""

from __future__ import annotations

import json

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.path_relevant_planner import (
    build_path_context_summary,
    enrich_user_context_with_graduation_path,
    extract_path_priority_course_ids,
    list_path_relevant_eligible_courses,
    reconcile_proposal_with_path_alignment,
    score_plan_path_relevance,
    select_path_aligned_plan_courses,
)


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    courses = [
        {
            "general": {
                "מספר מקצוע": "00140008",
                "שם מקצוע": "Mandatory A",
                "מקצועות קדם": "",
                "נקודות": "3",
            },
            "schedule": [],
        },
        {
            "general": {
                "מספר מקצוע": "00940139",
                "שם מקצוע": "Mandatory B",
                "מקצועות קדם": "",
                "נקודות": "3",
            },
            "schedule": [],
        },
        {
            "general": {
                "מספר מקצוע": "00140102",
                "שם מקצוע": "Unrelated",
                "מקצועות קדם": "",
                "נקודות": "3",
            },
            "schedule": [],
        },
    ]
    (raw / "courses_2025_201.json").write_text(json.dumps(courses), encoding="utf-8")
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_extract_path_priority_course_ids_from_graduation_progress() -> None:
    user_context = {
        "graduation_progress": {
            "remainingMandatoryCourses": [
                {"courseNumber": "00140008"},
                {"courseNumber": "00940139"},
            ]
        }
    }
    assert extract_path_priority_course_ids(user_context) == ["00140008", "00940139"]


def test_list_path_relevant_eligible_courses_prioritizes_remaining_mandatory(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    user_context = enrich_user_context_with_graduation_path(
        {
            "track_slug": "software-engineering",
            "completed_courses": [],
            "graduation_progress": {
                "remainingMandatoryCourses": [
                    {"courseNumber": "00940139"},
                    {"courseNumber": "00140008"},
                ],
                "requirementProgress": [],
            },
        }
    )

    ranked, references = list_path_relevant_eligible_courses(
        engine,
        [],
        user_context,
    )

    assert ranked[0] == "00940139"
    assert "00140008" in ranked
    assert any(ref.startswith("path:eligible_priority=") for ref in references)


def test_select_path_aligned_plan_courses_respects_credit_cap(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    user_context = {
        "path_priority_courses": ["00140008", "00940139", "00140102"],
        "graduation_progress": {
            "remainingMandatoryCourses": [
                {"courseNumber": "00140008"},
                {"courseNumber": "00940139"},
            ]
        },
    }

    selected, _refs = select_path_aligned_plan_courses(
        engine,
        [],
        user_context,
        max_credits=6.0,
    )

    assert selected == ["00140008", "00940139"]


def test_score_plan_path_relevance_rewards_mandatory_hits() -> None:
    user_context = {
        "path_priority_courses": ["00140008", "00940139"],
    }
    good_score, good_hits, _ = score_plan_path_relevance(["00140008", "00940139"], user_context)
    bad_score, bad_hits, _ = score_plan_path_relevance(["00140102"], user_context)

    assert good_hits == 2
    assert bad_hits == 0
    assert good_score > bad_score


def test_reconcile_replaces_irrelevant_llm_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    user_context = enrich_user_context_with_graduation_path(
        {
            "track_slug": "software-engineering",
            "completed_courses": [],
            "graduation_progress": {
                "remainingMandatoryCourses": [
                    {"courseNumber": "00140008"},
                    {"courseNumber": "00940139"},
                ],
            },
        }
    )

    reconciled, references, mode = reconcile_proposal_with_path_alignment(
        ["00140102"],
        engine=engine,
        completed_courses=[],
        user_context=user_context,
        max_credits=18.0,
    )

    assert mode == "replaced"
    assert "00140008" in reconciled
    assert "00140102" not in reconciled
    assert any(ref.startswith("path:reconcile=replaced") for ref in references)


def test_build_path_context_summary_includes_context_source_and_transcript_stats() -> None:
    summary = build_path_context_summary(
        {
            "track_slug": "track-data-information-engineering",
            "plan_semester_code": "2025-2",
            "completed_courses": ["00140008", "00940139"],
            "context_source": "api_bootstrap",
            "transcript_stats": {
                "recordCount": 2,
                "uniqueCourseCount": 2,
                "resolvedCompletedCount": 2,
            },
            "graduation_progress": {
                "creditsRemaining": 90.0,
                "remainingMandatoryCourses": [{"courseNumber": "00140102"}],
            },
            "path_priority_courses": ["00140102"],
            "planning_source": "progress_bundle",
            "planning_ready": True,
            "planning_context": {
                "status": "ok",
                "transcriptCourseNumbers": ["00140008", "00940139"],
                "pathPriorityCourseNumbers": ["00140102"],
            },
            "data_quality": {"warnings": [], "ok": True},
        }
    )

    assert summary["contextSource"] == "api_bootstrap"
    assert summary["planningSource"] == "progress_bundle"
    assert summary["planningReady"] is True
    assert summary["transcriptCourseCount"] == 2
    assert summary["pathPriorityCourseCount"] == 1
    assert summary["completedCourseCount"] == 2
    assert summary["planSemesterCode"] == "2025-2"
    assert summary["transcriptStats"]["recordCount"] == 2
    assert summary["remainingMandatoryCount"] == 1

