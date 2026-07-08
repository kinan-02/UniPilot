"""Entity/track page ranking for requirement retrieval profiles."""

from __future__ import annotations

import pytest

from app.retrieval.hybrid_wiki_retriever import (
    _infer_faculty_slug_from_query,
    _is_faculty_entity_chunk,
    _is_track_entity_chunk,
    retrieve_wiki_context_with_profile,
)
from app.retrieval.obsidian_wiki_indexer import WikiChunk, reset_wiki_index_cache
from app.retrieval.profiles import get_profile, reset_profile_config_cache


def _chunk(source_file: str, *, content: str = "requirements electives credits") -> WikiChunk:
    return WikiChunk(
        source_file=source_file,
        page_title="Test",
        section_title="Section",
        heading_path=("Test", "Section"),
        content=content,
    )


def test_track_entity_chunk_detection():
    chunk = _chunk("entities/tracks/track-data-information-engineering.md")
    assert _is_track_entity_chunk(chunk, "track-data-information-engineering")
    assert not _is_track_entity_chunk(chunk, "track-industrial-engineering-management")


def test_faculty_entity_chunk_detection():
    chunk = _chunk("entities/faculties/faculty-dds.md")
    assert _is_faculty_entity_chunk(chunk, "faculty-dds")
    assert not _is_faculty_entity_chunk(chunk, "faculty-medicine")


def test_entity_source_id_ignores_embedded_course_numbers():
    from app.retrieval.hybrid_wiki_retriever import _wiki_source_id

    chunk = _chunk(
        "entities/tracks/track-data-information-engineering.md",
        content="Required course 00940345 and elective 00940288",
    )
    assert _wiki_source_id(chunk) == "wiki:entities:tracks:track-data-information-engineering"


    assert _infer_faculty_slug_from_query("DDS faculty elective pool rules") == "faculty-dds"
    assert _infer_faculty_slug_from_query("Explain DNE elective requirements") is None


@pytest.fixture
def dds_wiki_dir(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    track_dir = wiki / "entities" / "tracks"
    faculty_dir = wiki / "entities" / "faculties"
    course_dir = wiki / "courses" / "009-dds"
    program_dir = wiki / "entities" / "programs"
    for directory in (track_dir, faculty_dir, course_dir, program_dir):
        directory.mkdir(parents=True)

    (track_dir / "track-data-information-engineering.md").write_text(
        """---
title: Data & Information Engineering
aliases: [DNE]
---

# Track

## Elective bucket
DNE electives require at least 24.5 credits from approved pool.
""",
        encoding="utf-8",
    )
    (track_dir / "track-industrial-engineering-management.md").write_text(
        """---
title: Industrial Engineering & Management
aliases: [IEM]
---

# Track

## Credit breakdown
Total credits required: 155 for IEM track students.
""",
        encoding="utf-8",
    )
    (track_dir / "track-information-systems-engineering.md").write_text(
        """---
title: Information Systems Engineering
aliases: [ISE]
---

# Track

## Required courses
ISE track required courses list for undergraduate students.
""",
        encoding="utf-8",
    )
    (faculty_dir / "faculty-dds.md").write_text(
        """---
title: Faculty of Data Science and Decisions
aliases: [DDS]
---

# Faculty

## Faculty electives
DDS faculty elective pool rules and approval process.
""",
        encoding="utf-8",
    )
    (course_dir / "03350002-elective.md").write_text(
        """---
title: Elective Course
---

# Elective
General elective requirements and credits.
""",
        encoding="utf-8",
    )
    (program_dir / "program-energy.md").write_text(
        """---
title: Energy Program
---

# Program
Credits required for energy-focused students.
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("ACADEMIC_WIKI_PATH", str(wiki))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()
    yield wiki
    get_settings.cache_clear()
    reset_wiki_index_cache()
    reset_profile_config_cache()


def _source_id(snippet: dict) -> str:
    source_file = snippet["sourceFile"].replace("/", ":").removesuffix(".md")
    return f"wiki:{source_file}"


@pytest.mark.asyncio
async def test_dne_track_ranks_first_for_elective_explanation(dds_wiki_dir):
    profile = get_profile("requirement_explanation")
    snippets, _, metadata = await retrieve_wiki_context_with_profile(
        query="Explain DNE elective requirements",
        user_context={
            "profile": {
                "track": "track-data-information-engineering",
                "catalogYear": 2025,
            }
        },
        entities={},
        profile=profile,
    )
    assert snippets
    assert metadata.get("entityLookupTarget") == "track-data-information-engineering"
    assert _source_id(snippets[0]) == "wiki:entities:tracks:track-data-information-engineering"


@pytest.mark.asyncio
async def test_iem_track_ranks_first_for_credit_query(dds_wiki_dir):
    profile = get_profile("catalog_requirement_lookup")
    snippets, _, _metadata = await retrieve_wiki_context_with_profile(
        query="How many credits are required for IEM track?",
        user_context={
            "profile": {
                "track": "track-industrial-engineering-management",
                "catalogYear": 2025,
            }
        },
        entities={},
        profile=profile,
    )
    assert _source_id(snippets[0]) == "wiki:entities:tracks:track-industrial-engineering-management"


@pytest.mark.asyncio
async def test_ise_track_ranks_first_for_required_courses_query(dds_wiki_dir):
    profile = get_profile("catalog_requirement_lookup")
    snippets, _, _metadata = await retrieve_wiki_context_with_profile(
        query="ISE track required courses list",
        user_context={
            "profile": {
                "track": "track-information-systems-engineering",
                "catalogYear": 2025,
            }
        },
        entities={},
        profile=profile,
    )
    assert _source_id(snippets[0]) == "wiki:entities:tracks:track-information-systems-engineering"


@pytest.mark.asyncio
async def test_faculty_dds_ranks_first_for_faculty_elective_query(dds_wiki_dir):
    profile = get_profile("requirement_explanation")
    snippets, _, metadata = await retrieve_wiki_context_with_profile(
        query="DDS faculty elective pool rules",
        user_context={
            "profile": {
                "track": "track-data-information-engineering",
                "catalogYear": 2025,
            }
        },
        entities={},
        profile=profile,
    )
    assert metadata.get("entityLookupTarget") == "faculty-dds"
    assert _source_id(snippets[0]) == "wiki:entities:faculties:faculty-dds"
