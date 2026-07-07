"""Unit tests for full shadow reporting caseResults (Phase 26)."""

from __future__ import annotations

from app.agent.evaluation.full_shadow_reporting import build_full_shadow_eval_report, render_full_shadow_markdown_report
from app.agent.evaluation.replay_schemas import EvalCaseResult


def test_case_results_include_reasoning_calls_and_schema_failures() -> None:
    results = [
        EvalCaseResult(
            case_id="case_a",
            name="Case A",
            status="failed",
            reasoning_call_summaries=[
                {
                    "contractName": "task_understanding_v1",
                    "status": "fallback",
                    "schemaValid": False,
                    "reasoningStatus": "completed",
                    "outputSchemaName": "task_understanding_output_v1",
                    "validationRetryCount": 2,
                    "validationNotes": ["schema_validation_failed"],
                    "warnings": ["incomplete"],
                },
                {
                    "contractName": "planner_agent_v1",
                    "status": "completed",
                    "schemaValid": True,
                    "reasoningStatus": "completed",
                    "outputSchemaName": "planner_output_v1",
                    "validationRetryCount": 0,
                    "validationNotes": [],
                    "warnings": [],
                },
            ],
            full_shadow={"traceSummary": {"totalReasoningCalls": 2}},
        )
    ]
    report = build_full_shadow_eval_report(results, allow_real_llm=True)
    assert len(report["caseResults"]) == 1
    case = report["caseResults"][0]
    assert len(case["reasoningCalls"]) == 2
    assert len(case["schemaValidationFailures"]) == 1
    assert case["schemaValidationFailures"][0]["contractName"] == "task_understanding_v1"
    assert report["fullShadow"]["schemaValidationFailures"]["task_understanding_v1"] == 1


def test_markdown_includes_schema_validation_section() -> None:
    report = build_full_shadow_eval_report(
        [
            EvalCaseResult(
                case_id="case_a",
                name="Case A",
                status="failed",
                reasoning_call_summaries=[
                    {
                        "contractName": "planner_agent_v1",
                        "status": "fallback",
                        "schemaValid": False,
                        "reasoningStatus": "completed",
                        "validationNotes": ["missing subtasks"],
                        "warnings": [],
                    }
                ],
            )
        ],
        allow_real_llm=True,
    )
    markdown = render_full_shadow_markdown_report(report)
    assert "Per-case schema validation failures" in markdown
    assert "planner_agent_v1" in markdown
    assert "missing subtasks" in markdown
