"""Unit tests for MAS negotiation orchestrator."""

from __future__ import annotations

import pytest

from app.orchestrator.engine import run_negotiation
from app.services.academic_graph_engine import AcademicGraphEngine


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        """
        [
          {
            "general": {
              "מספר מקצוע": "00940139",
              "שם מקצוע": "Intro Stats",
              "מקצועות קדם": ""
            },
            "schedule": []
          },
          {
            "general": {
              "מספר מקצוע": "0940345",
              "שם מקצוע": "Discrete Math",
              "מקצועות קדם": "00940139"
            },
            "schedule": []
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


@pytest.mark.asyncio
async def test_negotiation_commits_when_goal_names_valid_course(
    tmp_path, monkeypatch
) -> None:
    engine = _build_engine(tmp_path)

    class _Settings:
        mas_max_negotiation_rounds = 3

        def llm_configured(self) -> bool:
            return False

    monkeypatch.setattr(
        "app.orchestrator.workflow.planning.graph_registry.get_engine",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr("app.orchestrator.workflow.planning.get_settings", lambda: _Settings())

    result = await run_negotiation(
        goal="Please plan course 00940139 for next semester",
        user_context={"completed_courses": []},
        settings=_Settings(),
    )

    assert result.status == "completed"
    assert result.final_decision is not None
    assert "00940139" in result.final_decision["course_ids"]
    roles = [turn["agent_role"] for turn in result.transcript]
    assert "goal_analyst" in roles
    assert "planner" in roles
    assert "catalog_scout" in roles
    assert "risk_sentinel" in roles
    assert "progress_scout" in roles
    assert "student_advocate" in roles
    assert "arbiter" in roles
    assert "explainer" in roles
    assert "red_team" in roles
    assert result.utility_breakdown is not None
    assert "utility" in result.utility_breakdown
    assert result.final_decision is not None
    assert "studentSummary" in result.final_decision
    assert "validationReferences" in result.final_decision


@pytest.mark.asyncio
async def test_negotiation_revises_after_prereq_veto(tmp_path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)

    class _Settings:
        mas_max_negotiation_rounds = 3

        def llm_configured(self) -> bool:
            return False

    monkeypatch.setattr(
        "app.orchestrator.workflow.planning.graph_registry.get_engine",
        lambda *_args, **_kwargs: engine,
    )

    result = await run_negotiation(
        goal="Plan 0940345 and 00940139",
        user_context={"completed_courses": []},
        settings=_Settings(),
    )

    assert result.status == "completed"
    assert result.final_decision is not None
    assert result.final_decision["course_ids"] == ["00940139"]
