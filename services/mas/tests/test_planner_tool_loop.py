"""Unit tests for Planner LLM graph tool loop."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.llm.planner_tool_loop import run_planner_tool_loop
from app.services.academic_graph_engine import AcademicGraphEngine


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        json.dumps(
            [
                {
                    "general": {
                        "מספר מקצוע": "00940139",
                        "שם מקצוע": "Intro Stats",
                        "מקצועות קדם": "",
                        "נקודות": "3",
                    },
                    "schedule": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


class _Settings:
    def resolved_mas_openai_api_key(self) -> str:
        return "test-key"

    def resolved_mas_openai_chat_model(self) -> str:
        return "test-model"

    def resolved_mas_openai_base_url(self) -> str | None:
        return None

    mas_planner_max_tool_iterations = 3


@pytest.mark.asyncio
async def test_planner_tool_loop_returns_proposal_after_propose_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)

    eligibility_response = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_1",
                "name": "retrieve_graph_data",
                "args": {
                    "intent": "eligibility",
                    "course_id": "00940139",
                },
            }
        ],
    )
    propose_response = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_2",
                "name": "propose_plan",
                "args": {
                    "course_ids": ["00940139"],
                    "reasoning": "Eligible intro course for next semester.",
                    "notes": "Tool loop proposal.",
                },
            }
        ],
    )

    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(side_effect=[eligibility_response, propose_response])
    mock_llm.bind_tools.return_value = mock_bound

    with patch("app.llm.planner_tool_loop.build_mas_llm", return_value=mock_llm):
        result = await run_planner_tool_loop(
            goal="Plan an introductory statistics course next semester",
            engine=engine,
            technion_raw_dir=str(tmp_path / "technion"),
            completed_courses=[],
            semester_label="Spring 2026",
            semester_filename="courses_2025_201.json",
            settings=_Settings(),
        )

    assert result.status == "proposed"
    assert result.course_ids == ["00940139"]
    assert any(ref.startswith("tool:propose_plan") for ref in result.references)
    assert len(result.steps) == 2


@pytest.mark.asyncio
async def test_planner_tool_loop_max_iterations_without_proposal(tmp_path) -> None:
    engine = _build_engine(tmp_path)

    empty_response = AIMessage(content="Thinking...", tool_calls=[])

    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(return_value=empty_response)
    mock_llm.bind_tools.return_value = mock_bound

    with patch("app.llm.planner_tool_loop.build_mas_llm", return_value=mock_llm):
        result = await run_planner_tool_loop(
            goal="Plan something ambitious",
            engine=engine,
            technion_raw_dir=str(tmp_path / "technion"),
            completed_courses=[],
            semester_label="Spring 2026",
            semester_filename="courses_2025_201.json",
            settings=_Settings(),
            max_iterations=2,
        )

    assert result.status == "max_iterations"
    assert result.course_ids == []
