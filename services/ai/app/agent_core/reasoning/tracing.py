"""Lightweight developer-facing tracing for `ReasoningBlock` runs.

Traces are structured summaries only — no raw prompts, no chain-of-thought,
no per-pass intermediate text. This keeps logs safe to ship to normal
application log sinks without leaking user data or private model reasoning.
"""

from __future__ import annotations

import logging

from app.agent_core.reasoning.schemas import ReasoningTrace

logger = logging.getLogger(__name__)

__all__ = ["ReasoningTrace", "log_reasoning_trace"]


def log_reasoning_trace(trace: ReasoningTrace, *, log: logging.Logger | None = None) -> None:
    """Emit one structured log line for a completed `ReasoningBlock.run` call."""
    (log or logger).info("reasoning_block_trace", extra={"reasoningTrace": trace.model_dump()})
