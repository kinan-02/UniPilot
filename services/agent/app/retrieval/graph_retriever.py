"""Primary agent retrieval: wiki graph + semester JSON (replaces legacy hybrid RAG)."""

from __future__ import annotations

import re
import time
from typing import Any

from app.agent.schemas import AgentIntent
from app.config import Settings, get_settings
from app.retrieval.entity_slug_registry import (
    residual_search_query,
    slugs_from_entities,
)
from app.retrieval.graph_engine.graph_registry import graph_registry
from app.retrieval.graph_engine.semester_catalog import resolve_semester_from_query
from app.retrieval.profiles import RetrievalProfile, estimate_context_tokens
from app.retrieval.provenance import provenance_claim

_REGULATION_REASONING_RE = re.compile(
    r"\b(dual degree|second degree|additional degree|both degrees|two degrees|0\.75)\b",
    re.I,
)

# Block intents resolved by exact slug/course-id lookup rather than ranked
# search — "was this the right block" isn't a relevance question for these,
# so they get a fixed high confidence score instead of a search-derived one.
# `wiki_search` (and any future genuinely-ranked intent) is deliberately
# excluded — it's scored from its own real reranker score instead.
_STRUCTURAL_BLOCK_INTENTS = frozenset(
    {
        "course_info",
        "prerequisites",
        "eligibility",
        "syllabus",
        "structure",
        "schedule",
        "wiki_page",
        "wiki_section",
        "regulation_computation",
    }
)


def _completed_course_numbers(user_context: dict[str, Any]) -> list[str]:
    completed = user_context.get("completedCourses") or user_context.get("completed_courses") or []
    numbers: list[str] = []
    for item in completed:
        if isinstance(item, dict):
            number = item.get("courseNumber") or item.get("course_number")
            if number:
                numbers.append(str(number).strip())
        elif item:
            numbers.append(str(item).strip())
    return numbers


def _semester_filename(
    *,
    entities: dict[str, Any],
    user_context: dict[str, Any],
    query: str,
    engine,
) -> str | None:
    profile = user_context.get("profile") or {}
    explicit = (
        entities.get("semesterFilename")
        or entities.get("targetSemesterFilename")
        or profile.get("semesterFilename")
    )
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    plan_code = entities.get("targetSemesterCode") or profile.get("currentSemesterCode")
    resolution = resolve_semester_from_query(
        query,
        engine.available_semesters,
        explicit_plan_code=str(plan_code) if plan_code else None,
    )
    semester = resolution.get("semester")
    if semester is not None:
        return semester.filename
    return None


def _dedupe_slugs(slugs: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for slug in slugs:
        if not slug or slug in seen:
            continue
        seen.add(slug)
        ordered.append(slug)
    return ordered


def _program_minor_slugs(entities: dict[str, Any], combined: list[str]) -> list[str]:
    slugs: list[str] = []
    program = entities.get("programSlug")
    if isinstance(program, str) and program.strip():
        slugs.append(program.strip())
    for slug in combined:
        if slug.startswith("minor-") or slug.startswith("program-"):
            if slug not in slugs:
                slugs.append(slug)
    return slugs


def _track_structure_slugs(entities: dict[str, Any], combined: list[str]) -> list[str]:
    slugs: list[str] = []
    track = entities.get("trackSlug")
    if isinstance(track, str) and track.strip():
        slugs.append(track.strip())
    for slug in combined:
        if slug.startswith("track-"):
            if slug not in slugs:
                slugs.append(slug)
    return slugs


def _primary_wiki_slug(intent: AgentIntent, entities: dict[str, Any]) -> str | None:
    for key in ("programSlug", "trackSlug", "wikiSlug", "requirementSlug"):
        value = entities.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _prioritize_blocks(blocks: list[dict[str, Any]], primary_slug: str | None) -> list[dict[str, Any]]:
    if not primary_slug:
        return blocks
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("wiki_slug") == primary_slug:
            primary.append(block)
        else:
            secondary.append(block)
    return primary + secondary


def _wiki_source_path(engine, slug: str) -> str:
    page = getattr(engine, "wiki_pages", {}).get(slug) or {}
    rel_path = page.get("path") or f"{slug}.md"
    return f"wiki/{rel_path}"


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    ordered: list[dict[str, Any]] = []
    for action in actions:
        key = (
            action.get("intent"),
            action.get("course_id"),
            action.get("wiki_slug"),
            action.get("search_query"),
            action.get("section_query"),
        )
        if key in seen:
            continue
        seen.add(key)
        ordered.append(action)
    return ordered


def _append_wiki_page(actions: list[dict[str, Any]], slug: str) -> None:
    actions.append({"intent": "wiki_page", "wiki_slug": slug})


def _append_wiki_section(actions: list[dict[str, Any]], slug: str, section_query: str) -> None:
    actions.append(
        {
            "intent": "wiki_section",
            "wiki_slug": slug,
            "section_query": section_query,
        }
    )


def _track_structure_sections(query: str) -> list[str]:
    lowered = (query or "").lower()
    sections: list[str] = []
    if any(token in lowered for token in ("credit", "breakdown", "category", "categories", "graduat", "total")):
        sections.extend(["Credit Breakdown", "Program Structure"])
    sem_match = re.search(r"\bsemester\s+(\d+)\b", lowered)
    if sem_match:
        sections.append(f"Semester {sem_match.group(1)}")
    elif any(token in lowered for token in ("first semester", "semester 1")):
        sections.append("Semester 1")
    elif any(token in lowered for token in ("last semester", "final semester", "capstone")):
        sections.append("Semester 8")
    elif "scheduled" in lowered or "course" in lowered:
        sections.append("Semester 1")
    if not sections:
        sections.append("Credit Breakdown")
    return sections


def _regulation_sections(query: str) -> list[tuple[str, str]]:
    lowered = (query or "").lower()
    sections: list[tuple[str, str]] = []

    # Dual degree / additional degree formula
    if any(p in lowered for p in ("dual degree", "dual-degree", "second degree", "additional degree", "both degrees", "two degrees", "0.75", "תואר כפול", "תואר נוסף")):
        sections.append(("regulations-undergraduate", "Dual Degree / Additional Degree"))

    # Maximum course load
    if any(p in lowered for p in ("maximum number of credits", "max credits", "course load", "without special approval", "29 credits", "עומס", "כמה נקודות", "מקסימום נקודות")):
        sections.append(("regulations-undergraduate", "5.1 Maximum Course Load"))

    # Retaking courses / grade improvement / moed
    if (
        re.search(r"\bmoed\s+[ab]\b", lowered)
        or any(p in lowered for p in ("final grade", "grade improvement", "improve grade", "retake", "re-take", "taking it again", "שיפור ציון", "לחזור על"))
    ):
        sections.append(("regulations-undergraduate", "5.3 Retaking Courses"))

    # Grade appeal
    if any(p in lowered for p in ("grade appeal", "appeal", "days to appeal", "4 days", "unfair", "ערר")):
        sections.append(("regulations-undergraduate", "5.4 Grade Appeal"))

    # Non-regular academic standing
    if any(p in lowered for p in ("non-regular", "non regular", "academic standing", "מצב אקדמי לא תקין", "conditions", "standing")):
        sections.append(("regulations-undergraduate", "5.6 Non-Regular Academic Standing"))

    # Track transfer
    if any(p in lowered for p in ("transfer", "change track", "top quartile", "option b", "option a", "מעבר מסלול")):
        sections.append(("regulations-undergraduate", "5.11 Transfer Between Admission Tracks"))

    # Re-admission after break
    if any(p in lowered for p in ("re-admission", "readmission", "return after", "come back", "2 years", "waiting period", "חזרה ללימודים")):
        sections.append(("regulations-undergraduate", "5.12 Re-admission After Break"))

    # Graduation honors (degree-level)
    if any(p in lowered for p in ("cum laude", "summa", "graduation honor", "graduate with honor", "הצטיינות בתואר")):
        sections.append(("regulations-undergraduate", "Honors at Graduation"))

    # Per-semester honors
    if any(p in lowered for p in ("dean's excellence", "dean excellence", "president's excellence", "president excellence", "הצטיינות דיקן", "הצטיינות נשיא")):
        sections.append(("regulations-undergraduate", "Honors During Studies"))

    # Catch-all honors (could be either; include both if ambiguous)
    if "הצטיינות" in lowered and not sections:
        sections.append(("regulations-undergraduate", "Honors at Graduation"))
        sections.append(("regulations-undergraduate", "Honors During Studies"))

    # Graduate regulations — MSc / PhD admission
    if any(p in lowered for p in ("msc admission", "phd admission", "master admission", "doctorate admission", "graduate admission", "minimum gpa", "קבלה למוסמך", "קבלה לדוקטורט")):
        sections.append(("regulations-graduate", "Admission Requirements"))

    # Graduate regulations — scholarship
    if any(p in lowered for p in ("scholarship duration", "scholarship months", "msc scholarship", "phd scholarship", "stipend", "מלגה")):
        sections.append(("regulations-graduate", "Scholarships"))

    # Broad graduate fallback when no specific section matched yet
    if not sections and any(p in lowered for p in ("msc", "phd", "master's", "doctorate", "graduate program", "מוסמך", "דוקטורט", "תואר שני")):
        sections.append(("regulations-graduate", "Admission Requirements"))

    return sections


def plan_graph_retrieval_actions(
    *,
    intent: AgentIntent,
    entities: dict[str, Any],
    query: str,
    engine=None,
) -> list[dict[str, Any]]:
    """Map orchestrator intent + entities to academic-graph retrieval actions."""
    actions: list[dict[str, Any]] = []
    course_id = entities.get("courseNumber") or entities.get("courseId")
    if isinstance(course_id, str):
        course_id = course_id.strip() or None

    resolved_slugs: list[str] = []
    if engine is not None:
        resolved_slugs.extend(engine.resolve_slugs_from_query(query))
    for slug in slugs_from_entities(entities):
        if slug not in resolved_slugs:
            resolved_slugs.append(slug)
    resolved_slugs = _dedupe_slugs(resolved_slugs)

    if intent == "program_minor_lookup":
        resolved_slugs = _program_minor_slugs(entities, resolved_slugs)
        for slug in resolved_slugs:
            _append_wiki_page(actions, slug)
            _append_wiki_section(actions, slug, "Admission Requirements")
            _append_wiki_section(actions, slug, "Course Requirements")
        return _dedupe_actions(actions)

    if intent == "track_structure_lookup":
        resolved_slugs = _track_structure_slugs(entities, resolved_slugs)
        for slug in resolved_slugs:
            _append_wiki_page(actions, slug)
            for section in _track_structure_sections(query):
                _append_wiki_section(actions, slug, section)
        return _dedupe_actions(actions)

    if intent == "regulation_lookup" or (
        intent == "general_academic_question" and _REGULATION_REASONING_RE.search(query or "")
    ):
        reg_sections = _regulation_sections(query)
        for slug, section in reg_sections:
            _append_wiki_section(actions, slug, section)
        for slug in resolved_slugs:
            if slug.startswith("track-"):
                _append_wiki_page(actions, slug)
        # Fallback: no sections matched — fetch the full relevant regulation page
        if not any(action.get("intent") == "wiki_section" for action in actions):
            target_slug = "regulations-graduate" if any(
                p in (query or "").lower()
                for p in ("msc", "phd", "master", "doctorate", "graduate program", "מוסמך", "דוקטורט", "תואר שני")
            ) else "regulations-undergraduate"
            _append_wiki_page(actions, target_slug)
        residual = residual_search_query(query, resolved_slugs, getattr(engine, "alias_index", {}))
        if residual:
            actions.append({"intent": "wiki_search", "search_query": residual})
        return _dedupe_actions(actions)

    # Slug-first graph resolution for all other intents.
    for slug in resolved_slugs:
        _append_wiki_page(actions, slug)
        if slug.startswith("track-") and intent in {
            "general_academic_question",
            "requirement_explanation",
        }:
            for section in _track_structure_sections(query):
                _append_wiki_section(actions, slug, section)

    wiki_slug = entities.get("wikiSlug") or entities.get("trackSlug") or entities.get("requirementSlug")
    if isinstance(wiki_slug, str) and wiki_slug.strip() and wiki_slug.strip() not in resolved_slugs:
        _append_wiki_page(actions, wiki_slug.strip())

    if course_id:
        if intent in {
            "course_question",
            "prerequisite_check",
            "catalog_search",
            "semester_plan_generation",
            "semester_plan_modification",
        }:
            actions.append({"intent": "course_info", "course_id": course_id})
        if intent in {"course_question", "prerequisite_check", "semester_plan_generation"}:
            actions.append({"intent": "prerequisites", "course_id": course_id})
        if intent == "prerequisite_check":
            actions.append({"intent": "eligibility", "course_id": course_id})
        if intent in {"course_question", "semester_plan_generation", "semester_plan_modification"}:
            actions.append({"intent": "schedule", "course_id": course_id})
        if intent == "course_question":
            actions.append({"intent": "syllabus", "course_id": course_id})
        if intent in {"course_question", "requirement_explanation"}:
            actions.append({"intent": "structure", "course_id": course_id})

    alias_index = getattr(engine, "alias_index", {}) if engine is not None else {}
    residual = residual_search_query(query, resolved_slugs, alias_index)
    if residual and intent not in {"program_minor_lookup", "track_structure_lookup", "regulation_lookup"}:
        actions.append({"intent": "wiki_search", "search_query": residual})
    elif not actions and (query or "").strip():
        actions.append({"intent": "wiki_search", "search_query": query.strip()})

    if not actions and course_id:
        actions.append({"intent": "course_info", "course_id": course_id})

    return _dedupe_actions(actions)


def _build_regulation_synthesis_context(
    *,
    query: str,
    engine,
    resolved_slugs: list[str],
) -> str | None:
    if not _REGULATION_REASONING_RE.search(query or ""):
        return None
    track_rows = engine.track_credit_summary(resolved_slugs)
    if len(track_rows) < 2:
        return None
    total = sum(float(row["totalCredits"]) for row in track_rows)
    minimum = round(0.75 * total, 1)
    lines = [
        "Regulation application context:",
        "Rule: minimum combined credits = 0.75 × (sum of credits required by each track)",
        "Resolved track credit values:",
    ]
    for row in track_rows:
        lines.append(f"- {row['slug']}: {row['totalCredits']} credits ({row['title']})")
    lines.append(f"Sum of track credits: {total}")
    lines.append(f"Computed minimum combined credits: 0.75 × {total} = {minimum}")
    return "\n".join(lines)


def _block_to_snippet(block: dict[str, Any], *, score: float) -> dict[str, Any]:
    intent = str(block.get("intent") or "graph")
    course_id = block.get("course_id")
    wiki_slug = block.get("wiki_slug")
    section_query = block.get("section_query")
    context = str(block.get("context") or "").strip()
    title_parts = [intent.replace("_", " ")]
    if section_query:
        title_parts.append(str(section_query))
    if course_id:
        title_parts.append(str(course_id))
    if wiki_slug:
        title_parts.append(str(wiki_slug))
    source_file = wiki_slug or course_id
    if wiki_slug and section_query:
        source_file = f"{wiki_slug}#{section_query.replace(' ', '-').lower()}"
    return {
        "source_type": "academic_graph",
        "source_file": source_file,
        "page_title": " / ".join(title_parts),
        "section_title": section_query or intent,
        "content": context,
        "score": score,
    }


def _trim_to_token_budget(snippets: list[dict[str, Any]], max_tokens: int) -> list[dict[str, Any]]:
    """Keep snippets (in ranked order) until `max_tokens` would be exceeded.

    Mirrors `hybrid_wiki_retriever._trim_to_token_budget` — always keeps at
    least the first snippet so a single over-budget block never empties the
    result outright.
    """
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


def _source_id_for_block(block: dict[str, Any]) -> str:
    if block.get("wiki_slug"):
        slug = str(block["wiki_slug"])
        section = block.get("section_query")
        if section:
            return f"wiki:{slug}#{section}"
        return f"wiki:{slug}"
    if block.get("course_id"):
        return f"catalog:{block['course_id']}"
    if block.get("search_query"):
        return f"wiki_search:{block['search_query'][:80]}"
    return f"graph:{block.get('intent', 'unknown')}"


async def retrieve_graph_context_with_profile(
    *,
    query: str,
    user_context: dict[str, Any],
    entities: dict[str, Any],
    profile: RetrievalProfile,
    settings: Settings | None = None,
    intent: AgentIntent = "general_academic_question",
) -> tuple[list[dict[str, Any]], list[Any], dict[str, Any]]:
    """Drop-in replacement for legacy ``retrieve_wiki_context_with_profile``."""
    cfg = settings or get_settings()
    started = time.perf_counter()
    metadata: dict[str, Any] = {
        "retrievalBackend": "academic_graph",
        "profile": profile.profileName,
    }

    if not cfg.is_graph_retrieval_configured():
        metadata["error"] = "graph_paths_not_configured"
        return [], [], metadata

    engine = graph_registry.get_engine(cfg)
    semester_filename = _semester_filename(
        entities=entities,
        user_context=user_context,
        query=query,
        engine=engine,
    )
    if semester_filename:
        metadata["semesterFilename"] = semester_filename

    completed = _completed_course_numbers(user_context)
    resolved_slugs = engine.resolve_slugs_from_query(query)
    for slug in slugs_from_entities(entities):
        if slug not in resolved_slugs:
            resolved_slugs.append(slug)
    metadata["resolvedWikiSlugs"] = resolved_slugs

    actions = plan_graph_retrieval_actions(
        intent=intent,
        entities=entities,
        query=query,
        engine=engine,
    )
    metadata["plannedActions"] = actions

    blocks = graph_registry.execute_retrievals(
        actions,
        user_completed_courses=completed,
        semester_filename=semester_filename,
        settings=cfg,
    )
    blocks = _prioritize_blocks(blocks, _primary_wiki_slug(intent, entities))

    regulation_context = _build_regulation_synthesis_context(
        query=query,
        engine=engine,
        resolved_slugs=resolved_slugs,
    )
    if regulation_context:
        metadata["regulationSynthesisContext"] = regulation_context
        blocks.insert(
            0,
            {
                "intent": "regulation_computation",
                "context": regulation_context,
                "wiki_slug": "regulations-undergraduate",
            },
        )

    wiki_limit = max(1, int(profile.wikiChunksFinal or cfg.agent_wiki_retrieval_limit))
    snippets: list[dict[str, Any]] = []
    provenance: list[Any] = []

    for block in blocks[:wiki_limit]:
        context = str(block.get("context") or "").strip()
        if not context:
            continue
        intent = str(block.get("intent") or "")
        if intent in _STRUCTURAL_BLOCK_INTENTS:
            # Deterministically resolved by slug/course-id — "was this the
            # right block" isn't a ranking question for these, so they get a
            # fixed high confidence rather than a score that only ever
            # reflected how many blocks happened to be planned.
            score = 1.0
            retrieval_method = "exact_lookup"
        else:
            # wiki_search: real BM25 (+ embedding, when configured) score
            # from `rerank_chunks`/`AcademicGraphEngine.search_wiki` — 0.0
            # when nothing was actually found.
            score = float(block.get("score") or 0.0)
            retrieval_method = "metadata_filtered_hybrid_search"
        snippet = _block_to_snippet(block, score=score)
        snippets.append(snippet)
        provenance.append(
            provenance_claim(
                claim=f"Retrieved graph context ({block.get('intent')})",
                source_type="catalog_wiki",
                source_id=_source_id_for_block(block),
                retrieval_method=retrieval_method,
                confidence=1.0 if intent in _STRUCTURAL_BLOCK_INTENTS else min(1.0, score / 10.0),
                field_path="retrievedWikiContext",
            )
        )

    trimmed_snippets = _trim_to_token_budget(snippets, profile.maxContextTokens)
    if len(trimmed_snippets) < len(snippets):
        provenance = provenance[: len(trimmed_snippets)]
    snippets = trimmed_snippets

    metadata.update(
        {
            "retrievedCount": len(snippets),
            "blockCount": len(blocks),
            "estimatedContextTokens": estimate_context_tokens(snippets),
            "topScore": float(snippets[0].get("score") or 0) if snippets else 0.0,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "sourceIds": [_source_id_for_block(block) for block in blocks[:wiki_limit]],
            "retrievedSourcePages": [
                _wiki_source_path(engine, str(block.get("wiki_slug")))
                for block in blocks
                if block.get("wiki_slug")
            ],
        }
    )
    return snippets, provenance, metadata


async def retrieve_graph_context(
    *,
    query: str,
    user_context: dict[str, Any] | None = None,
    entities: dict[str, Any] | None = None,
    settings: Settings | None = None,
    intent: AgentIntent = "general_academic_question",
) -> tuple[list[dict[str, Any]], list[Any], dict[str, Any]]:
    """Convenience wrapper using the default general-academic profile."""
    from app.retrieval.profiles import get_profile

    profile = get_profile("general_catalog_question")
    return await retrieve_graph_context_with_profile(
        query=query,
        user_context=user_context or {},
        entities=entities or {},
        profile=profile,
        settings=settings,
        intent=intent,
    )


def warmup_graph_engine(*, settings: Settings | None = None) -> dict[str, Any]:
    """Pre-load wiki + semester JSON graph for eval runs."""
    cfg = settings or get_settings()
    if not cfg.is_graph_retrieval_configured():
        return {"configured": False}
    stats = graph_registry.refresh_stats(cfg)
    return stats
