"""Per-case and aggregate timing for final-answer eval runs (Phase 28.1)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseTiming:
    case_id: str | None = None
    total_ms: float = 0.0
    eval_setup_ms: float = 0.0
    agent_turn_ms: float = 0.0
    task_understanding_ms: float = 0.0
    planner_ms: float = 0.0
    workflow_ms: float = 0.0
    retrieval_context_ms: float = 0.0
    response_composition_ms: float = 0.0
    mongo_ms: float = 0.0
    fact_evaluation_ms: float = 0.0
    trace_write_ms: float = 0.0
    llm_total_ms: float = 0.0
    llm_call_count: int = 0
    agent_mode: str = "full_live"
    slowest_phase: str | None = None
    extra_phases: dict[str, float] = field(default_factory=dict)

    def record_phase(self, name: str, duration_ms: float) -> None:
        if duration_ms <= 0:
            return
        self.extra_phases[name] = self.extra_phases.get(name, 0.0) + duration_ms

    def finalize_slowest_phase(self) -> None:
        candidates: dict[str, float] = {
            "evalSetup": self.eval_setup_ms,
            "agentTurn": self.agent_turn_ms,
            "taskUnderstanding": self.task_understanding_ms,
            "planner": self.planner_ms,
            "workflow": self.workflow_ms,
            "retrievalContext": self.retrieval_context_ms,
            "responseComposition": self.response_composition_ms,
            "mongo": self.mongo_ms,
            "factEvaluation": self.fact_evaluation_ms,
            "traceWrite": self.trace_write_ms,
            "llmTotal": self.llm_total_ms,
        }
        candidates.update(self.extra_phases)
        if not candidates:
            self.slowest_phase = None
            return
        self.slowest_phase = max(candidates.items(), key=lambda item: item[1])[0]

    def to_report_dict(self) -> dict[str, Any]:
        self.finalize_slowest_phase()
        return {
            "totalMs": round(self.total_ms, 2),
            "evalSetupMs": round(self.eval_setup_ms, 2),
            "agentTurnMs": round(self.agent_turn_ms, 2),
            "taskUnderstandingMs": round(self.task_understanding_ms, 2),
            "plannerMs": round(self.planner_ms, 2),
            "workflowMs": round(self.workflow_ms, 2),
            "retrievalContextMs": round(self.retrieval_context_ms, 2),
            "responseCompositionMs": round(self.response_composition_ms, 2),
            "mongoMs": round(self.mongo_ms, 2),
            "factEvaluationMs": round(self.fact_evaluation_ms, 2),
            "traceWriteMs": round(self.trace_write_ms, 2),
            "llmTotalMs": round(self.llm_total_ms, 2),
            "llmCallCount": self.llm_call_count,
            "agentMode": self.agent_mode,
            "slowestPhase": self.slowest_phase,
        }


def extract_phase_timing_from_metadata(retrieval_metadata: dict[str, Any] | None) -> dict[str, float]:
    """Pull compact phase durations from turn retrieval metadata when present."""
    meta = dict(retrieval_metadata or {})
    phases: dict[str, float] = {}

    for key, target in (
        ("taskUnderstanding", "task_understanding_ms"),
        ("plannerOutput", "planner_ms"),
        ("plannerDiagnostics", "planner_ms"),
    ):
        block = meta.get(key)
        if isinstance(block, dict):
            duration = block.get("durationMs") or block.get("latencyMs")
            if duration is not None:
                try:
                    phases[target] = float(duration)
                except (TypeError, ValueError):
                    pass

    workflow = meta.get("workflowTiming")
    if isinstance(workflow, dict) and workflow.get("durationMs") is not None:
        try:
            phases["workflow_ms"] = float(workflow["durationMs"])
        except (TypeError, ValueError):
            pass

    context = meta.get("contextBuildTiming")
    if isinstance(context, dict) and context.get("durationMs") is not None:
        try:
            phases["retrieval_context_ms"] = float(context["durationMs"])
        except (TypeError, ValueError):
            pass

    return phases


def aggregate_timing_summary(
    timings: list[CaseTiming],
    *,
    total_run_ms: float | None = None,
) -> dict[str, Any]:
    if not timings:
        return {
            "totalRunMs": 0.0,
            "averageCaseMs": 0.0,
            "p50CaseMs": 0.0,
            "p95CaseMs": 0.0,
            "totalLlmCalls": 0,
            "totalLlmMs": 0.0,
            "slowestCases": [],
        }

    totals = [item.total_ms for item in timings if item.total_ms > 0]
    totals_sorted = sorted(totals)
    p50 = statistics.median(totals_sorted) if totals_sorted else 0.0
    p95_index = max(0, int(len(totals_sorted) * 0.95) - 1)
    p95 = totals_sorted[p95_index] if totals_sorted else 0.0

    slowest = sorted(timings, key=lambda item: item.total_ms, reverse=True)[:5]
    slowest_cases = []
    for item in slowest:
        item.finalize_slowest_phase()
        slowest_cases.append(
            {
                "caseId": item.case_id,
                "totalMs": round(item.total_ms, 2),
                "llmCallCount": item.llm_call_count,
                "slowestPhase": item.slowest_phase,
                "agentMode": item.agent_mode,
            }
        )

    return {
        "totalRunMs": round(total_run_ms if total_run_ms is not None else sum(totals), 2),
        "averageCaseMs": round(statistics.mean(totals), 2) if totals else 0.0,
        "p50CaseMs": round(float(p50), 2),
        "p95CaseMs": round(float(p95), 2),
        "totalLlmCalls": sum(item.llm_call_count for item in timings),
        "totalLlmMs": round(sum(item.llm_total_ms for item in timings), 2),
        "slowestCases": slowest_cases,
    }
