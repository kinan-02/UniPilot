"""Profile-aware hybrid reranking for wiki chunks (Agent_RAG_tuning.md §20)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, Iterable

from app.retrieval.obsidian_wiki_indexer import WikiChunk
from app.retrieval.profiles import RerankBoosts, RetrievalProfile, get_rerank_boosts

if TYPE_CHECKING:
    from app.config import Settings

_TOKEN = re.compile(r"[\w\u0590-\u05FF]+", re.UNICODE)
_WIKI_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?\]\]")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text or "") if len(token) > 1]


def embedding_text(chunk: WikiChunk) -> str:
    return "\n".join(
        [
            f"Page: {chunk.page_title}",
            f"Heading path: {' > '.join(chunk.heading_path)}",
            f"Catalog year: {chunk.catalog_year or ''}",
            f"Degree program: {chunk.degree_program or ''}",
            f"Track: {chunk.track or ''}",
            "",
            "Content:",
            chunk.content,
        ]
    )


def bm25_score(chunk: WikiChunk, query_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0

    haystack = " ".join(
        [
            chunk.page_title,
            chunk.section_title,
            chunk.content,
            " ".join(chunk.course_numbers_mentioned),
        ]
    ).lower()
    haystack_tokens = tokenize(haystack)
    if not haystack_tokens:
        return 0.0

    doc_freq = Counter(haystack_tokens)
    score = 0.0
    for token in query_tokens:
        tf = doc_freq.get(token, 0)
        if tf:
            score += 1.0 + math.log(1.0 + tf)
        if token in chunk.section_title.lower():
            score += 2.0
        for number in chunk.course_numbers_mentioned:
            if token == number.lower() or token in number:
                score += 3.0
    return score


def semantic_similarity_score(
    chunk: WikiChunk,
    query_tokens: list[str],
    *,
    query: str | None = None,
    semantic_override: float | None = None,
) -> float:
    if semantic_override is not None:
        return max(0.0, semantic_override)
    if not query_tokens:
        return 0.0
    doc_tokens = set(tokenize(embedding_text(chunk)))
    if not doc_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in doc_tokens)
    return overlap / max(1, len(set(query_tokens)))


def apply_metadata_boosts(
    chunk: WikiChunk,
    *,
    query_tokens: list[str],
    entities: dict[str, Any],
    user_context: dict[str, Any],
    boosts: RerankBoosts,
) -> float:
    adjustment = 0.0
    profile = user_context.get("profile") or {}
    course_number = str(entities.get("courseNumber") or "")
    if course_number and (
        chunk.primary_course_number == course_number
        or course_number in chunk.course_numbers_mentioned
    ):
        adjustment += boosts.exactCourseNumberBoost

    track = str(profile.get("track") or "").lower()
    if track and chunk.track and track in chunk.track.lower():
        adjustment += boosts.trackMatchBoost
    elif track and track not in (chunk.track or "").lower() and chunk.track:
        adjustment += boosts.wrongTrackPenalty

    catalog_year = profile.get("catalogYear")
    if catalog_year is not None and chunk.catalog_year:
        if str(catalog_year) in str(chunk.catalog_year):
            adjustment += boosts.catalogYearMatchBoost
        else:
            adjustment += boosts.wrongCatalogYearPenalty

    degree_program = str(profile.get("degreeProgram") or "").lower()
    if degree_program and chunk.degree_program and degree_program in chunk.degree_program.lower():
        adjustment += boosts.degreeProgramMatchBoost

    target_semester = str(entities.get("targetSemesterCode") or "")
    if target_semester and target_semester not in chunk.content and "semester" in query_tokens:
        adjustment += boosts.wrongSemesterPenalty * 0.25

    topic = str(entities.get("topic") or "").strip()
    normalized_path = chunk.source_file.replace("\\", "/").lower()
    if topic and "courses/009-dds/" in normalized_path:
        adjustment += boosts.sourcePriorityBoost * 2.0
    if topic and (
        normalized_path.endswith("/log.md")
        or normalized_path == "log.md"
        or normalized_path.endswith("/index.md")
    ):
        adjustment -= boosts.sourcePriorityBoost * 4.0

    profile_name = str(user_context.get("profileName") or "")
    if profile_name in {"catalog_requirement_lookup", "requirement_explanation"}:
        if track and f"entities/tracks/{track}.md" in normalized_path:
            adjustment += boosts.sourcePriorityBoost * 6.0
        elif track and "entities/tracks/" in normalized_path:
            adjustment += boosts.wrongTrackPenalty
        faculty_slug = str(entities.get("faculty") or "").strip().lower()
        if faculty_slug and f"entities/faculties/{faculty_slug}.md" in normalized_path:
            adjustment += boosts.sourcePriorityBoost * 6.0
        if "faculty" in query_tokens and "entities/faculties/" in normalized_path:
            adjustment += boosts.sourcePriorityBoost * 4.0
        if "courses/" in normalized_path:
            adjustment -= boosts.sourcePriorityBoost * 3.0
        if "entities/programs/" in normalized_path:
            adjustment -= boosts.sourcePriorityBoost * 2.0

    return adjustment


def hybrid_score_chunk(
    chunk: WikiChunk,
    *,
    query: str,
    profile: RetrievalProfile,
    entities: dict[str, Any] | None = None,
    user_context: dict[str, Any] | None = None,
    boosts: RerankBoosts | None = None,
    semantic_override: float | None = None,
) -> float:
    query_tokens = tokenize(query)
    keyword = bm25_score(chunk, query_tokens)
    semantic = semantic_similarity_score(
        chunk,
        query_tokens,
        query=query,
        semantic_override=semantic_override,
    )
    score = (
        profile.hybrid_keyword_weight_normalized * keyword
        + profile.hybrid_vector_weight_normalized * semantic
    )
    score += apply_metadata_boosts(
        chunk,
        query_tokens=query_tokens,
        entities=entities or {},
        user_context=user_context or {},
        boosts=boosts or get_rerank_boosts(),
    )
    return score


def rerank_chunks(
    chunks: Iterable[WikiChunk],
    *,
    query: str,
    limit: int = 5,
    profile: RetrievalProfile | None = None,
    entities: dict[str, Any] | None = None,
    user_context: dict[str, Any] | None = None,
    wiki_root: str | None = None,
    settings: "Settings | None" = None,
) -> list[tuple[WikiChunk, float]]:
    from app.config import get_settings
    from app.retrieval.cache_warmup import resolve_wiki_root
    from app.retrieval.embedding_service import (
        build_semantic_score_map,
        cosine_similarity,
        embed_query_cached,
    )
    from app.retrieval.profiles import get_profile
    from app.retrieval.wiki_vector_index import get_wiki_vector_index

    active_profile = profile or get_profile("fallback_academic_search")
    candidate_limit = max(active_profile.rerankCandidateLimit, limit)
    chunk_list = list(chunks)
    semantic_by_chunk_id: dict[int, float] = {}
    settings = settings or get_settings()
    resolved_root = resolve_wiki_root(wiki_root) if wiki_root else ""
    index = (
        get_wiki_vector_index(wiki_root=resolved_root, settings=settings)
        if resolved_root and settings.wiki_vector_index_enabled()
        else None
    )
    if index is not None:
        query_vector = embed_query_cached(
            query,
            settings.resolved_embedding_api_key(),
            settings.resolved_embedding_base_url(),
            settings.resolved_embedding_model(),
        )
        if query_vector:
            for chunk in chunk_list:
                chunk_vector = index.vector_for_chunk(chunk)
                if chunk_vector:
                    semantic_by_chunk_id[id(chunk)] = cosine_similarity(
                        list(query_vector),
                        chunk_vector,
                    )
    elif settings.embeddings_available() and chunk_list:
        score_map = build_semantic_score_map(
            query=query,
            document_texts=[embedding_text(chunk) for chunk in chunk_list],
            settings=settings,
        )
        if score_map is not None:
            for index_pos, chunk in enumerate(chunk_list):
                semantic_by_chunk_id[id(chunk)] = score_map.get(index_pos, 0.0)

    scored = [
        (
            chunk,
            hybrid_score_chunk(
                chunk,
                query=query,
                profile=active_profile,
                entities=entities,
                user_context=user_context,
                semantic_override=semantic_by_chunk_id.get(id(chunk)),
            ),
        )
        for chunk in chunk_list
    ]
    scored = [(chunk, score) for chunk, score in scored if score > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:candidate_limit][: max(1, limit)]


def extract_wiki_links(chunk: WikiChunk) -> list[str]:
    links: list[str] = []
    for match in _WIKI_LINK.finditer(chunk.content):
        label = match.group(1).strip()
        if label:
            links.append(label)
    return links


def expand_linked_chunks(
    ranked: list[tuple[WikiChunk, float]],
    *,
    all_chunks: list[WikiChunk],
    depth: int,
    max_linked: int,
    query: str,
    profile: RetrievalProfile,
    entities: dict[str, Any] | None = None,
    user_context: dict[str, Any] | None = None,
) -> list[tuple[WikiChunk, float]]:
    if depth <= 0 or max_linked <= 0 or not ranked:
        return ranked

    selected_ids = {id(chunk) for chunk, _ in ranked}
    by_title: dict[str, list[WikiChunk]] = {}
    for chunk in all_chunks:
        by_title.setdefault(chunk.page_title.lower(), []).append(chunk)

    linked: list[tuple[WikiChunk, float]] = []
    boosts = get_rerank_boosts()
    for chunk, score in ranked:
        for link_label in extract_wiki_links(chunk):
            candidates = by_title.get(link_label.lower(), [])
            for candidate in candidates:
                if id(candidate) in selected_ids:
                    continue
                link_score = hybrid_score_chunk(
                    candidate,
                    query=query,
                    profile=profile,
                    entities=entities,
                    user_context=user_context,
                    boosts=boosts,
                ) + boosts.linkRelevanceBoost
                if link_score <= 0:
                    continue
                linked.append((candidate, link_score))
                selected_ids.add(id(candidate))
                if len(linked) >= max_linked:
                    break
            if len(linked) >= max_linked:
                break

    merged = list(ranked)
    for item in sorted(linked, key=lambda pair: pair[1], reverse=True):
        merged.append(item)
    merged.sort(key=lambda pair: pair[1], reverse=True)
    return merged[: profile.finalTopN]
