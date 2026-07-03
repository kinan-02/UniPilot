"""Phase 7 agentic retrieval: decomposition, refinement, and merging."""

from __future__ import annotations

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.agent.query_decomposer import decompose_retrieval_query
from app.agent.retrieval_gaps import identify_retrieval_gaps
from app.agent.retrieval_refiner import (
    attempt_mode_for_index,
    refine_decomposed_queries,
    wiki_profile_for_attempt,
)
from app.agent.schemas import AgentContextPack, ContextValidation, WikiContextSnippet
from app.agent.wiki_context_merger import merge_wiki_snippets


def test_decompose_course_question_with_prereq_and_offering():
    queries = decompose_retrieval_query(
        user_message="Can I take 00940219 next semester and what are the prerequisites?",
        intent="course_question",
        entities={"courseNumber": "00940219", "targetSemesterCode": "2025-2"},
        base_wiki_query="00940219 prerequisites requirements",
    )
    facets = {query.facet for query in queries}
    texts = " ".join(query.text.lower() for query in queries)
    assert "prerequisite" in texts
    assert "offering" in facets
    assert len(queries) <= 4


def test_decompose_splits_compound_requirement_question():
    queries = decompose_retrieval_query(
        user_message="Explain DNE electives and also faculty elective pool rules",
        intent="requirement_explanation",
        entities={"track": "track-data-information-engineering"},
        base_wiki_query="requirement bucket elective explanation",
    )
    assert len(queries) >= 2
    assert any(query.source == "split" for query in queries)


def test_identify_missing_wiki_gap():
    pack = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="requirement_explanation",
        entities={},
        user_context={"profile": {"track": "track-test"}},
        academic_context={},
        retrieved_wiki_context=[],
        validation=ContextValidation(
            status="partial",
            warnings=["requirement_explanation_context_thin"],
        ),
    )
    gaps = identify_retrieval_gaps(pack)
    assert "missing_wiki" in gaps


def test_refine_queries_adds_retry_on_missing_wiki():
    refined = refine_decomposed_queries(
        user_message="Explain elective requirements",
        intent="requirement_explanation",
        entities={"track": "track-data-information-engineering"},
        base_wiki_query="requirement bucket elective explanation",
        gaps=["missing_wiki"],
        attempt_index=1,
    )
    assert len(refined) >= 2
    assert any(query.source == "refined" for query in refined)


def test_attempt_mode_progression():
    assert attempt_mode_for_index(0) == "strict"
    assert attempt_mode_for_index(1) == "relaxed"
    assert attempt_mode_for_index(2) == "fallback"


def test_wiki_profile_switches_to_fallback_on_third_attempt():
    assert wiki_profile_for_attempt(
        attempt_index=2,
        default_profile_name="requirement_explanation",
    ) == "fallback_academic_search"


def test_merge_wiki_snippets_dedupes_and_keeps_higher_score():
    first = WikiContextSnippet(
        source_file="entities/tracks/track-test.md",
        section_title="Electives",
        content="first",
        score=1.0,
    )
    second = WikiContextSnippet(
        source_file="entities/tracks/track-test.md",
        section_title="Electives",
        content="better",
        score=4.0,
    )
    third = WikiContextSnippet(
        source_file="entities/tracks/track-test.md",
        section_title="Credits",
        content="credits",
        score=2.0,
    )
    merged = merge_wiki_snippets([first], [second, third], max_snippets=2)
    assert len(merged) == 2
    assert merged[0].content == "better"
    assert merged[0].score == 4.0


def test_build_wiki_explanation_context_formats_sections():
    summary = build_wiki_explanation_context(
        [
            WikiContextSnippet(
                page_title="DNE Track",
                section_title="Electives",
                content="Students must complete 24.5 elective credits.",
            )
        ]
    )
    assert "DNE Track" in summary
    assert "24.5" in summary
