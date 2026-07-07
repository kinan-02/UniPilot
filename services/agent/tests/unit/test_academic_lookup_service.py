"""Unit tests for deterministic wiki academic lookups."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.entity_resolver import resolve_entities
from app.agent.intent_router import classify_intent
from app.services.academic_lookup_service import (
    classify_course_question_focus,
    compose_course_catalog_answer,
    compose_non_regular_standing_answer,
    compose_regulation_moed_answer,
    compose_track_credit_breakdown_answer,
    course_by_code,
    detect_academic_query_kind,
    tracks_requiring_course,
    try_compose_deterministic_answer,
)
from app.services.course_question_service import analyze_course_question, classify_question_focus
from app.agent.schemas import AgentContextPack, ContextValidation


REPO_ROOT = Path(__file__).resolve().parents[4]
WIKI_ROOT = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"


@pytest.fixture(autouse=True)
def wiki_path(monkeypatch: pytest.MonkeyPatch) -> None:
    if not WIKI_ROOT.is_dir():
        pytest.skip("catalog wiki fixtures unavailable")
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(WIKI_ROOT))
    from app.services import academic_lookup_service as lookup_module

    lookup_module._cached_track_code_index.cache_clear()


def test_classify_prerequisite_lookup_not_eligibility():
    assert classify_course_question_focus("What are the prerequisites for 02360343?") == "catalog_prerequisites"
    assert classify_question_focus("What are the prerequisites for 02360343?") == "catalog_prerequisites"


def test_classify_reverse_track_lookup():
    assert classify_course_question_focus("Which tracks require 00940412?") == "tracks_requiring"
    assert detect_academic_query_kind("Which study tracks formally require Probability M, code 00940412?") == "course_tracks_requiring"


def test_classify_eligibility_question():
    assert classify_course_question_focus("Can I take 02360343?") == "eligibility"


def test_entity_resolver_track_code_not_course():
    entities = resolve_entities(
        "How many total credits for the 4-year General Computer Science track (track code 023023)?"
    )
    assert entities.get("trackCode") == "023023"
    assert "courseNumber" not in entities


def test_intent_router_track_structure():
    result = classify_intent(
        "How many total credits do I need to graduate from the 4-year General Computer Science track (track code 023023), and how are they broken down by category?"
    )
    # `track_structure_lookup` is a more specific intent added after this test
    # was written; it now correctly supersedes the old `general_academic_question`
    # catch-all for track/credit-structure questions like this one.
    assert result.intent == "track_structure_lookup"


def test_course_by_code_includes_prerequisites_and_tracks():
    record = course_by_code("02360343")
    assert record is not None
    assert record["titleHebrew"] == "תורת החישוביות"
    assert len(record["prerequisites"]) == 2
    assert len(record["requiredTracks"]) == 11


def test_tracks_requiring_course_probability():
    tracks = tracks_requiring_course("00940412")
    assert len(tracks) == 9
    assert "track-education-computer-science" in tracks


def test_compose_course_prerequisite_answer():
    text, sources = compose_course_catalog_answer(
        "02360343",
        include_prerequisites=True,
        include_tracks=False,
    )
    assert "02340129" in text
    assert "02340247" in text
    assert "wiki/courses/023-cs/02360343-theory-of-computation.md" in sources[0]


def test_compose_compound_course_answer_lists_all_tracks():
    text, _sources = compose_course_catalog_answer(
        "02360343",
        include_prerequisites=True,
        include_tracks=True,
    )
    assert "track-computer-science-general-4year" in text
    assert "Total tracks requiring this course: 11" in text


def test_track_credit_breakdown_general_cs():
    text, sources = compose_track_credit_breakdown_answer("023023")
    assert "155" in text
    assert "87" in text
    assert "56" in text
    assert "12" in text
    assert "track-computer-science-general-4year" in sources[0]


def test_regulation_moed_answer_uses_last_grade():
    text, sources = compose_regulation_moed_answer(
        "I took Moed A and got 72. Then Moed B and got 58. What is my official final grade?"
    )
    assert "official final grade is 58" in text
    assert "72" in text  # mentioned as superseded Moed A grade
    assert "Section 5.3" in text
    assert "regulations-undergraduate" in sources[0]


def test_non_regular_standing_lists_eight_conditions():
    text, _sources = compose_non_regular_standing_answer()
    for number in range(1, 9):
        assert f"{number}." in text
    assert "OR logic" in text or "any one" in text


def test_try_compose_deterministic_course_question_analysis():
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "02360343"},
        academic_context={"course": {"courseNumber": "02360343", "title": "Theory of Computation"}},
        validation=ContextValidation(status="valid"),
    )
    analysis = analyze_course_question(
        context=context,
        user_message="What are the prerequisites for Theory of Computation (course 02360343)? And which tracks require it?",
    )
    assert analysis.use_catalog_answer is True
    assert "02340129" in analysis.headline
    assert "track-computer-science-general-4year" in analysis.headline


def test_try_compose_deterministic_regulation():
    result = try_compose_deterministic_answer(
        "What are all the conditions under which a Technion undergraduate student is placed in Non-Regular Academic Standing (מצב אקדמי לא תקין)? I want the complete list."
    )
    assert result is not None
    text, _sources = result
    assert "Condition" not in text  # numbered list uses digits
    assert "8 conditions" in text or "following 8 conditions" in text
