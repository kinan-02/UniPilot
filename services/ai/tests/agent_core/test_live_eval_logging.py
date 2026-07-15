"""Unit tests for the live-eval logging harness (`live_eval_logging.py`).

These are ordinary (non-live) unit tests: they use a fake inner adapter, so
no real LLM call is made. They lock in the one contract the harness must
honor to faithfully stand in for `ChatLLMAdapter` -- forwarding
`raw_model_text_out` back to the caller even when the underlying call raises a
parse failure. A gap here silently starved `CompositionReasoningBlock`'s
prose-recovery path during a live-eval run: the model returned a complete
prose answer, the real adapter would have surfaced it via `raw_model_text_out`
before raising `json_parse_failed`, but the wrapper dropped it on the
exception path, so the answer was discarded as an `internal_error`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from tests.agent_core.live_eval_logging import LoggingLLMAdapter

_PROSE = "Here is a grounded summary of what the data shows. You are not eligible yet."


class _InnerParseFailAdapter:
    """Mirrors `ChatLLMAdapter.complete_json` on a prose response: it records
    the raw text into `raw_model_text_out` (as the real adapter does before
    parsing) and then raises `json_parse_failed`."""

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **_: Any) -> dict[str, Any]:
        if raw_model_text_out is not None:
            raw_model_text_out.append(_PROSE)
        raise LLMAdapterError("json_parse_failed")

    async def complete_text(self, **_: Any) -> str:  # pragma: no cover - unused here
        return ""


async def test_forwards_raw_text_to_caller_on_parse_failure() -> None:
    adapter = LoggingLLMAdapter(adapter=_InnerParseFailAdapter())
    caller_raw: list[str] = []

    with pytest.raises(LLMAdapterError):
        await adapter.complete_json(
            system_prompt="s", user_prompt="u", raw_model_text_out=caller_raw
        )

    # The caller (e.g. a reasoning block's prose-recovery path) must see the
    # raw prose even though the call raised -- exactly as the real adapter
    # delivers it.
    assert caller_raw == [_PROSE]


async def test_logs_the_failed_call_with_raw_text_and_error() -> None:
    adapter = LoggingLLMAdapter(adapter=_InnerParseFailAdapter())

    with pytest.raises(LLMAdapterError):
        await adapter.complete_json(system_prompt="s", user_prompt="u", raw_model_text_out=[])

    assert len(adapter.calls) == 1
    recorded = adapter.calls[0]
    assert recorded.error is not None and "json_parse_failed" in recorded.error
    assert recorded.raw_response_text == _PROSE
