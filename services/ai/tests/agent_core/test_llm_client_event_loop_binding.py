"""Regression tests for the two defects behind the 2026-07-16 `ise_correctness`
live-eval run's phantom `llm_call_failed`s.

A cached `ChatOpenAI` was being handed to a DIFFERENT event loop than the one
that opened its pooled connections. `httpx` raises `RuntimeError: Event loop is
closed` from the transport in that case, which arrives as
`openai.APIConnectionError` and is re-raised as `llm_call_failed` -- with the
real cause discarded, so the log said nothing useful. pytest builds a fresh loop
per async test, so every test after the first lost its first LLM call to this,
including the final composition call of `presupposition_conflict`, which failed
that case with an empty answer the agent never had a chance to produce.

No network call is made here: `ChatOpenAI` construction is offline, and these
assert client IDENTITY and error plumbing, never a completion.
"""

from __future__ import annotations

import asyncio

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.reasoning.llm_client import build_chat_llm, reset_chat_llm_cache
from app.config import Settings

# A syntactically valid key is enough to get past the `not api_key` guard; it is
# never sent anywhere.
_CFG = Settings(openai_api_key="test-key-never-used-for-a-real-call")


async def _build() -> object:
    return build_chat_llm(settings=_CFG, temperature=0.0)


def test_each_event_loop_gets_its_own_client() -> None:
    # Two `asyncio.run` calls == two loops == what pytest does across two async
    # tests. Sharing one client here is the bug: the second loop would inherit
    # connections bound to the first, now-closed, loop.
    reset_chat_llm_cache()

    first = asyncio.run(_build())
    second = asyncio.run(_build())

    assert first is not None and second is not None
    assert first is not second, (
        "a client built in a closed event loop was reused in a new one -- its pooled "
        "connections are bound to the dead loop and the next call dies with "
        "'Event loop is closed'"
    )


def test_a_single_event_loop_still_shares_one_client() -> None:
    # The other half of the contract: loop-keying must not defeat the caching
    # that lets connections pool. One loop, same settings => one client.
    reset_chat_llm_cache()

    async def build_twice() -> tuple[object, object]:
        return await _build(), await _build()

    first, second = asyncio.run(build_twice())

    assert first is not None
    assert first is second, "same loop + same settings must reuse one client, or pooling is lost"


def test_error_detail_reports_the_cause_while_str_stays_the_bare_code() -> None:
    root = RuntimeError("Event loop is closed")
    transport = ConnectionError("Connection error.")
    transport.__cause__ = root
    error = LLMAdapterError("llm_call_failed", cause=transport)

    # Callers dispatch on `str(exc)` (e.g. `str(exc) in _PARSE_FAILURE_CODES`),
    # so the message must stay exactly the code -- the cause goes in `detail`.
    assert str(error) == "llm_call_failed"
    assert error.code == "llm_call_failed"
    assert "llm_call_failed" in error.detail
    assert "Connection error." in error.detail
    assert "Event loop is closed" in error.detail, "the root cause is what the log was missing"


def test_error_detail_without_a_cause_is_just_the_code() -> None:
    error = LLMAdapterError("json_parse_failed")

    assert str(error) == "json_parse_failed"
    assert error.detail == "json_parse_failed"
    assert error.cause is None
