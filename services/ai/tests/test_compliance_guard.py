"""Unit tests for Compliance Guard (AGT-9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.advisor import UserContextPayload
from app.services.advisor_agent import AdvisorResponse
from app.services.compliance_guard import (
    _check_credit_consistency,
    _check_unknown_courses,
    _ground_truth_eligibility_from_blocks,
    run_compliance_guard,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WIKI_DIR = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
TECHNION_RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
CATALOG_JSON = TECHNION_RAW_DIR / "courses_2025_201.json"


class _StubEngine:
    def __init__(self, *, catalog: dict[str, dict] | None = None) -> None:
        self.course_catalog = catalog or {"00440148": {"general": {"שם מקצוע": "Test"}}}
        self.graph = type("G", (), {"nodes": self.course_catalog})()

    def evaluate_eligibility(self, course_id: str, completed_courses: list[str]) -> tuple[bool, list[str]]:
        if course_id == "00440148" and "00440105" not in completed_courses:
            return False, ["00440105"]
        if course_id == "00440148":
            return True, []
        return True, []


@pytest.fixture(scope="module")
def real_engine():
    if not WIKI_DIR.exists() or not CATALOG_JSON.exists():
        pytest.skip("Real wiki/catalog data not available locally")
    from app.services.academic_graph_engine import AcademicGraphEngine

    engine = AcademicGraphEngine()
    engine.load_from_paths(
        str(WIKI_DIR),
        str(TECHNION_RAW_DIR),
        semester_filename="courses_2025_201.json",
    )
    engine.build_graph()
    return engine


def test_ground_truth_eligibility_from_blocks_extracts_profile_facts():
    blocks = [
        {
            "source": "profile_agent",
            "intent": "course_fit",
            "course_id": "00440148",
            "facts": {
                "course_id": "00440148",
                "eligible": False,
                "missing_prerequisites": ["00440105"],
            },
        }
    ]
    truth = _ground_truth_eligibility_from_blocks(blocks)
    assert truth["00440148"]["eligible"] is False
    assert truth["00440148"]["missing_prerequisites"] == ["00440105"]


def test_check_unknown_courses_flags_missing_catalog_entries():
    engine = _StubEngine(catalog={"00440148": {}})
    issues = _check_unknown_courses(["00440148", "99999999"], engine)  # type: ignore[arg-type]
    assert len(issues) == 1
    assert issues[0].code == "unknown_course"
    assert issues[0].course_id == "99999999"


def test_check_credit_consistency_flags_wrong_completion_percentage():
    issues = _check_credit_consistency(
        "You have completed 90% of your degree requirements.",
        {"completionPercentage": 42},
    )
    assert len(issues) == 1
    assert issues[0].code == "credit_mismatch"


def test_run_compliance_guard_passes_clean_response():
    engine = _StubEngine()
    response = AdvisorResponse(
        answer="Course 00440148 syllabus is available in the catalog.",
        confidence="high",
        course_ids=["00440148"],
    )
    result = run_compliance_guard(
        question="What is the syllabus?",
        response=response,
        retrieval_blocks=[],
        user_context=UserContextPayload(completed_courses=["00440105", "00440140"]),
        engine=engine,  # type: ignore[arg-type]
    )
    assert result.status == "passed"
    assert result.issues == []


def test_run_compliance_guard_remediates_eligibility_mismatch():
    engine = _StubEngine()
    response = AdvisorResponse(
        answer="Yes, you are eligible for course 00440148.",
        confidence="high",
        course_ids=["00440148"],
        eligibility={
            "course_id": "00440148",
            "eligible": True,
            "missing_prerequisites": [],
        },
    )
    blocks = [
        {
            "source": "profile_agent",
            "intent": "course_fit",
            "course_id": "00440148",
            "facts": {
                "course_id": "00440148",
                "eligible": False,
                "missing_prerequisites": ["00440105"],
            },
        }
    ]
    result = run_compliance_guard(
        question="Am I eligible for 00440148?",
        response=response,
        retrieval_blocks=blocks,
        user_context=UserContextPayload(completed_courses=[]),
        engine=engine,  # type: ignore[arg-type]
    )
    assert result.status == "failed"
    assert result.response is not None
    assert result.response.confidence in {"medium", "low"}
    assert result.response.eligibility is not None
    assert result.response.eligibility["eligible"] is False
    assert "00440105" in result.response.eligibility["missing_prerequisites"]
    assert "Compliance note" in result.response.answer
    assert any(remediation.startswith("corrected_eligibility") for remediation in result.remediations)


def test_run_compliance_guard_remediates_block_contradiction(real_engine):
    response = AdvisorResponse(
        answer="Yes, you are eligible for course 00440148 based on your transcript.",
        confidence="high",
        course_ids=["00440148"],
    )
    blocks = [
        {
            "source": "profile_agent",
            "intent": "course_fit",
            "course_id": "00440148",
            "facts": {
                "course_id": "00440148",
                "eligible": False,
                "missing_prerequisites": ["00440105"],
            },
        }
    ]
    result = run_compliance_guard(
        question="Am I eligible for 00440148?",
        response=response,
        retrieval_blocks=blocks,
        user_context=UserContextPayload(completed_courses=[]),
        engine=real_engine,
    )
    assert result.status == "failed"
    assert any(issue.code == "block_contradiction" for issue in result.issues)


def test_run_compliance_guard_removes_unknown_course_ids():
    engine = _StubEngine(catalog={"00440148": {}})
    response = AdvisorResponse(
        answer="See courses 00440148 and 12345678.",
        confidence="high",
        course_ids=["00440148", "12345678"],
    )
    result = run_compliance_guard(
        question="Which courses?",
        response=response,
        retrieval_blocks=[],
        user_context=UserContextPayload(),
        engine=engine,  # type: ignore[arg-type]
    )
    assert result.status == "failed"
    assert result.response is not None
    assert "12345678" not in result.response.course_ids
