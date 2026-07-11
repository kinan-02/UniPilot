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
    """Emit one structured log line for a completed `ReasoningBlock.run` call.

    The summary is folded directly into the log message (not left in `extra`
    alone) so it's visible under a plain `%(message)s`-style formatter --
    `extra` fields are silently dropped by the default formatter otherwise,
    which is exactly why a real latency investigation found zero trace
    output despite every reasoning call already going through this path.
    """
    (log or logger).info(
        "reasoning_block_trace block_id=%s agent=%s status=%s iterations=%d "
        "repair_attempts=%d duration_ms=%.0f schema_valid=%s",
        trace.block_id,
        trace.agent_name,
        trace.status,
        trace.iterations_used,
        trace.repair_attempts_used,
        trace.duration_ms,
        trace.schema_valid,
        extra={"reasoningTrace": trace.model_dump()},
    )
