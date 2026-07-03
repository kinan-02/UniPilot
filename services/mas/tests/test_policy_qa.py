"""Unit tests for policy Q&A goal routing and regulations search."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.goal_analyst_layer import analyze_goal_deterministic
from app.orchestrator.artifacts import GoalIntent
from app.orchestrator.engine import run_negotiation
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.policy_qa import build_policy_answer, search_regulation_citations


def test_analyze_goal_detects_policy_qa_intent() -> None:
    spec = analyze_goal_deterministic(
        "What is the retake policy for failed courses?",
        {},
    )
    assert spec.intent == GoalIntent.POLICY_QA


def test_analyze_goal_detects_hebrew_policy_qa_intent() -> None:
    spec = analyze_goal_deterministic("מה אומר התקנון על ערעור ציון?", {})
    assert spec.intent == GoalIntent.POLICY_QA


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    (wiki / "student-rights.md").write_text(
        "# Student Rights\nAppeal procedures and academic committee rules.\n",
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_search_regulation_citations_returns_wiki_hits(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    citations = search_regulation_citations(engine, query="appeal")
    assert citations
    assert citations[0]["slug"] == "student-rights"


def test_build_policy_answer_includes_citations(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    answer, citations = build_policy_answer(engine, question="student rights appeal")
    assert citations
    assert "student-rights" in answer


@pytest.mark.asyncio
async def test_run_negotiation_routes_policy_qa_vertical(tmp_path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)

    class _Settings:
        mas_max_negotiation_rounds = 3

        def llm_configured(self) -> bool:
            return False

    monkeypatch.setattr(
        "app.orchestrator.workflow.policy.graph_registry.get_engine",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr(
        "app.orchestrator.workflow.policy.get_settings",
        lambda: _Settings(),
    )
    monkeypatch.setattr(
        "app.orchestrator.workflow.policy.workflow_snapshot",
        AsyncMock(),
    )

    result = await run_negotiation(
        goal="What are my student rights for grade appeals?",
        user_context={},
        settings=_Settings(),
    )

    assert result.status == "completed"
    assert result.final_decision is not None
    assert result.final_decision.get("vertical") == "policy_qa"
    assert result.final_decision.get("answer")
    roles = [turn["agent_role"] for turn in result.transcript]
    assert "goal_analyst" in roles
    assert "policy_responder" in roles
    assert "planner" not in roles
