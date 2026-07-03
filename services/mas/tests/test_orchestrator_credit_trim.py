"""Unit tests for credit overload revision in negotiation."""

from __future__ import annotations

import json

import pytest

from app.orchestrator.engine import run_negotiation
from app.services.academic_graph_engine import AcademicGraphEngine


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    courses = [
        {
            "general": {
                "מספר מקצוע": "00940139",
                "שם מקצוע": "Intro Stats",
                "מקצועות קדם": "",
                "נקודות": "6",
            },
            "schedule": [],
        },
        {
            "general": {
                "מספר מקצוע": "0940345",
                "שם מקצוע": "Discrete Math",
                "מקצועות קדם": "00940139",
                "נקודות": "6",
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


@pytest.mark.asyncio
async def test_negotiation_trims_plan_after_credit_overload_veto(tmp_path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)

    class _Settings:
        mas_max_negotiation_rounds = 3

        def llm_configured(self) -> bool:
            return False

        def resolved_technion_raw_dir(self) -> str:
            return str(tmp_path / "technion")

    monkeypatch.setattr(
        "app.orchestrator.workflow.planning.graph_registry.get_engine",
        lambda *_args, **_kwargs: engine,
    )

    result = await run_negotiation(
        goal="Plan 00940139 and 0940345",
        user_context={
            "completed_courses": ["00940139"],
            "preferences": {"maxCreditsPerSemester": 6},
        },
        settings=_Settings(),
    )

    assert result.status == "completed"
    assert result.final_decision is not None
    assert len(result.final_decision["course_ids"]) == 1
    roles = [turn["agent_role"] for turn in result.transcript]
    assert "risk_sentinel" in roles
