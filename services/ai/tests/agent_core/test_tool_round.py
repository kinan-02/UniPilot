"""Tests for the shared `execute_tool_round` helper
(docs/agent/agent_plans/INTERPRETATION_REASONING_BLOCK_PLAN.md, "Shared
refactor" section) -- extracted from `RetrievalReasoningBlock`'s own
inlined version once `InterpretationReasoningBlock` needed the identical
logic.

Uses a small in-file stub tool (rather than the real `get_entity`, which
needs data files/an academic graph engine not available in this unit-test
environment) so success/failure behavior is directly controllable.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry


class _FakeInput(BaseModel):
    entity_id: str = ""


def _make_registry(*, ok: bool = True, names: tuple[str, ...] = ("fake_tool",)) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:

        async def _callable(payload: _FakeInput, _ok: bool = ok) -> ToolOutputEnvelope:
            return ToolOutputEnvelope(
                ok=_ok,
                data={"entity_id": payload.entity_id} if _ok else None,
                error=None if _ok else "simulated_not_found",
            )

        registry.register(
            ToolDescriptor(
                name=name,
                description="test stub",
                input_model=_FakeInput,
                output_model=ToolOutputEnvelope,
                side_effect="read",
                callable=_callable,
            )
        )
    return registry


class _CountingToolRegistry:
    def __init__(self, inner: ToolRegistry) -> None:
        self._inner = inner
        self.call_count = 0

    def get(self, name: str):
        descriptor = self._inner.get(name)
        original_callable = descriptor.callable

        async def _counting_callable(payload):
            self.call_count += 1
            return await original_callable(payload)

        return descriptor.model_copy(update={"callable": _counting_callable})

    def has(self, name: str) -> bool:
        return self._inner.has(name)


async def test_successful_call_merges_into_a_new_dict_and_records_audit():
    registry = _CountingToolRegistry(_make_registry(ok=True))
    original = {"existing_key": {"already": "there"}}

    merged, records = await execute_tool_round(
        tool_requests=[{"tool_name": "fake_tool", "arguments": {"entity_id": "234218"}}],
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far=original,
    )

    assert registry.call_count == 1
    assert len(records) == 1
    assert records[0].tool_name == "fake_tool"
    assert records[0].output_ok is True
    # Original dict untouched -- immutability.
    assert original == {"existing_key": {"already": "there"}}
    assert "existing_key" in merged
    assert any(k.startswith("fake_tool:") for k in merged)


async def test_two_calls_to_same_tool_with_different_arguments_do_not_clobber():
    registry = _CountingToolRegistry(_make_registry(ok=True))

    merged, records = await execute_tool_round(
        tool_requests=[
            {"tool_name": "fake_tool", "arguments": {"entity_id": "111"}},
            {"tool_name": "fake_tool", "arguments": {"entity_id": "222"}},
        ],
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far={},
    )

    assert registry.call_count == 2
    assert len(records) == 2
    fake_tool_keys = [k for k in merged if k.startswith("fake_tool:")]
    assert len(fake_tool_keys) == 2


async def test_failed_but_executed_call_is_audited_and_merged_as_error():
    registry = _CountingToolRegistry(_make_registry(ok=False))

    merged, records = await execute_tool_round(
        tool_requests=[{"tool_name": "fake_tool", "arguments": {"entity_id": "999"}}],
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far={},
    )

    assert registry.call_count == 1
    assert len(records) == 1
    assert records[0].output_ok is False
    # Failed results are now merged so the LLM can see the error and avoid
    # retrying the same call infinitely.
    assert len(merged) == 1
    key = list(merged.keys())[0]
    assert merged[key]["ok"] is False


async def test_tool_not_in_grant_is_skipped_and_audited_ok_false():
    registry = _CountingToolRegistry(_make_registry(ok=True))

    merged, records = await execute_tool_round(
        tool_requests=[{"tool_name": "fake_tool", "arguments": {"entity_id": "1"}}],
        tool_grant=["some_other_tool"],
        tool_registry=registry,
        tool_results_so_far={},
    )

    assert registry.call_count == 0
    assert len(records) == 1
    assert records[0].tool_name == "fake_tool"
    assert records[0].output_ok is False
    assert merged == {}


async def test_unregistered_tool_is_skipped_and_audited_ok_false():
    registry = _CountingToolRegistry(_make_registry(ok=True))

    merged, records = await execute_tool_round(
        tool_requests=[{"tool_name": "not_a_real_tool", "arguments": {}}],
        tool_grant=["not_a_real_tool"],
        tool_registry=registry,
        tool_results_so_far={},
    )

    assert registry.call_count == 0
    assert len(records) == 1
    assert records[0].output_ok is False
    assert merged == {}


async def test_raising_tool_is_skipped_and_audited_ok_false():
    class ThrowingRegistry(_CountingToolRegistry):
        def get(self, name: str):
            descriptor = self._inner.get(name)
            if name == "fake_tool":

                async def _throw(*args, **kwargs):
                    raise RuntimeError("simulated error")

                return descriptor.model_copy(update={"callable": _throw})
            return super().get(name)

    registry = ThrowingRegistry(_make_registry(ok=True))

    merged, records = await execute_tool_round(
        tool_requests=[{"tool_name": "fake_tool", "arguments": {"entity_id": "1"}}],
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far={},
    )

    assert len(records) == 1
    assert records[0].output_ok is False
    # Exception results are now merged so the LLM can see the error.
    assert len(merged) == 1
    key = list(merged.keys())[0]
    assert merged[key]["ok"] is False
    assert "simulated error" in merged[key]["error"]


async def test_no_requests_returns_unchanged_copy_and_no_records():
    registry = _CountingToolRegistry(_make_registry(ok=True))
    original = {"a": 1}

    merged, records = await execute_tool_round(
        tool_requests=[],
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far=original,
    )

    assert records == []
    assert merged == original
    assert merged is not original


async def test_shared_tool_call_cache_avoids_a_second_real_call_across_separate_rounds():
    """Regression guard: a live-eval run found `get_entity(student_profile,
    "student_123")` called 40 times with identical arguments in one turn --
    each call landed in a different `RetrievalReasoningBlock` instance (or a
    sibling nested sub-plan), so the existing `tool_results_so_far` dict
    (block-local, thrown away when that one instance returns) never helped.
    A `ToolCallCache` shared ACROSS separate `execute_tool_round` calls --
    simulating two different block instances -- must serve the second
    identical request from cache instead of re-invoking the tool."""
    registry = _CountingToolRegistry(_make_registry(ok=True))
    cache = ToolCallCache()
    request = [{"tool_name": "fake_tool", "arguments": {"entity_id": "234218"}}]

    merged_1, records_1 = await execute_tool_round(
        tool_requests=request,
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far={},
        tool_call_cache=cache,
    )
    # A brand-new, empty `tool_results_so_far` -- as a fresh block instance
    # (or a sibling nested sub-plan) would start with -- but the SAME cache.
    merged_2, records_2 = await execute_tool_round(
        tool_requests=request,
        tool_grant=["fake_tool"],
        tool_registry=registry,
        tool_results_so_far={},
        tool_call_cache=cache,
    )

    assert registry.call_count == 1  # the real tool ran exactly once
    assert records_1[0].from_cache is False
    assert records_2[0].from_cache is True
    assert records_2[0].output_ok is True
    assert merged_1 == merged_2


async def test_without_a_cache_a_second_round_still_pays_for_a_real_call():
    """Omitting `tool_call_cache` (its default) must behave exactly as
    before this feature existed -- every existing caller that doesn't pass
    it stays unaffected."""
    registry = _CountingToolRegistry(_make_registry(ok=True))
    request = [{"tool_name": "fake_tool", "arguments": {"entity_id": "234218"}}]

    await execute_tool_round(
        tool_requests=request, tool_grant=["fake_tool"], tool_registry=registry, tool_results_so_far={}
    )
    await execute_tool_round(
        tool_requests=request, tool_grant=["fake_tool"], tool_registry=registry, tool_results_so_far={}
    )

    assert registry.call_count == 2


def _make_slow_registry(*, delay_seconds: float = 0.05) -> ToolRegistry:
    """A tool whose real call takes a moment -- forces two genuinely
    concurrent `execute_tool_round` calls to actually overlap in time,
    rather than one finishing before the other even starts."""
    registry = ToolRegistry()

    async def _callable(payload: _FakeInput) -> ToolOutputEnvelope:
        await asyncio.sleep(delay_seconds)
        return ToolOutputEnvelope(ok=True, data={"entity_id": payload.entity_id})

    registry.register(
        ToolDescriptor(
            name="fake_tool",
            description="test stub",
            input_model=_FakeInput,
            output_model=ToolOutputEnvelope,
            side_effect="read",
            callable=_callable,
        )
    )
    return registry


async def test_concurrent_identical_requests_only_invoke_the_tool_once():
    """Regression guard for the "thundering herd" gap: `orchestrator/
    parallel_dispatch.py` dispatches a whole execution layer concurrently,
    so several sibling steps can all check the cache, all see a miss (none
    has finished yet), and all pay for a real call. A live-eval run found
    only 27 of 272 identical `get_entity` calls served from cache in one
    turn for exactly this reason. Two genuinely concurrent
    `execute_tool_round` calls sharing one `ToolCallCache` must still only
    invoke the underlying tool once."""
    registry = _CountingToolRegistry(_make_slow_registry())
    cache = ToolCallCache()
    request = [{"tool_name": "fake_tool", "arguments": {"entity_id": "student_123"}}]

    results = await asyncio.gather(
        execute_tool_round(
            tool_requests=request,
            tool_grant=["fake_tool"],
            tool_registry=registry,
            tool_results_so_far={},
            tool_call_cache=cache,
        ),
        execute_tool_round(
            tool_requests=request,
            tool_grant=["fake_tool"],
            tool_registry=registry,
            tool_results_so_far={},
            tool_call_cache=cache,
        ),
    )

    assert registry.call_count == 1
    from_cache_flags = sorted(records[0].from_cache for _, records in results)
    assert from_cache_flags == [False, True]
