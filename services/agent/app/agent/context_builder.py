"""Centralized context assembly for agent workflows (spec §12, academic graph retrieval)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.agent.context_validator import validate_context_pack
from app.agent.llm_answer_validator import validate_retrieval_with_llm
from app.agent.query_decomposer import decompose_retrieval_query
from app.agent.retrieval_gaps import identify_retrieval_gaps
from app.agent.retrieval_planner import build_retrieval_plan
from app.agent.retrieval_refiner import (
    attempt_mode_for_index,
    refine_decomposed_queries,
    wiki_profile_for_attempt,
)
from app.agent.schemas import (
    AgentContextPack,
    AgentIntent,
    IntentClassification,
    TaskPlan,
    WikiContextSnippet,
)
from app.agent.wiki_context_merger import merge_wiki_snippets
from app.config import Settings, get_settings
from app.planning.technion_planner_semesters import resolve_planner_semester_codes
from app.repositories import catalog_repository
from app.retrieval.catalog_retriever import retrieve_catalog_context
from app.retrieval.graph_retriever import retrieve_graph_context_with_profile
from app.retrieval.mongodb_user_retriever import retrieve_mongodb_user_data
from app.retrieval.offerings_retriever import retrieve_offerings_context
from app.retrieval.profiles import RetrievalProfile, get_profile, intent_omits_student_profile, primary_profile_for_intent, select_profiles_for_intent
from app.retrieval.provenance import ProvenanceRecord, provenance_to_strings


def _wiki_only_user_context(user_context: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in user_context.items()
        if key not in {"profile", "completedCourses", "completed_courses", "user_preferences"}
    }


def _finalize_context_pack_for_intent(pack: AgentContextPack, intent: AgentIntent) -> AgentContextPack:
    if not intent_omits_student_profile(intent):
        return pack
    return pack.model_copy(update={"user_context": _wiki_only_user_context(pack.user_context)})


def resolve_target_semester_code(
    entities: dict[str, Any],
    *,
    profile_semester: str | None,
    available_semesters: list[str],
) -> str | None:
    target = entities.get("targetSemesterCode") or entities.get("targetSemester")
    if isinstance(target, str) and target.strip() and target != "next":
        return target.strip()

    if target == "next" or entities.get("targetSemester") == "next":
        if not available_semesters:
            return profile_semester
        if profile_semester and profile_semester in available_semesters:
            index = available_semesters.index(profile_semester)
            if index + 1 < len(available_semesters):
                return available_semesters[index + 1]
        return available_semesters[0]

    return profile_semester


def _base_wiki_query(intent: AgentIntent, entities: dict[str, Any], user_message: str) -> str:
    from app.agent.retrieval_planner import _wiki_query

    return _wiki_query(intent, entities) if not user_message.strip() else user_message.strip()


async def _retrieve_wiki_multi_step(
    *,
    queries: list[str],
    user_context: dict[str, Any],
    entities: dict[str, Any],
    profile: RetrievalProfile,
    settings: Settings,
    attempt_index: int,
    existing_snippets: list[WikiContextSnippet],
    intent: AgentIntent,
) -> tuple[list[WikiContextSnippet], list[ProvenanceRecord], list[dict[str, Any]]]:
    attempt_mode = attempt_mode_for_index(attempt_index)
    profile_name = wiki_profile_for_attempt(
        attempt_index=attempt_index,
        default_profile_name=profile.profileName,
    )
    step_profile = get_profile(profile_name)
    wiki_snippets = list(existing_snippets)
    provenance_records: list[ProvenanceRecord] = []
    step_logs: list[dict[str, Any]] = []

    retrieval_context = {
        **user_context,
        "retrievalAttemptMode": attempt_mode,
    }

    for sub_query in queries:
        snippets, records, wiki_meta = await retrieve_graph_context_with_profile(
            query=sub_query,
            user_context=retrieval_context,
            entities=entities,
            profile=step_profile,
            settings=settings,
            intent=intent,
        )
        wiki_snippets = merge_wiki_snippets(
            wiki_snippets,
            [WikiContextSnippet(**snippet) for snippet in snippets],
            max_snippets=step_profile.wikiChunksFinal,
        )
        provenance_records.extend(records)
        step_logs.append(
            {
                "query": sub_query,
                "profile": step_profile.profileName,
                "attemptMode": attempt_mode,
                **wiki_meta,
            }
        )

    return wiki_snippets, provenance_records, step_logs


async def build_agent_context_pack(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    run_id: str,
    user_id: str,
    intent: AgentIntent,
    entities: dict[str, Any],
    classification: IntentClassification,
    task_plan: TaskPlan,
    user_message: str,
    message_attachments: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
    settings: Settings | None = None,
) -> AgentContextPack:
    """Execute retrieval plan with bounded agentic attempts and return validated context pack."""
    cfg = settings or get_settings()
    selected_profiles = select_profiles_for_intent(intent, entities=entities)
    primary = primary_profile_for_intent(intent, entities=entities)
    retrieval_plan = build_retrieval_plan(
        classification=classification,
        task_plan=task_plan,
        entities=entities,
    )

    user_context: dict[str, Any] = {}
    academic_context: dict[str, Any] = {}
    wiki_snippets: list[WikiContextSnippet] = []
    provenance_records: list[ProvenanceRecord] = []
    missing_data: list[str] = []
    warnings: list[str] = []
    conversation_assumptions = list(assumptions or [])
    retrieval_metadata: dict[str, Any] = {
        "primaryProfile": primary.profileName,
        "profiles": [profile.profileName for profile in selected_profiles],
        "steps": [],
        "attempts": 0,
        "agenticRetrieval": cfg.is_agentic_retrieval_enabled(),
        "retrievalBackend": "academic_graph",
    }

    base_wiki_query = _base_wiki_query(intent, entities, user_message)
    decomposed = decompose_retrieval_query(
        user_message=user_message,
        intent=intent,
        entities=entities,
        base_wiki_query=base_wiki_query,
    )
    wiki_queries = [query.text for query in decomposed]
    retrieval_metadata["decomposedQueries"] = [
        {"text": query.text, "facet": query.facet, "source": query.source}
        for query in decomposed
    ]

    max_attempts = max(1, int(primary.maxRetrievalAttempts or cfg.agent_max_retrieval_attempts))

    for attempt in range(max_attempts):
        retrieval_metadata["attempts"] = attempt + 1
        attempt_mode = attempt_mode_for_index(attempt)
        retrieval_metadata["attemptMode"] = attempt_mode
        gaps: list[str] = []

        if attempt > 0 and cfg.is_agentic_retrieval_enabled():
            gaps = identify_retrieval_gaps(
                AgentContextPack(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    user_id=user_id,
                    intent=intent,
                    entities=entities,
                    user_context=user_context,
                    academic_context=academic_context,
                    retrieved_wiki_context=wiki_snippets,
                    validation=validate_context_pack(
                        AgentContextPack(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            user_id=user_id,
                            intent=intent,
                            entities=entities,
                            user_context=user_context,
                            academic_context=academic_context,
                            retrieved_wiki_context=wiki_snippets,
                            retrieval_profile=primary.profileName,
                            retrieval_metadata=retrieval_metadata,
                        )
                    ),
                    retrieval_profile=primary.profileName,
                    retrieval_metadata=retrieval_metadata,
                )
            )
            refined = refine_decomposed_queries(
                user_message=user_message,
                intent=intent,
                entities=entities,
                base_wiki_query=base_wiki_query,
                gaps=gaps,
                attempt_index=attempt,
            )
            wiki_queries = [query.text for query in refined]
            retrieval_metadata.setdefault("refinedQueries", []).append(
                {
                    "attempt": attempt + 1,
                    "gaps": gaps,
                    "queries": wiki_queries,
                }
            )

        for step in retrieval_plan:
            source = str(step.get("source") or "")
            if source == "academic_graph":
                continue

            # `mongodb` (student profile/completed courses) is genuinely
            # single-shot — re-running it can't fix anything a later gap
            # would detect. `structured_catalog`/`structured_offerings`
            # re-run when the gap they'd actually fix is present, instead
            # of the previous blanket "only ever run on attempt 0" skip
            # that left `missing_structured_course`/`missing_offering`
            # gaps structurally unfixable by the retry loop.
            should_run = attempt == 0
            if not should_run and cfg.is_agentic_retrieval_enabled():
                if source == "structured_catalog" and "missing_structured_course" in gaps:
                    should_run = True
                elif source == "structured_offerings" and "missing_offering" in gaps:
                    should_run = True
            if not should_run:
                continue

            step_profile_name = str(step.get("profile") or primary.profileName)
            step_log: dict[str, Any] = {
                "source": source,
                "profile": step_profile_name,
                "attempt": attempt + 1,
            }

            if source == "mongodb":
                fragment, records = await retrieve_mongodb_user_data(
                    database,
                    user_id=user_id,
                    queries=list(step.get("queries") or []),
                )
                user_context.update(fragment)
                provenance_records.extend(records)
                step_log["fields"] = list(fragment.keys())

            elif source == "structured_catalog":
                fragment, records = await retrieve_catalog_context(
                    database,
                    user_id=user_id,
                    queries=list(step.get("queries") or []),
                    entities=entities,
                    user_context=user_context,
                )
                academic_context.update(fragment)
                provenance_records.extend(records)
                step_log["fields"] = list(fragment.keys())

            elif source == "structured_offerings":
                profile_data = user_context.get("profile") or {}
                mongo_codes = await catalog_repository.list_planner_semester_codes_from_offerings(
                    database,
                )
                available = resolve_planner_semester_codes(
                    raw_dir=Path(cfg.technion_raw_dir) if cfg.technion_raw_dir else None,
                    mongo_codes=mongo_codes,
                )
                resolved_semester = resolve_target_semester_code(
                    entities,
                    profile_semester=profile_data.get("currentSemesterCode"),
                    available_semesters=available,
                )
                if resolved_semester:
                    entities = {**entities, "targetSemesterCode": resolved_semester}

                fragment, records = await retrieve_offerings_context(
                    database,
                    queries=list(step.get("queries") or []),
                    entities=entities,
                    settings=cfg,
                )
                academic_context.update(fragment)
                provenance_records.extend(records)
                step_log["targetSemesterCode"] = entities.get("targetSemesterCode")
                step_log["offeringFound"] = academic_context.get("offering") is not None

            retrieval_metadata["steps"].append(step_log)

        wiki_steps = [step for step in retrieval_plan if step.get("source") == "academic_graph"]
        if wiki_steps and (attempt == 0 or cfg.is_agentic_retrieval_enabled()):
            wiki_profile = get_profile(
                str(wiki_steps[0].get("profile") or primary.profileName)
            )
            query_batch = (
                wiki_queries
                if cfg.is_agentic_retrieval_enabled()
                else [str(wiki_steps[0].get("query") or base_wiki_query)]
            )
            wiki_snippets, wiki_records, wiki_step_logs = await _retrieve_wiki_multi_step(
                queries=query_batch,
                user_context=user_context,
                entities=entities,
                profile=wiki_profile,
                settings=cfg,
                attempt_index=attempt,
                existing_snippets=wiki_snippets if attempt > 0 else [],
                intent=intent,
            )
            provenance_records.extend(wiki_records)
            retrieval_metadata["steps"].append(
                {
                    "source": "academic_graph",
                    "profile": wiki_profile.profileName,
                    "attempt": attempt + 1,
                    "subQueries": wiki_step_logs,
                }
            )
            if wiki_step_logs:
                last_meta = wiki_step_logs[-1]
                for key in ("resolvedWikiSlugs", "retrievedSourcePages", "regulationSynthesisContext"):
                    if last_meta.get(key) is not None:
                        retrieval_metadata[key] = last_meta.get(key)
            regulation_context = None
            for step_log in wiki_step_logs:
                regulation_context = step_log.get("regulationSynthesisContext") or regulation_context
            regulation_context = regulation_context or retrieval_metadata.get("regulationSynthesisContext")
            if regulation_context:
                academic_context = {
                    **academic_context,
                    "regulationSynthesisContext": regulation_context,
                }
            retrieval_metadata["wikiExplanationSummary"] = build_wiki_explanation_context(
                wiki_snippets
            )

        pack = AgentContextPack(
            conversation_id=conversation_id,
            run_id=run_id,
            user_id=user_id,
            intent=intent,
            entities=entities,
            user_context=user_context,
            academic_context=academic_context,
            retrieved_wiki_context=wiki_snippets,
            assumptions=conversation_assumptions,
            missing_data=missing_data,
            warnings=warnings,
            provenance=provenance_to_strings(provenance_records),
            message_attachments=list(message_attachments or []),
            retrieval_profile=primary.profileName,
            retrieval_profiles=[profile.profileName for profile in selected_profiles],
            retrieval_metadata=retrieval_metadata,
        )
        validation = validate_context_pack(pack)
        pack = pack.model_copy(update={"validation": validation})

        if cfg.is_agent_llm_validation_enabled() and validation.status != "valid":
            llm_validation = await validate_retrieval_with_llm(
                pack,
                user_message=user_message,
                settings=cfg,
            )
            if llm_validation is not None:
                retrieval_metadata["llmValidation"] = llm_validation
                if llm_validation.get("sufficient"):
                    validation = validation.model_copy(
                        update={
                            "status": "valid",
                            "warnings": [
                                *validation.warnings,
                                "llm_validation_overrode_partial_status",
                            ],
                        }
                    )
                    pack = pack.model_copy(update={"validation": validation})
                else:
                    for gap in llm_validation.get("gaps") or []:
                        gap_text = str(gap)
                        if gap_text not in validation.warnings:
                            validation = validation.model_copy(
                                update={"warnings": [*validation.warnings, gap_text]}
                            )
                    pack = pack.model_copy(update={"validation": validation})

        if validation.status == "valid":
            return _finalize_context_pack_for_intent(pack, intent)
        if validation.status == "partial" and attempt == max_attempts - 1:
            return _finalize_context_pack_for_intent(
                pack.model_copy(
                update={
                    "missing_data": list(validation.errors),
                    "warnings": list({*warnings, *validation.warnings}),
                }
            ),
                intent,
            )

        missing_data = list(validation.errors)

    return _finalize_context_pack_for_intent(
        AgentContextPack(
            conversation_id=conversation_id,
            run_id=run_id,
            user_id=user_id,
            intent=intent,
            entities=entities,
            user_context=user_context,
            academic_context=academic_context,
            retrieved_wiki_context=wiki_snippets,
            assumptions=conversation_assumptions,
            missing_data=missing_data,
            warnings=warnings,
            provenance=provenance_to_strings(provenance_records),
            message_attachments=list(message_attachments or []),
            retrieval_profile=primary.profileName,
            retrieval_profiles=[profile.profileName for profile in selected_profiles],
            retrieval_metadata=retrieval_metadata,
            validation=validate_context_pack(
                AgentContextPack(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    user_id=user_id,
                    intent=intent,
                    entities=entities,
                    user_context=user_context,
                    academic_context=academic_context,
                    retrieved_wiki_context=wiki_snippets,
                    retrieval_profile=primary.profileName,
                )
            ),
        ),
        intent,
    )
