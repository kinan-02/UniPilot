"""Eval-only LLM call counting for final-answer runs (Phase 28.1)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

_eval_llm_tracker: ContextVar["EvalLlmCallTracker | None"] = ContextVar("eval_llm_tracker", default=None)


@dataclass
class EvalLlmCallTracker:
    """Counts LLM calls during an eval case without writing unsafe debug artifacts."""

    case_id: str
    call_count: int = 0
    total_duration_ms: float = 0.0
    contracts: list[str] = field(default_factory=list)

    def on_llm_call(
        self,
        *,
        case_id: str,
        phase: str,
        contract_name: str,
        contract_version: str,
        prompt_text: str,
        raw_model_output: str,
        parsed_json_preview: dict[str, Any] | None,
        schema_valid: bool,
        status: str,
        repair_attempted: bool,
        repair_succeeded: bool,
        fallback_used: bool,
        warnings: list[str],
        duration_ms: float | None = None,
    ) -> None:
        _ = (
            case_id,
            phase,
            contract_version,
            prompt_text,
            raw_model_output,
            parsed_json_preview,
            schema_valid,
            status,
            repair_attempted,
            repair_succeeded,
            fallback_used,
            warnings,
        )
        self.call_count += 1
        if contract_name and contract_name not in self.contracts:
            self.contracts.append(contract_name)
        if duration_ms is not None:
            try:
                self.total_duration_ms += max(0.0, float(duration_ms))
            except (TypeError, ValueError):
                pass

    def snapshot(self) -> tuple[int, float]:
        return self.call_count, self.total_duration_ms


def current_eval_llm_tracker() -> EvalLlmCallTracker | None:
    return _eval_llm_tracker.get()


@contextmanager
def eval_llm_tracker_context(tracker: EvalLlmCallTracker | None) -> Iterator[None]:
    token = _eval_llm_tracker.set(tracker)
    try:
        yield
    finally:
        _eval_llm_tracker.reset(token)
