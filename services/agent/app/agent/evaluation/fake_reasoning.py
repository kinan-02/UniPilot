"""Fake ReasoningBlock outputs for offline shadow replay (Phase 23)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.replay_schemas import MockReasoningOutput
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput


class FakeReasoningBlockRunner:
    """Deterministic mock ReasoningBlock — never calls a real LLM."""

    def __init__(self, mock_outputs: list[MockReasoningOutput]) -> None:
        self._outputs = list(mock_outputs)
        self._call_counts: dict[str, int] = {}
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        contract = input.prompt_contract_name or input.output_schema_name or "unknown"
        index = self._call_counts.get(contract, 0)
        self._call_counts[contract] = index + 1

        matched = self._match(contract, index)
        if matched is None:
            return ReasoningBlockOutput(
                status="failed",
                result={"status": "skipped", "decision_summary": "no_mock_output"},
                decision_summary="no_mock_output",
                confidence=0.0,
                schema_valid=False,
                iterations_used=0,
                repair_attempts_used=0,
            )

        return ReasoningBlockOutput(
            status="completed",
            result=matched.output,
            decision_summary=str(matched.output.get("decision_summary") or "mock"),
            confidence=float(matched.output.get("confidence") or 0.8),
            schema_valid=True,
            iterations_used=1,
            repair_attempts_used=0,
        )

    def _match(self, contract_name: str, call_index: int) -> MockReasoningOutput | None:
        for item in self._outputs:
            if item.contract_name != contract_name:
                continue
            if item.call_index is not None and item.call_index != call_index:
                continue
            return item
        for item in self._outputs:
            if item.contract_name == contract_name and item.call_index is None:
                return item
        return None
