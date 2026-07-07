"""Deterministic clarification-need detection (Phase 17)."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.clarification.schemas import ClarificationNeed, ClarificationSource

_PREFERENCE_AMBIGUITY_TAGS = frozenset(
    {
        "preference",
        "ambiguous",
        "clarification",
        "user_choice",
        "user_preference",
    }
)

_RETRIEVABLE_CONTEXT_TAGS = frozenset(
    {
        "catalog",
        "transcript",
        "profile",
        "requirement",
        "offering",
        "context",
        "retrieval",
    }
)

_CONSEQUENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def needs_from_monitor_output(monitor_output: dict[str, Any]) -> list[ClarificationNeed]:
    """Create needs when monitor emitted an ask_clarification decision."""
    if not isinstance(monitor_output, dict):
        return []

    try:
        decision = monitor_output.get("decision")
        if not isinstance(decision, dict):
            return []

        action = str(decision.get("action") or "").strip()
        clarification_needed = bool(decision.get("clarificationNeeded"))
        if action != "ask_clarification" and not clarification_needed:
            return []

        reason = str(decision.get("reason") or "monitor_clarification_needed").strip()
        plan_id = monitor_output.get("planId")
        if plan_id is not None:
            plan_id = str(plan_id)

        ambiguity_type = "preference" if "preference" in reason.lower() else "mixed"
        consequence = "high" if ambiguity_type == "preference" else "medium"

        return [
            ClarificationNeed(
                id=f"monitor_{uuid.uuid4().hex[:12]}",
                source="monitor",
                ambiguity_type=ambiguity_type,
                consequence=consequence,
                question_topic=_topic_from_reason(reason),
                reason=reason,
                affected_plan_id=plan_id,
                evidence={"monitorDecisionAction": action or "ask_clarification"},
            )
        ]
    except Exception:  # noqa: BLE001 — detector must never raise
        return []


def needs_from_missing_context(
    *,
    missing_context: list[str],
    source: ClarificationSource,
    affected_subtask_ids: list[str] | None = None,
    affected_plan_id: str | None = None,
) -> list[ClarificationNeed]:
    """Create needs from explicit missing-context markers only."""
    if not missing_context:
        return []

    subtask_ids = list(affected_subtask_ids or [])
    needs: list[ClarificationNeed] = []

    for index, raw_item in enumerate(missing_context):
        try:
            text = str(raw_item or "").strip()
            if not text:
                continue

            classification = _classify_missing_context(text)
            if classification is None:
                continue

            ambiguity_type, consequence, retrievable = classification
            needs.append(
                ClarificationNeed(
                    id=f"{source}_missing_{index}_{uuid.uuid4().hex[:8]}",
                    source=source,
                    ambiguity_type=ambiguity_type,
                    consequence=consequence,
                    question_topic=_topic_from_text(text),
                    reason=f"missing_context:{text[:120]}",
                    affected_plan_id=affected_plan_id,
                    affected_subtask_ids=subtask_ids,
                    evidence={
                        "missingContextSnippet": text[:80],
                        "preferenceAmbiguity": ambiguity_type in {"preference", "mixed"},
                        "retrievableEpistemic": retrievable,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            continue

    return needs


def dedupe_clarification_needs(needs: list[ClarificationNeed]) -> list[ClarificationNeed]:
    """Deduplicate by normalized topic, keeping highest consequence."""
    best_by_topic: dict[str, ClarificationNeed] = {}
    for need in needs:
        key = need.question_topic.strip().lower()
        existing = best_by_topic.get(key)
        if existing is None or _CONSEQUENCE_RANK[need.consequence] > _CONSEQUENCE_RANK[existing.consequence]:
            best_by_topic[key] = need
    return sorted(best_by_topic.values(), key=lambda item: (-_CONSEQUENCE_RANK[item.consequence], item.id))


def _classify_missing_context(
    text: str,
) -> tuple[str, str, bool] | None:
    lowered = text.lower()
    tags = {token for token in lowered.replace("-", " ").split() if token}
    preference = bool(tags & _PREFERENCE_AMBIGUITY_TAGS) or "which" in lowered or "prefer" in lowered
    retrievable = bool(tags & _RETRIEVABLE_CONTEXT_TAGS)

    if preference and retrievable:
        return "mixed", "high", True
    if preference:
        consequence = "high" if any(word in lowered for word in ("must", "critical", "required")) else "medium"
        return "preference", consequence, False
    if retrievable:
        return "epistemic", "medium", True
    if tags:
        return "epistemic", "low", False
    return None


def _topic_from_reason(reason: str) -> str:
    cleaned = reason.replace("_", " ").strip()
    return cleaned[:120] if cleaned else "clarification needed"


def _topic_from_text(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= 120:
        return cleaned
    return cleaned[:117] + "..."
