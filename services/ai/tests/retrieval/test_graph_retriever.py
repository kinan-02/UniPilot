"""Unit tests for academic graph retrieval (wiki + semester JSON)."""

from __future__ import annotations

import pytest

from app.retrieval.intent_types import AgentIntent
from app.config import Settings
from app.retrieval.graph_retriever import (
    plan_graph_retrieval_actions,
    retrieve_graph_context_with_profile,
    warmup_graph_engine,
)
from app.retrieval.profiles import get_profile


def _graph_settings() -> Settings:
    return Settings(
        academic_wiki_path="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/catalog_valut/catalog_valut/wiki",
        academic_technion_raw_dir="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/raw/technion",
        **{
            # These fields declare a `validation_alias` — constructing via the
            # plain python attribute name is silently ignored by pydantic
            # (falls back to each field's own default) rather than raising,
            # which is an easy, silent trap. Use the alias form for anything
            # that actually needs to override the default.
            "ACADEMIC_DEFAULT_SEMESTER_FILE": "courses_2025_201.json",
            "AGENT_GRAPH_RETRIEVAL_ENABLED": True,
            # Explicitly off regardless of the developer's local .env — these
            # tests must exercise the deterministic BM25-only fallback, not
            # make real network embedding calls. `search_wiki`'s reranking now
            # touches embeddings when they're configured process-wide (see
            # `AcademicGraphEngine.search_wiki`), and a real network round-trip
            # per test call is both slow and non-deterministic in CI.
            "EMBEDDING_ENABLED": False,
        },
    )


@pytest.mark.parametrize(
    ("intent", "entities", "expected_intents"),
    [
        (
            "course_question",
            {"courseNumber": "00440148"},
            {"course_info", "prerequisites", "schedule", "syllabus", "structure"},
        ),
        (
            "prerequisite_check",
            {"courseNumber": "00440148"},
            {"course_info", "prerequisites", "eligibility"},
        ),
        (
            "program_minor_lookup",
            {},
            {"wiki_page", "wiki_section"},
        ),
        (
            "track_structure_lookup",
            {},
            {"wiki_page", "wiki_section"},
        ),
        (
            "regulation_lookup",
            {},
            {"wiki_section"},
        ),
    ],
)
def test_plan_graph_retrieval_actions(
    intent: AgentIntent,
    entities: dict,
    expected_intents: set[str],
) -> None:
    from app.config import Settings
    from app.retrieval.graph_engine.graph_registry import graph_registry

    settings = Settings(
        academic_wiki_path="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/catalog_valut/catalog_valut/wiki",
        academic_technion_raw_dir="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/raw/technion",
        academic_default_semester_file="courses_2025_201.json",
        agent_graph_retrieval_enabled=True,
    )
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")
    engine = graph_registry.get_engine(settings)
    query = {
        "program_minor_lookup": "Inter-Faculty Robotics Minor admission requirements",
        "track_structure_lookup": "Biomedical Engineering BSc track credit breakdown",
        "regulation_lookup": "maximum number of credits without special approval",
    }.get(intent, "00440148 prerequisites")
    actions = plan_graph_retrieval_actions(
        intent=intent,
        entities=entities,
        query=query,
        engine=engine,
    )
    assert {action["intent"] for action in actions} >= expected_intents


@pytest.mark.parametrize(
    ("intent", "query"),
    [
        (
            "track_structure_lookup",
            "How many physical education credits do I need to graduate from a "
            "Technion B.Sc., and is there a maximum I can take per semester?",
        ),
        (
            "program_minor_lookup",
            "What GPA do I need to graduate cum laude or summa cum laude from a "
            "Technion B.Sc. program?",
        ),
    ],
)
def test_program_minor_and_track_structure_fall_back_to_wiki_search(
    intent: AgentIntent, query: str
) -> None:
    """Regression test: `program_minor_lookup`/`track_structure_lookup` used
    to return early with only slug-guessed `wiki_page`/`wiki_section`
    actions and no way to recover when the guessed slug was wrong (or a
    misclassified question landed in this intent at all) -- confirmed in
    practice for both queries above, which are genuinely about undergraduate
    regulations, not a specific minor/track page. A `wiki_search` fallback
    action must now always be planned so free-text search over the whole
    corpus gets a chance."""
    from app.config import Settings
    from app.retrieval.graph_engine.graph_registry import graph_registry

    settings = Settings(
        academic_wiki_path="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/catalog_valut/catalog_valut/wiki",
        academic_technion_raw_dir="/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/raw/technion",
        academic_default_semester_file="courses_2025_201.json",
        agent_graph_retrieval_enabled=True,
    )
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")
    engine = graph_registry.get_engine(settings)
    actions = plan_graph_retrieval_actions(intent=intent, entities={}, query=query, engine=engine)
    assert any(action["intent"] == "wiki_search" for action in actions)


@pytest.mark.asyncio
async def test_structural_blocks_get_fixed_confidence_and_search_blocks_get_real_score() -> None:
    """Regression test: `retrieve_graph_context_with_profile` used to score
    every block as `len(blocks) - index*0.15` — an ordinal position number,
    not a relevance signal. Structural/exact-lookup blocks (resolved by
    slug/course-id) should get a fixed high confidence; `wiki_search` blocks
    should carry their own real BM25/embedding-derived score.
    """
    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    warmup_graph_engine(settings=settings)
    profile = get_profile("course_exact_lookup")

    snippets, _, metadata = await retrieve_graph_context_with_profile(
        query="00440148 prerequisites",
        user_context={"completedCourses": [{"courseNumber": "00440105"}]},
        entities={"courseNumber": "00440148"},
        profile=profile,
        settings=settings,
        intent="course_question",
    )

    assert snippets, "expected at least one structural snippet (course_info/prerequisites)"
    # All returned snippets here are structural (course_info/prerequisites) —
    # exact lookups resolved by course id, not ranked search results.
    assert all(snippet["score"] == 1.0 for snippet in snippets)
    assert metadata["topScore"] == 1.0

    # A general free-text query with no resolvable slug/course-id routes
    # entirely through `wiki_search` — its score must NOT be the fixed 1.0
    # structural value; it should be a real (BM25-derived) score.
    search_snippets, _, search_metadata = await retrieve_graph_context_with_profile(
        query="student rights ombudsman procedure",
        user_context={},
        entities={},
        profile=get_profile("general_catalog_question"),
        settings=settings,
        intent="general_academic_question",
    )
    if search_snippets:
        assert any(snippet["score"] != 1.0 for snippet in search_snippets)


@pytest.mark.asyncio
async def test_retrieve_graph_context_returns_snippets() -> None:
    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    warmup_graph_engine(settings=settings)
    profile = get_profile("course_exact_lookup")

    snippets, provenance, metadata = await retrieve_graph_context_with_profile(
        query="00440148 prerequisites",
        user_context={"completedCourses": [{"courseNumber": "00440105"}]},
        entities={"courseNumber": "00440148"},
        profile=profile,
        settings=settings,
        intent="course_question",
    )

    assert metadata.get("retrievalBackend") == "academic_graph"
    assert metadata.get("blockCount", 0) >= 1
    assert len(snippets) >= 1
    assert snippets[0].get("content")
    assert len(provenance) >= 1


@pytest.mark.asyncio
async def test_retrieve_graph_context_enforces_max_context_tokens() -> None:
    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    warmup_graph_engine(settings=settings)
    # A generous budget as a baseline, then a tiny one to force trimming.
    generous_profile = get_profile("course_exact_lookup").model_copy(
        update={"wikiChunksFinal": 5, "maxContextTokens": 100_000}
    )
    tiny_profile = generous_profile.model_copy(update={"maxContextTokens": 20})

    query_kwargs = dict(
        query="00440148 prerequisites",
        user_context={"completedCourses": [{"courseNumber": "00440105"}]},
        entities={"courseNumber": "00440148"},
        settings=settings,
        intent="course_question",
    )

    baseline_snippets, _, baseline_metadata = await retrieve_graph_context_with_profile(
        profile=generous_profile, **query_kwargs
    )
    trimmed_snippets, _, trimmed_metadata = await retrieve_graph_context_with_profile(
        profile=tiny_profile, **query_kwargs
    )

    assert len(baseline_snippets) >= 1
    assert len(trimmed_snippets) <= len(baseline_snippets)
    assert trimmed_metadata["estimatedContextTokens"] <= baseline_metadata["estimatedContextTokens"]
    # Never trims away entirely — always keeps at least the top result.
    assert len(trimmed_snippets) >= 1


def test_execute_retrievals_does_not_rebuild_graph_for_same_semester(monkeypatch) -> None:
    """Regression test: `execute_retrievals` used to call `build_graph()`
    unconditionally whenever `semester_filename` was truthy — which is
    almost every call — rebuilding the whole graph redundantly on every turn.
    """
    from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
    from app.retrieval.graph_engine.graph_registry import GraphRegistry

    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    registry = GraphRegistry()
    engine = registry.get_engine(settings)
    semester_filename = engine.active_semester.filename

    build_calls = {"count": 0}
    original_build_graph = AcademicGraphEngine.build_graph

    def _counting_build_graph(self):
        build_calls["count"] += 1
        return original_build_graph(self)

    monkeypatch.setattr(AcademicGraphEngine, "build_graph", _counting_build_graph)

    registry.execute_retrievals(
        [{"intent": "wiki_page", "wiki_slug": "regulations-undergraduate"}],
        semester_filename=semester_filename,
        settings=settings,
    )
    registry.execute_retrievals(
        [{"intent": "wiki_page", "wiki_slug": "regulations-undergraduate"}],
        semester_filename=semester_filename,
        settings=settings,
    )

    assert build_calls["count"] == 0


def test_execute_retrievals_rebuilds_only_when_semester_changes(monkeypatch) -> None:
    from pathlib import Path

    from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
    from app.retrieval.graph_engine.graph_registry import GraphRegistry
    from app.retrieval.graph_engine.semester_catalog import discover_semester_catalogs

    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    registry = GraphRegistry()
    engine = registry.get_engine(settings)

    available = discover_semester_catalogs(Path(settings.academic_technion_raw_dir))
    if len(available) < 2:
        pytest.skip("need at least two semester catalogs to test a real switch")

    # Pick `first` to genuinely differ from whatever semester `get_engine`
    # already loaded by default, so the first `execute_retrievals` call below
    # is a real switch regardless of which semester happens to be configured
    # as the default.
    filenames = [info.filename for info in available]
    active = engine.active_semester.filename if engine.active_semester else None
    first = next(name for name in filenames if name != active)
    second = next(name for name in filenames if name != first)

    build_calls = {"count": 0}
    original_build_graph = AcademicGraphEngine.build_graph

    def _counting_build_graph(self):
        build_calls["count"] += 1
        return original_build_graph(self)

    monkeypatch.setattr(AcademicGraphEngine, "build_graph", _counting_build_graph)

    registry.execute_retrievals([], semester_filename=first, settings=settings)
    assert build_calls["count"] == 1, "switching semester should rebuild once"

    registry.execute_retrievals([], semester_filename=first, settings=settings)
    assert build_calls["count"] == 1, "repeating the same semester should not rebuild again"

    registry.execute_retrievals([], semester_filename=second, settings=settings)
    assert build_calls["count"] == 2, "switching semester again should rebuild once more"


@pytest.mark.asyncio
async def test_wiki_search_action_for_general_question() -> None:
    settings = _graph_settings()
    if not settings.is_graph_configured():
        pytest.skip("graph paths not available")

    profile = get_profile("general_catalog_question")
    snippets, _, metadata = await retrieve_graph_context_with_profile(
        query="student rights ombudsman",
        user_context={},
        entities={},
        profile=profile,
        settings=settings,
        intent="general_academic_question",
    )

    planned = metadata.get("plannedActions") or []
    planned_intents = {action.get("intent") for action in planned}
    assert planned_intents & {"wiki_search", "wiki_page"}
    assert isinstance(snippets, list)
