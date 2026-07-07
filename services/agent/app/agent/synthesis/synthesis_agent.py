"""Optional ReasoningBlock synthesis path and diagnostic runner (Phase 21)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import SYNTHESIS_COMPOSER_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.reasoning.task_schemas import SYNTHESIS_OUTPUT_SCHEMA
from app.agent.synthesis.diagnostics import build_synthesis_diagnostics, compare_synthesis_to_live_response
from app.agent.synthesis.fallback_composer import deterministic_synthesis
from app.agent.synthesis.input_builder import build_synthesis_input
from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput, SynthesisStatus
from app.agent.synthesis.validation import validate_synthesis_output
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _compact_evidence(input: SynthesisInput) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "sourceType": item.source_type,
            "sourceName": item.source_name,
            "claim": item.claim[:200],
            "trustLevel": item.trust_level,
            "confidence": item.confidence,
            "provenance": item.provenance,
        }
        for item in input.evidence_items[:12]
    ]


def _normalize_llm_synthesis(result: dict[str, Any], *, synthesis_id: str) -> SynthesisOutput | None:
    try:
        status = str(result.get("status") or "")
        if status not in {
            "candidate_ready",
            "candidate_ready_with_warnings",
            "needs_clarification",
            "insufficient_evidence",
            "unsafe",
            "failed",
            "skipped",
        }:
            return None
        return SynthesisOutput(
            status=status,  # type: ignore[arg-type]
            synthesis_id=synthesis_id,
            candidate_answer_text=result.get("candidate_answer_text") or result.get("candidateAnswerText"),
            decision_summary=str(result.get("decision_summary") or result.get("decisionSummary") or ""),
            key_points=list(result.get("key_points") or result.get("keyPoints") or []),
            uncertainty_notes=list(result.get("uncertainty_notes") or result.get("uncertaintyNotes") or []),
            evidence_used_ids=list(result.get("evidence_used_ids") or result.get("evidenceUsedIds") or []),
            evidence_excluded_ids=list(result.get("evidence_excluded_ids") or result.get("evidenceExcludedIds") or []),
            safe_to_show=bool(result.get("safe_to_show") or result.get("safeToShow")),
            safe_to_promote=False,
            confidence=float(result.get("confidence") or 0.0),
            warnings=list(result.get("warnings") or []),
        )
    except Exception:  # noqa: BLE001
        return None


async def run_synthesis_with_llm(
    input: SynthesisInput,
    *,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> SynthesisOutput:
    cfg = settings or get_settings()
    if not cfg.is_agent_synthesis_use_llm():
        return SynthesisOutput(
            status="skipped",
            synthesis_id=input.synthesis_id,
            decision_summary="LLM synthesis disabled — skipped.",
            warnings=["llm_synthesis_disabled"],
        )

    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg), settings=cfg)
    reasoning_input = ReasoningBlockInput(
        block_id=f"synthesis-{uuid.uuid4().hex[:10]}",
        agent_name="synthesis_composer",
        objective="Reconcile compact evidence and produce a diagnostic synthesis candidate.",
        task_context={
            "userGoal": input.user_goal,
            "normalizedRequest": input.normalized_request,
            "workflowSummary": input.workflow_summary,
            "evidenceItems": _compact_evidence(input),
            "monitorSummary": input.monitor_summary,
            "clarificationSummary": {
                "status": (input.clarification_summary.get("clarificationDiagnostics") or {}).get("status"),
            },
            "planRepairSummary": input.plan_repair_summary,
            "dryRun": True,
        },
        constraints=[
            "Prefer authoritative deterministic academic facts.",
            "Preserve confirmed user preferences and surface uncertainty.",
            "Do not invent degree requirements, catalog facts, or transcript data.",
            "Do not claim writes/saves/imports happened.",
            "Do not create proposed actions.",
            "Do not expose chain-of-thought or raw context.",
        ],
        success_criteria=[
            "Output matches synthesis_output_v1 schema.",
            "safe_to_promote remains false for Phase 21 diagnostics.",
        ],
        output_schema_name="synthesis_output_v1",
        output_schema=SYNTHESIS_OUTPUT_SCHEMA,
        prompt_contract_name=SYNTHESIS_COMPOSER_V1,
        risk_level="high",
    )

    try:
        output: ReasoningBlockOutput = await block.run(reasoning_input)
    except Exception:  # noqa: BLE001
        logger.exception("synthesis_llm_failed", extra={"synthesisId": input.synthesis_id})
        fallback = deterministic_synthesis(input, cfg)
        fallback.warnings = [*fallback.warnings, "llm_synthesis_failed_fallback"]
        return fallback

    if output.status != "completed" or not output.schema_valid or not isinstance(output.result, dict):
        fallback = deterministic_synthesis(input, cfg)
        fallback.warnings = [*fallback.warnings, "llm_synthesis_invalid_fallback"]
        return fallback

    normalized = _normalize_llm_synthesis(output.result, synthesis_id=input.synthesis_id)
    if normalized is None:
        fallback = deterministic_synthesis(input, cfg)
        fallback.warnings = [*fallback.warnings, "llm_synthesis_schema_fallback"]
        return fallback

    normalized.safe_to_promote = False
    return normalized


async def run_synthesis(
    input: SynthesisInput,
    *,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> SynthesisOutput:
    cfg = settings or get_settings()
    if cfg.is_agent_synthesis_use_llm():
        output = await run_synthesis_with_llm(input, settings=cfg, reasoning_block=reasoning_block)
    else:
        output = deterministic_synthesis(input, cfg)
    return validate_synthesis_output(output, input, cfg)


async def run_synthesis_diagnostics(
    *,
    user_goal: str | None,
    normalized_request: str | None,
    live_response_summary: dict[str, Any],
    retrieval_metadata: dict[str, Any] | None = None,
    supervisor_metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> tuple[SynthesisOutput | None, dict[str, Any] | None]:
    """Run diagnostic synthesis when enabled. Never raises; never changes live response."""
    cfg = settings or get_settings()
    if not cfg.is_agent_synthesis_enabled():
        return None, None

    warnings: list[str] = []
    if not cfg.agent_synthesis_dry_run:
        warnings.append("synthesis_forced_dry_run")

    try:
        synthesis_input = build_synthesis_input(
            user_goal=user_goal,
            normalized_request=normalized_request,
            live_response_summary=live_response_summary,
            retrieval_metadata=retrieval_metadata or {},
            supervisor_metadata=supervisor_metadata,
            settings=cfg,
        )
        output = await run_synthesis(synthesis_input, settings=cfg, reasoning_block=reasoning_block)
        if warnings:
            output = output.model_copy(update={"warnings": [*output.warnings, *warnings]})

        diagnostics = build_synthesis_diagnostics(output)
        comparison = compare_synthesis_to_live_response(
            synthesis_output=output,
            live_response_summary=live_response_summary,
        )
        diagnostics["liveComparison"] = comparison
        return output, diagnostics
    except Exception as exc:  # noqa: BLE001
        logger.exception("synthesis_diagnostics_failed")
        return None, {
            "status": "failed",
            "safeToShow": False,
            "safeToPromote": False,
            "warnings": [f"synthesis_error:{type(exc).__name__}"],
        }
