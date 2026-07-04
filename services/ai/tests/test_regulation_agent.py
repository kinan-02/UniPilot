"""Unit tests for regulation specialist sub-agent (no OpenAI calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.regulation_agent import (
    _wiki_page,
    _wiki_search,
    build_regulation_agent_tools,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WIKI_DIR = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
TECHNION_RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
CATALOG_JSON = TECHNION_RAW_DIR / "courses_2025_201.json"


@pytest.fixture(scope="module")
def engine() -> AcademicGraphEngine:
    if not WIKI_DIR.exists() or not CATALOG_JSON.exists():
        pytest.skip("Real wiki/catalog data not available locally")
    graph_engine = AcademicGraphEngine()
    graph_engine.load_from_paths(
        str(WIKI_DIR),
        str(TECHNION_RAW_DIR),
        semester_filename="courses_2025_201.json",
    )
    graph_engine.build_graph()
    return graph_engine


def test_wiki_search_returns_matches(engine: AcademicGraphEngine):
    context = _wiki_search(engine, "זכויות סטודנט")
    assert "student-rights" in context or "זכויות" in context


def test_wiki_page_loads_student_rights(engine: AcademicGraphEngine):
    context = _wiki_page(engine, "student-rights")
    assert "Student Rights" in context or "זכויות" in context


def test_regulation_tools_record_blocks_and_citations(engine: AcademicGraphEngine):
    agent_state: dict = {
        "finish": None,
        "blocks": [],
        "cited_slugs": [],
        "suggested_contacts": [],
    }
    tools = build_regulation_agent_tools(engine, agent_state)
    tool_map = {tool.name: tool for tool in tools}

    tool_map["wiki_search"].invoke({"search_query": "ערעור ציון"})
    tool_map["wiki_page"].invoke({"wiki_slug": "student-rights"})
    tool_map["cite_sources"].invoke({"wiki_slugs": ["student-rights", "regulations-undergraduate"]})
    tool_map["suggested_contacts"].invoke(
        {"contacts": ["Student Ombudsman — grade appeals and rights"]}
    )
    finish_raw = tool_map["finish_regulation_retrieval"].invoke(
        {"status": "ok", "reasoning": "Found appeal policy context."}
    )
    finish = json.loads(finish_raw)

    assert finish["status"] == "ok"
    assert len(agent_state["blocks"]) >= 4
    assert agent_state["blocks"][0]["source"] == "regulation_agent"
    assert "student-rights" in agent_state["cited_slugs"]
    assert "regulations-undergraduate" in agent_state["cited_slugs"]
    assert len(agent_state["suggested_contacts"]) == 1
