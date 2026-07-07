"""Deterministic synthesis conflict detection (Phase 21)."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.synthesis.schemas import EvidenceItem, SynthesisConflict

_MAX_CONFLICTS = 6


def _conflict_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _topic(item: EvidenceItem) -> str:
    return str(item.metadata.get("topic") or item.source_name or "general")


def _status_tag(item: EvidenceItem) -> str:
    return str(item.metadata.get("status") or item.metadata.get("signal") or "").lower()


def detect_synthesis_conflicts(
    evidence_items: list[EvidenceItem],
    *,
    monitor_summary: dict[str, Any] | None = None,
    plan_repair_summary: dict[str, Any] | None = None,
    max_conflicts: int = _MAX_CONFLICTS,
) -> list[SynthesisConflict]:
    conflicts: list[SynthesisConflict] = []

    by_topic: dict[str, list[EvidenceItem]] = {}
    for item in evidence_items:
        by_topic.setdefault(_topic(item), []).append(item)

    for topic, group in by_topic.items():
        if len(group) < 2:
            continue
        statuses = {_status_tag(item) for item in group if _status_tag(item)}
        if len(statuses) > 1 and "general" not in topic:
            conflicts.append(
                SynthesisConflict(
                    id=_conflict_id("topic"),
                    severity="warning",
                    summary=f"Conflicting status signals for topic '{topic}'.",
                    evidence_item_ids=[item.id for item in group],
                    resolution="prefer_authoritative",
                )
            )

    workflow = [item for item in evidence_items if item.source_type == "deterministic_workflow"]
    specialists = [item for item in evidence_items if item.source_type == "specialist_agent"]
    dynamic = [item for item in evidence_items if item.source_type == "dynamic_agent"]
    confirmed = [item for item in evidence_items if item.source_type == "confirmed_user_clarification"]
    assumed = [item for item in evidence_items if item.source_type == "assumed_user_preference"]

    if workflow and specialists:
        conflicts.append(
            SynthesisConflict(
                id=_conflict_id("wf_spec"),
                severity="warning",
                summary="Specialist evidence may diverge from deterministic workflow summary.",
                evidence_item_ids=[workflow[0].id, specialists[0].id],
                resolution="prefer_authoritative",
            )
        )

    if workflow and dynamic:
        conflicts.append(
            SynthesisConflict(
                id=_conflict_id("wf_dyn"),
                severity="warning",
                summary="Dynamic-agent evidence may diverge from deterministic workflow summary.",
                evidence_item_ids=[workflow[0].id, dynamic[0].id],
                resolution="prefer_authoritative",
            )
        )

    if confirmed and assumed:
        conflicts.append(
            SynthesisConflict(
                id=_conflict_id("clar"),
                severity="info",
                summary="Both confirmed and assumed clarification evidence are present.",
                evidence_item_ids=[confirmed[0].id, assumed[0].id],
                resolution="prefer_confirmed",
            )
        )

    monitor = monitor_summary if isinstance(monitor_summary, dict) else {}
    decision = monitor.get("decision") if isinstance(monitor.get("decision"), dict) else {}
    if str(decision.get("action") or "") == "abort_safely":
        conflicts.append(
            SynthesisConflict(
                id=_conflict_id("unsafe"),
                severity="error",
                summary="Monitor unsafe_output signal blocks synthesis promotion.",
                evidence_item_ids=[item.id for item in evidence_items if item.source_type == "monitor"],
                resolution="exclude_low_trust",
            )
        )

    for item in evidence_items:
        if item.metadata.get("signal") == "missing_context":
            conflicts.append(
                SynthesisConflict(
                    id=_conflict_id("missing"),
                    severity="warning",
                    summary="Missing context signal conflicts with candidate-ready synthesis.",
                    evidence_item_ids=[item.id],
                    resolution="requires_clarification",
                )
            )
            break

    repair = plan_repair_summary if isinstance(plan_repair_summary, dict) else {}
    mode = str(repair.get("modeUsed") or "")
    if mode in {"regenerate", "abort_safely"}:
        conflicts.append(
            SynthesisConflict(
                id=_conflict_id("repair"),
                severity="warning",
                summary=f"Plan repair requested {mode} while synthesis may produce a candidate.",
                evidence_item_ids=[item.id for item in evidence_items if item.source_type == "plan_repair"],
                resolution="surface_uncertainty",
            )
        )

    return conflicts[: max(0, max_conflicts)]
