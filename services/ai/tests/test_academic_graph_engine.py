"""Unit tests for academic graph engine retrieval extensions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.academic_graph_engine import AcademicGraphEngine, parse_prerequisites_string

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


def test_parse_prerequisites_or_and():
    ast = parse_prerequisites_string(
        "(00440105 ו-00440140) או (00440105 ו-01140245)"
    )
    assert ast["type"] == "OR"
    assert len(ast["operands"]) == 2


def test_syllabus_retrieval(engine: AcademicGraphEngine):
    context = engine.retrieve_context("syllabus", course_id="00440148")
    assert "00440148" in context
    assert "סילבוס" in context or "syllabus" in context or "מקסוול" in context


def test_prerequisites_retrieval(engine: AcademicGraphEngine):
    context = engine.retrieve_context("prerequisites", course_id="00440148")
    assert "00440105" in context
    assert "prerequisites" in context or "prereqs" in context


def test_wiki_search_student_rights(engine: AcademicGraphEngine):
    context = engine.retrieve_context(
        "wiki_search", search_query="זכויות סטודנט"
    )
    assert "student-rights" in context or "זכויות" in context


def test_wiki_page_direct(engine: AcademicGraphEngine):
    context = engine.retrieve_context(
        "wiki_page", wiki_slug="student-rights"
    )
    assert "Student Rights" in context or "זכויות" in context


def test_execute_retrievals_multi_intent(engine: AcademicGraphEngine):
    blocks = engine.execute_retrievals(
        [
            {"intent": "syllabus", "course_id": "00440148"},
            {"intent": "wiki_search", "search_query": "תקנון לימודי הסמכה"},
        ],
        user_completed_courses=["00440105", "00440140"],
    )
    assert len(blocks) == 2
    assert blocks[0]["intent"] == "syllabus"
    assert blocks[1]["intent"] == "wiki_search"


def test_eligibility_facts_in_blocks(engine: AcademicGraphEngine):
    blocks = engine.execute_retrievals(
        [{"intent": "eligibility", "course_id": "00440148"}],
        user_completed_courses=["00440105", "00440140"],
    )
    assert blocks[0]["facts"]["eligible"] is True
    assert blocks[0]["facts"]["missing_prerequisites"] == []


def test_semester_switch_changes_active_catalog(engine: AcademicGraphEngine):
    summer_file = TECHNION_RAW_DIR / "courses_2025_202.json"
    if not summer_file.exists():
        pytest.skip("Summer catalog not available locally")
    engine.set_active_semester("courses_2025_202.json", str(TECHNION_RAW_DIR))
    engine.build_graph()
    assert engine.active_semester is not None
    assert engine.active_semester.filename == "courses_2025_202.json"
    context = engine.retrieve_context("schedule", course_id="00440148")
    assert "courses_2025_202.json" in context or "Summer 2026" in context
