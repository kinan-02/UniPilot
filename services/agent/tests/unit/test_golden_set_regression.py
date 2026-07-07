"""Golden-set regression hardening tests (Phase 27.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.entity_resolver import resolve_entities
from app.agent.evaluation.final_answer_eval import (
    derive_source_warnings,
    evaluate_fact_deterministic,
    load_golden_answer_cases,
    score_final_answer_case,
)
from app.agent.evaluation.regression_assertions import (
    assert_complete_standing_conditions,
    assert_complete_track_list,
    assert_credit_breakdown_values,
    assert_wiki_sources_grounded,
    deterministic_answer_for_prompt,
    has_eligibility_drift,
    has_track_course_confusion,
    is_eligibility_prompt,
    is_information_lookup_prompt,
)
from app.agent.intent_router import classify_intent
from app.agent.schemas import AgentContextPack, ContextValidation
from app.services.academic_lookup_service import classify_course_question_focus, detect_academic_query_kind
from app.services.course_question_service import analyze_course_question, classify_question_focus

REPO_ROOT = Path(__file__).resolve().parents[4]
WIKI_ROOT = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
GOLDEN_SET = Path(__file__).resolve().parents[2] / "eval_sets" / "eval_cases.json"
PARAPHRASE_SET = Path(__file__).resolve().parents[2] / "eval_sets" / "eval_cases_paraphrase.json"


@pytest.fixture(autouse=True)
def wiki_path(monkeypatch: pytest.MonkeyPatch) -> None:
    if not WIKI_ROOT.is_dir():
        pytest.skip("catalog wiki fixtures unavailable")
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(WIKI_ROOT))
    from app.services import academic_lookup_service as lookup_module

    lookup_module._cached_track_code_index.cache_clear()


# --- Routing: course prerequisite lookup (not eligibility) ---

@pytest.mark.parametrize(
    "prompt",
    [
        "What are the prerequisites for 02360343?",
        "List the prerequisites for Theory of Computation.",
        "For course 02360343, what courses do I need before it?",
        "List the prerequisite courses I need before taking Theory of Computation (02360343).",
    ],
)
def test_prerequisite_prompts_route_to_catalog_not_eligibility(prompt: str) -> None:
    assert classify_course_question_focus(prompt) == "catalog_prerequisites"
    assert classify_question_focus(prompt) == "catalog_prerequisites"
    assert not is_eligibility_prompt(prompt)
    assert is_information_lookup_prompt(prompt)


# --- Routing: reverse required-track lookup ---

@pytest.mark.parametrize(
    "prompt",
    [
        "Which tracks require 00940412?",
        "Where is Probability M mandatory across tracks for 00940412?",
        "Which study programs formally require course 00940412?",
    ],
)
def test_reverse_track_prompts_route_correctly(prompt: str) -> None:
    assert classify_course_question_focus(prompt) == "tracks_requiring"
    assert detect_academic_query_kind(prompt) == "course_tracks_requiring"


def test_hebrew_reverse_track_prompt_routes_correctly() -> None:
    prompt = "בקורס הסתברות מ (00940412) — באילו מסלולי לימוד הוא מוגדר כקורס חובה?"
    assert classify_course_question_focus(prompt) == "tracks_requiring"

@pytest.mark.parametrize(
    "prompt",
    [
        "Can I take 02360343?",
        "Am I eligible for Theory of Computation?",
        "Can I take Theory of Computation (02360343) next semester with my current transcript?",
    ],
)
def test_eligibility_prompts_stay_on_eligibility_branch(prompt: str) -> None:
    assert classify_course_question_focus(prompt) == "eligibility"
    assert is_eligibility_prompt(prompt)
    assert not is_information_lookup_prompt(prompt)


def test_eligibility_analysis_not_catalog_dump() -> None:
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "02360343"},
        user_context={"completedCourses": []},
        academic_context={
            "course": {"courseNumber": "02360343", "title": "Theory of Computation"},
            "prerequisiteResult": {
                "eligible": False,
                "missingPrerequisites": [{"courseNumber": "02340129"}],
            },
        },
        validation=ContextValidation(status="valid"),
    )
    analysis = analyze_course_question(
        context=context,
        user_message="Can I take 02360343?",
    )
    assert analysis.focus == "eligibility"
    assert analysis.use_eligibility_validation is True
    assert analysis.use_catalog_answer is False
    assert "yes — you appear eligible" not in analysis.headline.lower()


# --- Track code disambiguation ---

# `track_structure_lookup` is a more specific intent added after this test was
# written; it now correctly supersedes the old `general_academic_question`
# catch-all for prompts that name a track-code or ask about credit structure.
# "4-year General CS track" alone (no track code, no credits/graduation
# language) still doesn't match `_TRACK_STRUCTURE_PATTERNS`, so it's still the
# general catch-all — that one case is genuinely unchanged.
@pytest.mark.parametrize(
    ("prompt", "expected_intent"),
    [
        ("track code 023023", "track_structure_lookup"),
        ("4-year General CS track", "general_academic_question"),
        ("How many credits do I need to graduate from 023023?", "track_structure_lookup"),
        (
            "I'm on the 4-year General CS track (track code 023023). How many credits do I need to graduate?",
            "track_structure_lookup",
        ),
    ],
)
def test_track_code_prompts_resolve_track_not_course(prompt: str, expected_intent: str) -> None:
    entities = resolve_entities(prompt)
    if "023023" in prompt:
        assert entities.get("trackCode") == "023023" or entities.get("trackSlug")
        assert "courseNumber" not in entities
    result = classify_intent(prompt)
    assert result.intent == expected_intent


# --- Regulation routing ---

@pytest.mark.parametrize(
    "prompt,expected_kind",
    [
        ("Moed A 72, Moed B 58, what is my final grade?", "regulation_moed_grade"),
        ("If I got a lower Moed B, which grade counts?", "regulation_moed_grade"),
        (
            "What are all non-regular academic standing conditions?",
            "regulation_standing_list",
        ),
        (
            "תן לי את הרשימה המלאה של כל התנאים שמכניסים סטודנט למצב אקדמי לא תקין",
            "regulation_standing_list",
        ),
    ],
)
def test_regulation_prompt_kinds(prompt: str, expected_kind: str) -> None:
    assert detect_academic_query_kind(prompt) == expected_kind


# --- No eligibility drift on deterministic composers ---

@pytest.mark.parametrize(
    "prompt,entities",
    [
        ("What are the prerequisites for 02360343?", {"courseNumber": "02360343"}),
        (
            "For course 02360343, what earlier courses are required, and which degree tracks count it as mandatory?",
            {"courseNumber": "02360343"},
        ),
        ("Which tracks require 00940412?", {"courseNumber": "00940412"}),
    ],
)
def test_deterministic_answers_do_not_start_with_eligibility_stub(prompt: str, entities: dict) -> None:
    result = deterministic_answer_for_prompt(prompt, entities=entities)
    assert result is not None
    text, sources = result
    assert not has_eligibility_drift(user_request=prompt, final_answer=text)
    assert sources
    grounded, warnings = assert_wiki_sources_grounded(
        final_answer=text,
        used_sources=[f"Loaded catalog wiki page [{sources[0]}]"],
        expected_pages=[sources[0]],
    )
    assert grounded, warnings


def test_track_breakdown_not_course_not_found() -> None:
    prompt = "track code 023023 credit breakdown for graduation"
    result = deterministic_answer_for_prompt(prompt, entities=resolve_entities(prompt))
    assert result is not None
    text, _sources = result
    assert not has_track_course_confusion(user_request=prompt, final_answer=text)
    assert assert_credit_breakdown_values(text)


# --- Complete list preservation ---

def test_non_regular_standing_preserves_eight_conditions() -> None:
    result = deterministic_answer_for_prompt(
        "List every מצב אקדמי לא תקין trigger for undergraduates."
    )
    assert result is not None
    text, _sources = result
    assert assert_complete_standing_conditions(text, expected=8)


def test_theory_of_computation_lists_eleven_tracks() -> None:
    result = deterministic_answer_for_prompt(
        "Which tracks require 02360343?",
        entities={"courseNumber": "02360343"},
    )
    assert result is not None
    text, _sources = result
    assert assert_complete_track_list(text, minimum=11)
    assert "Total tracks requiring this course: 11" in text


def test_probability_m_lists_nine_tracks() -> None:
    result = deterministic_answer_for_prompt(
        "Which tracks require 00940412?",
        entities={"courseNumber": "00940412"},
    )
    assert result is not None
    text, _sources = result
    assert assert_complete_track_list(text, minimum=9)
    assert "Total tracks requiring this course: 9" in text or "9 tracks" in text


# --- Source grounding on golden + paraphrase sets (deterministic layer) ---

@pytest.mark.parametrize("case_path", [GOLDEN_SET, PARAPHRASE_SET])
def test_eval_sets_load(case_path: Path) -> None:
    cases = load_golden_answer_cases(case_path)
    assert len(cases) >= 5


@pytest.mark.parametrize(
    "prompt,entities,expected_page",
    [
        (
            "What are the prerequisites for 02360343?",
            {"courseNumber": "02360343"},
            "wiki/courses/023-cs/02360343-theory-of-computation.md",
        ),
        (
            "Which tracks require 00940412?",
            {"courseNumber": "00940412"},
            "wiki/courses/009-dds/00940412-probability.md",
        ),
        (
            "How many credits for track code 023023?",
            {"trackCode": "023023"},
            "wiki/entities/tracks/track-computer-science-general-4year.md",
        ),
        (
            "Moed A 72 Moed B 58 final grade?",
            {},
            "wiki/concepts/regulations-undergraduate.md",
        ),
    ],
)
def test_expected_wiki_pages_grounded_in_deterministic_answers(
    prompt: str,
    entities: dict,
    expected_page: str,
) -> None:
    result = deterministic_answer_for_prompt(prompt, entities=entities)
    assert result is not None
    text, sources = result
    used = [f"Loaded catalog wiki page [{sources[0]}]"] if sources else []
    grounded, warnings = assert_wiki_sources_grounded(
        final_answer=text,
        used_sources=used,
        expected_pages=[expected_page],
    )
    assert grounded, warnings


def test_paraphrase_set_metadata_count() -> None:
    cases = load_golden_answer_cases(PARAPHRASE_SET)
    assert len(cases) == 8


def test_eligibility_drift_detector_positive() -> None:
    assert has_eligibility_drift(
        user_request="What are the prerequisites for 02360343?",
        final_answer="Yes — you appear eligible to take course 02360343.",
    )


def test_score_includes_source_warnings_when_ungrounded() -> None:
    case = load_golden_answer_cases(GOLDEN_SET)[0]
    fact_results = [evaluate_fact_deterministic(fact, "02360343") for fact in case.key_facts[:3]]
    scored = score_final_answer_case(
        case,
        final_answer="ungrounded stub",
        fact_results=fact_results,
        used_sources=["mongodb:only"],
    )
    assert scored.source_warnings
    assert any("expected_source_not_evident" in warning for warning in scored.source_warnings)


def test_derive_source_warnings_accepts_wiki_path_in_used_sources() -> None:
    warnings = derive_source_warnings(
        answer="Theory of Computation prerequisites",
        used_sources=["Loaded catalog wiki page [wiki/courses/023-cs/02360343-theory-of-computation.md]"],
        expected_pages=["wiki/courses/023-cs/02360343-theory-of-computation.md"],
    )
    assert warnings == []
