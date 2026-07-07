"""Extract safe trace phases from agent turn artifacts."""

from __future__ import annotations

import re
from typing import Any

from app.agent.evaluation.trace_logging import (
    EvalTraceCollector,
    compare_expected_sources,
    sanitize_trace_data,
)

_COURSE_CODE_RE = re.compile(r"\b\d{8}\b")
_TRACK_SLUG_RE = re.compile(r"track-[a-z0-9-]+(?:-[a-z0-9-]+)*")


def _wiki_pages_from_snippets(snippets: list[Any]) -> list[str]:
    pages: list[str] = []
    for item in snippets:
        if not isinstance(item, dict):
            continue
        for key in ("path", "sourcePath", "wikiPath", "pagePath", "source", "id"):
            value = item.get(key)
            if value:
                pages.append(str(value))
    return pages


def _extract_codes(text: str) -> dict[str, list[str]]:
    return {
        "courseCodes": _COURSE_CODE_RE.findall(text),
        "trackSlugs": _TRACK_SLUG_RE.findall(text),
    }


def _extract_eligibility_trace(
    sse_events: list[dict[str, Any]],
    used_sources: list[str],
) -> dict[str, Any] | None:
    block_data: dict[str, Any] | None = None
    for event in sse_events:
        if event.get("type") != "structured_output":
            continue
        block = event.get("block") or {}
        if block.get("type") != "PrerequisiteStatusBlock":
            continue
        data = block.get("data") or {}
        if data.get("eligibilityStatus") or data.get("requiredPrerequisiteCodes"):
            block_data = data
            break

    if block_data is None and not any(
        "Deterministic prerequisite eligibility validation" in item for item in used_sources
    ):
        return None

    llm_rewrite_skipped = any(
        "Deterministic prerequisite eligibility validation" in item for item in used_sources
    )
    if block_data is None:
        return {"llmRewriteSkipped": llm_rewrite_skipped}

    return sanitize_trace_data(
        {
            "targetCourseCode": block_data.get("courseNumber"),
            "prerequisiteCodes": block_data.get("requiredPrerequisiteCodes") or [],
            "completedCourseCount": block_data.get("completedCourseCount"),
            "satisfiedPrerequisiteCodes": block_data.get("satisfiedPrerequisites") or [],
            "missingPrerequisiteCodes": [
                item.get("courseNumber")
                for item in (block_data.get("missingPrerequisites") or [])
                if isinstance(item, dict) and item.get("courseNumber")
            ],
            "eligibilityStatus": block_data.get("eligibilityStatus"),
            "sourcePaths": [
                item.split("[", 1)[1][:-1]
                for item in used_sources
                if "Loaded catalog wiki page [" in item
            ],
            "llmRewriteSkipped": llm_rewrite_skipped,
        }
    )


def populate_trace_from_turn(
    collector: EvalTraceCollector,
    *,
    sse_events: list[dict[str, Any]],
    retrieval_metadata: dict[str, Any] | None,
    intent: str | None,
    entities: dict[str, Any] | None,
    used_sources: list[str],
    firewall_violations: list[dict[str, str]] | None = None,
    latency_ms: float | None = None,
) -> None:
    """Populate collector events from one completed agent turn."""
    meta = dict(retrieval_metadata or {})
    entities = dict(entities or {})

    collector.add_event(
        phase="intent",
        event_type="classification",
        name="rules_and_orchestrator",
        status=intent,
        data={
            "intent": intent,
            "entities": sanitize_trace_data(entities),
            "entityCodes": _extract_codes(collector.case.user_request),
        },
    )

    task_understanding = meta.get("taskUnderstanding")
    if isinstance(task_understanding, dict):
        collector.add_event(
            phase="task_understanding",
            event_type="reasoning_contract",
            name="task_understanding_v1",
            status=str(task_understanding.get("status") or "unknown"),
            data={
                "primaryIntent": task_understanding.get("primaryIntent"),
                "secondaryIntents": task_understanding.get("secondaryIntents"),
                "taskCategory": task_understanding.get("taskCategory"),
                "taskComplexity": task_understanding.get("taskComplexity"),
                "missingContext": task_understanding.get("missingContext"),
                "intentConfidence": task_understanding.get("intentConfidence"),
                "overallConfidence": task_understanding.get("overallConfidence"),
                "warnings": task_understanding.get("warnings"),
                "source": task_understanding.get("source"),
                "decisionSummary": task_understanding.get("decisionSummary"),
                "writeRisk": task_understanding.get("writeRisk"),
                "recommendedAutonomyLevel": task_understanding.get("recommendedAutonomyLevel"),
            },
        )

    planner = meta.get("plannerDiagnostics")
    if isinstance(planner, dict):
        collector.add_event(
            phase="planner",
            event_type="reasoning_contract",
            name="planner_agent_v1",
            status=str(planner.get("status") or "unknown"),
            data={
                "planId": planner.get("planId"),
                "executionMode": planner.get("executionMode"),
                "primaryIntent": planner.get("primaryIntent"),
                "subtaskCount": planner.get("subtaskCount"),
                "subtasks": planner.get("subtasks"),
                "capabilitiesRequested": planner.get("capabilitiesRequested"),
                "assumptions": planner.get("assumptions"),
                "successCriteria": planner.get("successCriteria"),
                "missingContext": planner.get("missingContext"),
                "clarificationNeeds": planner.get("clarificationNeeds"),
                "contextPreviews": planner.get("contextPreviews"),
                "warnings": planner.get("warnings"),
            },
        )

    capability = meta.get("capabilityDiagnostics")
    if isinstance(capability, dict):
        collector.add_event(
            phase="planner",
            event_type="capabilities",
            name="capability_registry",
            data=capability,
        )

    for key, phase in (
        ("supervisorDiagnostics", "orchestrator"),
        ("supervisorValidation", "orchestrator"),
        ("monitorDiagnostics", "orchestrator"),
        ("planRepairDiagnostics", "orchestrator"),
        ("clarificationDiagnostics", "orchestrator"),
        ("dynamicAgents", "workflow"),
        ("specialistValidation", "workflow"),
    ):
        payload = meta.get(key)
        if isinstance(payload, dict):
            collector.add_event(
                phase=phase,
                event_type="diagnostics",
                name=key,
                data=payload,
            )

    wiki_snippets = meta.get("retrievedWikiContext") or meta.get("wikiSnippets") or []
    retrieved_pages = _wiki_pages_from_snippets(wiki_snippets if isinstance(wiki_snippets, list) else [])
    for step in meta.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for key in ("sourcePath", "wikiPath", "path"):
            if step.get(key):
                retrieved_pages.append(str(step[key]))
    decomposed = meta.get("decomposedQueries") or []
    source_compare = compare_expected_sources(
        expected_pages=collector.case.source_wiki_pages,
        retrieved_pages=retrieved_pages,
        used_pages=used_sources,
    )
    collector.add_event(
        phase="retrieval",
        event_type="source_provenance",
        name="wiki_and_used_sources",
        data={
            **source_compare,
            "retrievalProfile": meta.get("retrievalProfile"),
            "topScore": meta.get("topScore"),
            "fallbackUsed": meta.get("fallbackUsed"),
            "retrievalAttempts": meta.get("retrievalAttempts") or meta.get("attempts"),
            "queries": meta.get("queries") or meta.get("retrievalQueries") or decomposed,
            "decomposedQueries": decomposed,
            "wikiExplanationSummary": (meta.get("wikiExplanationSummary") or "")[:400],
            "snippets": [
                {
                    "path": item.get("path") or item.get("sourcePath"),
                    "title": item.get("title"),
                    "score": item.get("score"),
                    "snippet": (item.get("snippet") or item.get("text") or "")[:240],
                }
                for item in (wiki_snippets[:12] if isinstance(wiki_snippets, list) else [])
                if isinstance(item, dict)
            ],
        },
    )

    synthesis = meta.get("synthesisDiagnostics")
    if isinstance(synthesis, dict):
        collector.add_event(
            phase="synthesis",
            event_type="diagnostics",
            name="synthesis",
            status=str(synthesis.get("status") or "unknown"),
            data={
                "safeToShow": synthesis.get("safeToShow"),
                "confidence": synthesis.get("confidence"),
                "decisionSummary": synthesis.get("decisionSummary"),
                "warnings": synthesis.get("warnings"),
            },
        )
    promotion = meta.get("synthesisPromotion")
    if isinstance(promotion, dict):
        collector.add_event(
            phase="synthesis",
            event_type="promotion",
            name="synthesis_text_promotion",
            status=str(promotion.get("status") or "unknown"),
            data={
                "promoted": promotion.get("promoted"),
                "mode": promotion.get("mode"),
                "warnings": promotion.get("warnings"),
            },
        )

    step_labels = [
        str(event.get("label") or "")
        for event in sse_events
        if event.get("type") in {"agent.step.started", "agent.step.completed", "agent.step.failed"}
    ]
    block_types = [
        str((event.get("block") or {}).get("type") or "")
        for event in sse_events
        if event.get("type") == "structured_output"
    ]
    eligibility_trace = _extract_eligibility_trace(sse_events, used_sources)
    if eligibility_trace:
        collector.add_event(
            phase="workflow",
            event_type="eligibility_validation",
            name="prerequisite_grounding",
            status=str(eligibility_trace.get("eligibilityStatus") or "unknown"),
            data=eligibility_trace,
        )
    collector.add_event(
        phase="workflow",
        event_type="execution",
        name="sse_workflow_steps",
        data={
            "stepLabels": step_labels[:20],
            "structuredBlockTypes": [item for item in block_types if item][:20],
            "runFailed": any(event.get("type") == "run.failed" for event in sse_events),
        },
    )

    if firewall_violations:
        collector.add_event(
            phase="firewall",
            event_type="blocked_side_effects",
            status="blocked",
            data={"violations": firewall_violations},
        )

    collector.add_event(
        phase="synthesis",
        event_type="final_answer_capture",
        name="message.completed",
        data={
            "latencyMs": round(latency_ms, 1) if latency_ms is not None else None,
            "usedSources": used_sources[:20],
            "finalAnswerSource": "message.completed_sse_or_persisted_assistant_message",
        },
    )
