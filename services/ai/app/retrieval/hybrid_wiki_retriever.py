"""LEGACY — Profile-driven hybrid wiki retrieval (BM25 + embeddings).

Not wired into the live agent path. The orchestrator uses
``app.retrieval.graph_retriever`` (wiki graph + semester JSON) instead.
Kept for regression benchmarks and reference.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.retrieval.cache_warmup import resolve_wiki_root
from app.config import Settings, get_settings
from app.retrieval.metadata_filter import filter_wiki_chunks, filters_from_user_context
from app.retrieval.obsidian_wiki_indexer import WikiChunk, load_wiki_chunks
from app.retrieval.profiles import RetrievalProfile, estimate_context_tokens, get_profile
from app.retrieval.provenance import provenance_claim
from app.retrieval.reranker import expand_linked_chunks, rerank_chunks, tokenize
from app.retrieval.wiki_vector_index import get_wiki_vector_index

_REQUIREMENT_PROFILES = frozenset(
    {"catalog_requirement_lookup", "requirement_explanation"}
)


def _wiki_source_id(chunk: WikiChunk) -> str:
    normalized_path = chunk.source_file.replace("\\", "/")
    if normalized_path.startswith("entities/"):
        slug = normalized_path.replace("/", ":").removesuffix(".md")
        return f"wiki:{slug}"
    course_number = chunk.primary_course_number or (
        chunk.course_numbers_mentioned[0] if chunk.course_numbers_mentioned else None
    )
    if course_number:
        return f"wiki:course:{course_number}"
    slug = normalized_path.replace("/", ":").removesuffix(".md")
    return f"wiki:{slug}"


def _is_primary_course_page_chunk(chunk: WikiChunk, course_number: str) -> bool:
    if chunk.primary_course_number == course_number:
        return True
    basename = Path(chunk.source_file).name
    return basename.startswith(f"{course_number}-") or basename == f"{course_number}.md"


def _prioritize_exact_course_chunks(
    ranked: list[tuple[WikiChunk, float]],
    *,
    course_number: str,
) -> list[tuple[WikiChunk, float]]:
    if not course_number:
        return ranked
    primary_matches = [
        item for item in ranked if _is_primary_course_page_chunk(item[0], course_number)
    ]
    if not primary_matches:
        return ranked
    primary_ids = {id(chunk) for chunk, _score in primary_matches}
    remainder = [item for item in ranked if id(item[0]) not in primary_ids]
    return primary_matches + remainder


def _is_requirement_profile(profile: RetrievalProfile) -> bool:
    return profile.profileName in _REQUIREMENT_PROFILES


def _entity_page_path_suffix(*parts: str) -> str:
    return "/".join(part.strip("/").lower() for part in parts if part)


def _is_track_entity_chunk(chunk: WikiChunk, track_slug: str) -> bool:
    slug = track_slug.strip().lower()
    if not slug:
        return False
    path = chunk.source_file.replace("\\", "/").lower()
    target = _entity_page_path_suffix("entities", "tracks", f"{slug}.md")
    return path == target or path.endswith(f"/{target}")


def _is_faculty_entity_chunk(chunk: WikiChunk, faculty_slug: str) -> bool:
    slug = faculty_slug.strip().lower()
    if not slug:
        return False
    path = chunk.source_file.replace("\\", "/").lower()
    target = _entity_page_path_suffix("entities", "faculties", f"{slug}.md")
    return path == target or path.endswith(f"/{target}")


def _infer_faculty_slug_from_query(query: str) -> str | None:
    tokens = set(tokenize(query))
    lowered = query.lower()
    if "faculty" not in tokens:
        return None
    if "dds" in tokens or "faculty-dds" in lowered:
        return "faculty-dds"
    return None


def _prioritize_entity_page_chunks(
    ranked: list[tuple[WikiChunk, float]],
    *,
    track_slug: str | None = None,
    faculty_slug: str | None = None,
) -> list[tuple[WikiChunk, float]]:
    if faculty_slug:
        primary_matches = [
            item for item in ranked if _is_faculty_entity_chunk(item[0], faculty_slug)
        ]
    elif track_slug:
        primary_matches = [
            item for item in ranked if _is_track_entity_chunk(item[0], track_slug)
        ]
    else:
        return ranked
    if not primary_matches:
        return ranked
    primary_ids = {id(chunk) for chunk, _score in primary_matches}
    remainder = [item for item in ranked if id(item[0]) not in primary_ids]
    return primary_matches + remainder


async def retrieve_wiki_context_with_profile(
    *,
    query: str,
    user_context: dict[str, Any],
    entities: dict[str, Any],
    profile: RetrievalProfile | None = None,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]], list[Any], dict[str, Any]]:
    cfg = settings or get_settings()
    active_profile = profile or get_profile("fallback_academic_search")
    metadata: dict[str, Any] = {
        "profileName": active_profile.profileName,
        "query": query,
        "wikiChunksRequested": active_profile.wikiChunksFinal,
        "fallbackUsed": False,
        "semanticMethod": "token_overlap",
        "retrievalAttemptMode": str(user_context.get("retrievalAttemptMode") or "strict"),
    }
    started = time.perf_counter()
    wiki_path = resolve_wiki_root((cfg.academic_wiki_path or "").strip())
    vector_index = None
    if cfg.embeddings_available():
        metadata["semanticMethod"] = "embedding"
        metadata["embeddingProvider"] = "llmod"
        metadata["embeddingModel"] = cfg.resolved_embedding_model()
        if wiki_path and cfg.wiki_vector_index_enabled():
            vector_index = get_wiki_vector_index(wiki_root=wiki_path, settings=cfg)
            if vector_index is not None:
                metadata["vectorIndex"] = "cache"
    if not wiki_path or active_profile.wikiChunksFinal <= 0:
        metadata["latencyMs"] = int((time.perf_counter() - started) * 1000)
        return [], [], metadata

    chunks = list(load_wiki_chunks(wiki_path))
    if not chunks:
        metadata["latencyMs"] = int((time.perf_counter() - started) * 1000)
        return [], [], metadata

    filters = filters_from_user_context(user_context, entities)
    track_slug = str(filters.get("track_slug") or "").strip()
    exact_course_number = str(entities.get("courseNumber") or "").strip()
    faculty_slug = (
        _infer_faculty_slug_from_query(query)
        if _is_requirement_profile(active_profile)
        else None
    )
    entity_lookup_mode = bool(
        _is_requirement_profile(active_profile)
        and active_profile.exactLookupFirst
        and not exact_course_number
        and (faculty_slug or track_slug)
    )
    if entity_lookup_mode:
        if faculty_slug:
            filtered = [
                chunk for chunk in chunks if _is_faculty_entity_chunk(chunk, faculty_slug)
            ]
        else:
            filtered = [
                chunk for chunk in chunks if _is_track_entity_chunk(chunk, track_slug)
            ]
        metadata["entityLookupTarget"] = faculty_slug or track_slug
    else:
        filtered = filter_wiki_chunks(
            chunks,
            track_slug=filters.get("track_slug"),
            catalog_year=filters.get("catalog_year"),
            degree_program=filters.get("degree_program"),
            course_number=filters.get("course_number"),
        )
    exact_lookup_mode = bool(
        active_profile.exactLookupFirst and exact_course_number
    )
    attempt_mode = str(user_context.get("retrievalAttemptMode") or "strict")
    if not exact_lookup_mode and not entity_lookup_mode:
        if attempt_mode == "fallback":
            metadata["fallbackUsed"] = True
            filtered = list(chunks)
        elif attempt_mode == "relaxed" and len(filtered) < 5:
            metadata["fallbackUsed"] = True
            filtered = list(chunks)
    if exact_lookup_mode:
        primary_page_chunks = [
            chunk
            for chunk in filtered
            if _is_primary_course_page_chunk(chunk, exact_course_number)
        ]
        if primary_page_chunks:
            filtered = primary_page_chunks
    rerank_context = {
        **user_context,
        "profileName": active_profile.profileName,
    }
    if not filtered and chunks and not (
        active_profile.exactLookupFirst
        and (
            str(entities.get("courseNumber") or "").strip()
            or entity_lookup_mode
        )
    ):
        metadata["fallbackUsed"] = True
        filtered = list(chunks)
        rerank_context = {"profileName": active_profile.profileName}

    candidate_pool = (
        list(filtered)
        if exact_lookup_mode or entity_lookup_mode
        else filtered[: max(active_profile.bm25TopK + active_profile.vectorTopK, 20)]
    )
    if vector_index is not None and filtered and not exact_lookup_mode:
        from app.retrieval.embedding_service import embed_query_cached

        query_vector = embed_query_cached(
            query,
            cfg.resolved_embedding_api_key(),
            cfg.resolved_embedding_base_url(),
            cfg.resolved_embedding_model(),
        )
        if query_vector:
            semantic_hits = vector_index.semantic_scores(
                list(query_vector),
                limit=active_profile.vectorTopK,
            )
            if semantic_hits:
                seen = {id(chunk) for chunk in candidate_pool}
                for chunk, _score in semantic_hits:
                    if id(chunk) not in seen:
                        candidate_pool.append(chunk)
                        seen.add(id(chunk))

    ranked = rerank_chunks(
        candidate_pool,
        query=query,
        limit=active_profile.finalTopN,
        profile=active_profile,
        entities=entities,
        user_context=rerank_context,
        wiki_root=wiki_path,
    )
    ranked = expand_linked_chunks(
        ranked,
        all_chunks=chunks,
        depth=active_profile.linkExpansionDepth,
        max_linked=active_profile.maxLinkedChunks,
        query=query,
        profile=active_profile,
        entities=entities,
        user_context=rerank_context,
    )
    if exact_lookup_mode:
        ranked = _prioritize_exact_course_chunks(
            ranked,
            course_number=exact_course_number,
        )
    elif entity_lookup_mode:
        ranked = _prioritize_entity_page_chunks(
            ranked,
            track_slug=track_slug if not faculty_slug else None,
            faculty_slug=faculty_slug,
        )

    wiki_limit = max(1, active_profile.wikiChunksFinal)
    trimmed = ranked[:wiki_limit]
    snippets: list[dict[str, Any]] = []
    provenance: list[Any] = []
    for chunk, score in trimmed:
        snippet = chunk.to_snippet_dict(score=score)
        snippets.append(snippet)
        provenance.append(
            provenance_claim(
                claim=f"Retrieved wiki section '{snippet.get('sectionTitle')}'",
                source_type="catalog_wiki",
                source_id=_wiki_source_id(chunk),
                retrieval_method="metadata_filtered_hybrid_search",
                confidence=min(1.0, float(score) / 10.0),
                field_path="retrievedWikiContext",
            )
        )

    snippets = _trim_to_token_budget(snippets, active_profile.maxContextTokens)

    metadata.update(
        {
            "retrievedCount": len(snippets),
            "estimatedContextTokens": estimate_context_tokens(snippets),
            "topScore": float(snippets[0].get("score") or 0) if snippets else 0.0,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "sourceIds": [_wiki_source_id(chunk) for chunk, _ in trimmed],
        }
    )
    return snippets, provenance, metadata


def _trim_to_token_budget(snippets: list[dict[str, Any]], max_tokens: int) -> list[dict[str, Any]]:
    if max_tokens <= 0:
        return snippets
    kept: list[dict[str, Any]] = []
    used = 0
    for snippet in snippets:
        tokens = estimate_context_tokens([snippet])
        if used + tokens > max_tokens and kept:
            break
        kept.append(snippet)
        used += tokens
    return kept


async def retrieve_wiki_context(
    *,
    query: str,
    user_context: dict[str, Any],
    entities: dict[str, Any],
    limit: int | None = None,
    profile: RetrievalProfile | None = None,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Backward-compatible wiki retrieval wrapper."""
    active = profile or get_profile("fallback_academic_search")
    if limit is not None:
        active = active.model_copy(update={"wikiChunksFinal": limit})
    snippets, provenance, _metadata = await retrieve_wiki_context_with_profile(
        query=query,
        user_context=user_context,
        entities=entities,
        profile=active,
        settings=settings,
    )
    return snippets, provenance
