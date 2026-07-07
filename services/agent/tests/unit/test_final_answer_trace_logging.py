"""Unit tests for golden-set eval trace logging (Phase 27.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.evaluation.final_answer_eval import (
    FinalAnswerCaseResult,
    GoldenAnswerCase,
    build_final_answer_eval_report,
)
from app.agent.evaluation.trace_extraction import populate_trace_from_turn
from app.agent.evaluation.trace_logging import (
    EvalTraceCollector,
    TraceConfig,
    assert_safe_trace_payload,
    build_case_trace_document,
    compare_expected_sources,
    render_case_trace_markdown,
    sanitize_trace_data,
    validate_trace_dir,
    validate_unsafe_raw_llm_mode,
    write_case_trace_files,
    write_trace_index,
)
from app.agent.reasoning.debug_observer import RAW_DEBUG_WARNING, EvalRawLlmDebugSink


def _case() -> GoldenAnswerCase:
    return GoldenAnswerCase(
        id="case_001",
        query_type="course_prerequisites_lookup",
        difficulty="easy",
        language="en",
        user_request="What are prerequisites for 02360343?",
        correct_summary="summary",
        key_facts=["Course code: 02360343"],
        source_wiki_pages=["wiki/courses/023-cs/02360343-theory-of-computation.md"],
    )


def test_trace_event_creation_and_sanitization() -> None:
    payload = sanitize_trace_data(
        {
            "intent": "course_question",
            "raw_prompt": "SECRET",
            "promptText": "nope",
            "notes": "x" * 5000,
        },
        level="summary",
    )
    assert "raw_prompt" not in payload
    assert "promptText" not in payload
    assert len(str(payload.get("notes") or "")) <= 500


def test_compare_expected_sources() -> None:
    result = compare_expected_sources(
        expected_pages=["wiki/concepts/regulations-undergraduate.md"],
        retrieved_pages=["wiki/concepts/regulations-undergraduate.md"],
        used_pages=[],
    )
    assert result["missingExpectedSourcePages"] == []
    missing = compare_expected_sources(
        expected_pages=["wiki/concepts/regulations-undergraduate.md"],
        retrieved_pages=[],
        used_pages=[],
    )
    assert missing["missingExpectedSourcePages"]


def test_trace_writer_outputs(tmp_path: Path) -> None:
    trace_dir = tmp_path / "final_answer_eval_traces"
    config = TraceConfig(trace_dir=trace_dir, level="detailed")
    collector = EvalTraceCollector(case=_case(), config=config)
    collector.add_event(
        phase="intent",
        event_type="classification",
        name="rules",
        status="course_question",
        data={"intent": "course_question"},
    )
    result = FinalAnswerCaseResult(
        case_id="case_001",
        status="failed",
        query_type="course_prerequisites_lookup",
        difficulty="easy",
        user_request="What are prerequisites for 02360343?",
        final_answer="eligible",
        fact_coverage=0.05,
        facts_missing=1,
    )
    trace = collector.build_case_trace(result)
    write_case_trace_files(trace, trace_dir=trace_dir)
    write_trace_index([trace], trace_dir=trace_dir)
    assert (trace_dir / "case_001.json").is_file()
    assert (trace_dir / "case_001.md").is_file()
    assert (trace_dir / "index.md").is_file()
    doc = json.loads((trace_dir / "case_001.json").read_text(encoding="utf-8"))
    assert_safe_trace_payload(doc)
    assert "promptText" not in json.dumps(doc)
    assert "# Trace: case_001" in (trace_dir / "case_001.md").read_text(encoding="utf-8")


def test_populate_trace_from_turn_includes_retrieval_compare() -> None:
    collector = EvalTraceCollector(
        case=_case(),
        config=TraceConfig(trace_dir=Path("/tmp/final_answer_eval_traces"), level="detailed"),
    )
    populate_trace_from_turn(
        collector,
        sse_events=[{"type": "agent.step.completed", "label": "Analyzing course eligibility"}],
        retrieval_metadata={
            "taskUnderstanding": {"status": "completed", "primaryIntent": "course_question"},
            "plannerDiagnostics": {"status": "completed", "subtaskCount": 1},
            "decomposedQueries": [{"text": "02360343 prerequisites", "facet": "course"}],
            "steps": [{"path": "wiki/courses/023-cs/02360343-theory-of-computation.md"}],
        },
        intent="course_question",
        entities={"courseNumber": "02360343"},
        used_sources=["wiki:courses/02360343"],
        latency_ms=1200.0,
    )
    phases = {event.phase for event in collector.events}
    assert "retrieval" in phases
    assert "task_understanding" in phases


def test_validate_trace_dir_allows_tmp(tmp_path: Path) -> None:
    allowed = tmp_path / "tmp" / "final_answer_eval_traces"
    allowed.mkdir(parents=True)
    assert validate_trace_dir(allowed)


def test_unsafe_raw_mode_requires_trace_dir() -> None:
    with pytest.raises(ValueError, match="requires_trace_dir"):
        validate_unsafe_raw_llm_mode(trace_dir=None, enabled=True)


def test_unsafe_raw_mode_refuses_non_tmp_path(tmp_path: Path) -> None:
    bad = tmp_path / "not_allowed" / "traces"
    bad.mkdir(parents=True)
    with pytest.raises(ValueError, match="unsafe_raw_llm_logs"):
        validate_unsafe_raw_llm_mode(trace_dir=bad, enabled=True)


def test_unsafe_raw_debug_writes_separate_files(tmp_path: Path) -> None:
    trace_dir = tmp_path / "tmp" / "final_answer_eval_traces"
    trace_dir.mkdir(parents=True)
    sink = EvalRawLlmDebugSink(trace_dir=trace_dir, case_id="case_001", max_chars=10_000)
    sink.on_llm_call(
        case_id="case_001",
        phase="task_understanding",
        contract_name="task_understanding_v1",
        contract_version="1.0.0",
        prompt_text="SYSTEM:\nhello",
        raw_model_output='{"status":"completed"}',
        parsed_json_preview={"status": "completed"},
        schema_valid=True,
        status="completed",
        repair_attempted=False,
        repair_succeeded=False,
        fallback_used=False,
        warnings=[],
    )
    raw_path = trace_dir / "raw_llm" / "case_001" / "task_understanding_v1.json"
    assert raw_path.is_file()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    assert RAW_DEBUG_WARNING.split("\n")[0] in payload["warning"]
    assert "promptText" in payload


def test_main_eval_report_never_includes_raw_fields() -> None:
    result = FinalAnswerCaseResult(
        case_id="case_001",
        status="failed",
        query_type="x",
        difficulty="easy",
        user_request="q",
        final_answer="answer",
    )
    report = build_final_answer_eval_report([result])
    serialized = json.dumps(report)
    assert "promptText" not in serialized
    assert "rawModelOutput" not in serialized


def test_trace_disabled_by_default_cli_path() -> None:
    """Trace config stays None unless trace dir is provided."""
    assert TraceConfig(trace_dir=Path("/tmp/final_answer_eval_traces")).trace_dir.name == "final_answer_eval_traces"
