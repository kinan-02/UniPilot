"""Optional LLM judge for golden-set final answer evaluation."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.evaluation.final_answer_eval import (
    FactCheckResult,
    GoldenAnswerCase,
    JudgeMode,
    evaluate_fact_deterministic,
)
from app.agent.reasoning.prompt_registry import FINAL_ANSWER_JUDGE_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import FINAL_ANSWER_JUDGE_OUTPUT_SCHEMA
from app.config import Settings

_VALID_STATUSES = frozenset({"present", "partial", "missing", "contradicted"})


async def evaluate_facts_with_judge(
    *,
    case: GoldenAnswerCase,
    final_answer: str,
    judge_mode: JudgeMode,
    settings: Settings,
    allow_real_llm: bool,
) -> tuple[list[FactCheckResult], list[str]]:
    """Evaluate key facts using deterministic, LLM, or hybrid judge mode."""
    deterministic = [
        evaluate_fact_deterministic(fact, final_answer) for fact in case.key_facts
    ]
    if judge_mode == "deterministic":
        return deterministic, []

    if not allow_real_llm:
        raise ValueError("llm_judge_requires_allow_real_llm")

    llm_results, hallucination_warnings = await _run_llm_judge(
        case=case,
        final_answer=final_answer,
        settings=settings,
    )
    if judge_mode == "llm":
        return llm_results, hallucination_warnings

    merged: list[FactCheckResult] = []
    llm_by_fact = {item.fact: item for item in llm_results}
    for det in deterministic:
        llm_item = llm_by_fact.get(det.fact)
        if det.status == "present":
            merged.append(det)
            continue
        if llm_item is not None and llm_item.status in {"present", "contradicted"}:
            merged.append(llm_item)
        elif det.status == "contradicted":
            merged.append(det)
        elif llm_item is not None:
            merged.append(llm_item)
        else:
            merged.append(det)
    return merged, hallucination_warnings


async def _run_llm_judge(
    *,
    case: GoldenAnswerCase,
    final_answer: str,
    settings: Settings,
) -> tuple[list[FactCheckResult], list[str]]:
    block = ReasoningBlock(settings=settings)
    output = await block.run(
        ReasoningBlockInput(
            block_id=f"final_answer_judge-{uuid.uuid4().hex[:10]}",
            agent_name="final_answer_judge",
            objective="Judge whether each key fact is supported by the final answer.",
            task_context={
                "userRequest": case.user_request,
                "correctSummary": case.correct_summary,
                "keyFacts": case.key_facts,
                "finalAnswer": final_answer,
                "evaluationNotes": case.evaluation_notes,
                "sourceWikiPages": case.source_wiki_pages,
            },
            constraints=[
                "Do not invent academic facts.",
                "Use only the supplied final answer text as evidence.",
                "Return concise evidence excerpts, not chain-of-thought.",
            ],
            success_criteria=[
                "Each key fact receives one status: present, partial, missing, or contradicted.",
            ],
            output_schema_name="final_answer_judge_output_v1",
            output_schema=FINAL_ANSWER_JUDGE_OUTPUT_SCHEMA,
            prompt_contract_name=FINAL_ANSWER_JUDGE_V1,
            max_reasoning_iterations=1,
            min_reasoning_iterations=1,
            max_schema_repair_attempts=1,
            temperature=0.0,
        )
    )

    hallucination_warnings: list[str] = []
    if output.status != "completed" or not output.result:
        return [
            FactCheckResult(
                fact=fact,
                status="missing",
                notes=f"llm_judge_unavailable:{output.status}",
            )
            for fact in case.key_facts
        ], [f"llm_judge_status:{output.status}"]

    payload = output.result
    raw_results = payload.get("fact_results") or payload.get("factResults") or []
    results: list[FactCheckResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact") or "").strip()
        status = str(item.get("status") or "missing").strip().lower()
        if status not in _VALID_STATUSES:
            status = "missing"
        results.append(
            FactCheckResult(
                fact=fact,
                status=status,  # type: ignore[arg-type]
                evidence_excerpt=str(item.get("evidence_excerpt") or item.get("evidenceExcerpt") or "") or None,
                notes=str(item.get("notes") or "") or None,
            )
        )

    if len(results) != len(case.key_facts):
        by_fact = {item.fact: item for item in results}
        results = [
            by_fact.get(fact)
            or FactCheckResult(fact=fact, status="missing", notes="llm_judge_missing_fact")
            for fact in case.key_facts
        ]

    hallucination_warnings = [
        str(item)
        for item in (payload.get("hallucination_warnings") or payload.get("hallucinationWarnings") or [])
        if str(item).strip()
    ]
    return results, hallucination_warnings
