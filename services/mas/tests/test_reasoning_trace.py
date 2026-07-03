"""Unit tests for reasoning trace sanitization."""

from __future__ import annotations

from app.services.reasoning_trace import (
    build_advocate_trace,
    build_arbitration_trace,
    build_feasibility_trace,
    build_goal_analysis_trace,
    build_planner_repair_trace,
    build_planner_tool_loop_trace,
    build_progress_scout_trace,
    build_risk_trace,
    sanitize_planner_tool_steps,
)


def test_sanitize_planner_tool_steps_trims_content_and_blocks() -> None:
    steps = [
        {
            "iteration": 1,
            "content": "x" * 800,
            "tool_calls": [{"name": "retrieve_graph_data", "args": {"intent": "schedule"}}],
            "retrieved_blocks": [
                {
                    "intent": "schedule",
                    "course_id": "00140008",
                    "wiki_slug": "course",
                    "large_payload": {"nodes": list(range(50))},
                }
            ],
            "tool_cache_hits": 1,
            "tool_cache_misses": 0,
            "proposal": {
                "course_ids": ["00140008"],
                "reasoning": "Eligible intro course.",
                "notes": "",
            },
        }
    ]

    sanitized = sanitize_planner_tool_steps(steps)
    assert len(sanitized) == 1
    assert sanitized[0]["content"].endswith("...")
    assert "large_payload" not in sanitized[0]["retrieved_blocks"][0]
    assert sanitized[0]["proposal"]["course_ids"] == ["00140008"]


def test_build_planner_tool_loop_trace() -> None:
    trace = build_planner_tool_loop_trace(
        status="proposed",
        reasoning="Plan satisfies light workload goal.",
        notes="",
        steps=[{"iteration": 1, "tool_calls": [], "retrieved_blocks": []}],
    )
    assert trace["kind"] == "planner_tool_loop"
    assert trace["status"] == "proposed"
    assert trace["reasoning"].startswith("Plan satisfies")


def test_build_planner_repair_trace() -> None:
    trace = build_planner_repair_trace(
        course_ids=["00140008"],
        reasoning="Dropped overload course.",
        violations=["Credit overload"],
    )
    assert trace["kind"] == "planner_repair"
    assert trace["violations"] == ["Credit overload"]


def test_build_goal_analysis_trace() -> None:
    trace = build_goal_analysis_trace(
        goal_spec={
            "intent": "explicit_courses",
            "confidence": 0.9,
            "analysis_source": "deterministic",
            "explicit_course_ids": ["00140008"],
        }
    )
    assert trace["kind"] == "goal_analysis"
    assert trace["intent"] == "explicit_courses"


def test_build_arbitration_trace() -> None:
    trace = build_arbitration_trace(
        arbitration={
            "chosen_variant": "balanced",
            "utility": 0.81,
            "considered_variants": ["balanced", "fast"],
            "rejected_alternatives": [{"variant": "fast", "utility": 0.7}],
        }
    )
    assert trace["kind"] == "arbitration"
    assert trace["chosen_variant"] == "balanced"


def test_build_progress_scout_trace_single_variant() -> None:
    trace = build_progress_scout_trace(
        progress_score=0.72,
        unlock_count=3,
        critiques=[{"type": "slow_track", "message": "Does not unlock core electives."}],
    )
    assert trace["kind"] == "progress_review"
    assert trace["progressScore"] == 0.72
    assert trace["critiques"][0]["type"] == "slow_track"


def test_build_progress_scout_trace_multi_variant() -> None:
    trace = build_progress_scout_trace(
        variants=[
            {
                "variant": "balanced",
                "progressScore": 0.8,
                "unlockCount": 2,
                "critiques": [],
            }
        ]
    )
    assert trace["variantCount"] == 1
    assert trace["variants"][0]["variant"] == "balanced"


def test_build_advocate_trace() -> None:
    trace = build_advocate_trace(
        critiques=[{"type": "day_preference_conflict", "message": "Friday conflict."}],
        trade_offs=[{"action": "drop", "courseId": "00140008", "message": "Drop Friday course."}],
        critique_count=1,
    )
    assert trace["kind"] == "preference_review"
    assert trace["critiqueCount"] == 1
    assert trace["tradeOffs"][0]["action"] == "drop"


def test_build_feasibility_trace() -> None:
    trace = build_feasibility_trace(
        approved=False,
        violations=[{"type": "prereq_missing", "message": "Missing prerequisite.", "hard": True}],
    )
    assert trace["kind"] == "feasibility_review"
    assert trace["approved"] is False
    assert trace["violationCount"] == 1


def test_build_risk_trace() -> None:
    trace = build_risk_trace(
        approved=False,
        violations=[{"type": "credit_overload", "message": "Too many credits."}],
        evidence={"totalCredits": 22.0, "maxCredits": 18.0},
        probation_pressured=True,
    )
    assert trace["kind"] == "risk_review"
    assert trace["evidence"]["totalCredits"] == 22.0
    assert trace["probationPressured"] is True
