"""Tests for `RetrievalReasoningBlock`/`run_retrieval_subagent`
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_retrieval_subagent`
entry point.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.subagents.retrieval_block import (
    _DEGRADED_FINALIZE_CONFIDENCE,
    _MAX_ROUNDS,
    run_retrieval_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolRegistry


class _NeedToolsThenTransientFailAdapter:
    """Round 1 asks for a tool (so a real tool runs and results accumulate);
    the next round's LLM call raises a transient `llm_call_failed` -- the
    mid-loop transport blip that used to discard the whole retrieval step and
    every fact its earlier rounds already fetched.
    """

    def __init__(self, tool_requests: list[dict[str, Any]], *, failure_code: str = "llm_call_failed") -> None:
        self._first: dict[str, Any] = {"status": "need_tools", "tool_requests": tool_requests}
        self._failure_code = failure_code
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return self._first
        raise LLMAdapterError(self._failure_code)

    async def complete_text(self, **_: Any) -> str:
        raise AssertionError("retrieval block does not use complete_text")


class _AlwaysTransientFailAdapter:
    """Every LLM call raises `llm_call_failed` -- the failure hits round 1
    before any tool runs, so there is nothing to salvage."""

    def __init__(self, *, failure_code: str = "llm_call_failed") -> None:
        self._failure_code = failure_code
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        raise LLMAdapterError(self._failure_code)

    async def complete_text(self, **_: Any) -> str:
        raise AssertionError("retrieval block does not use complete_text")


def _context_package(tool_grant=("get_entity", "search_knowledge", "traverse_relationship")) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Fetch the prerequisite.",
        structured_fields=StepInstructionFields(goal="Fetch the prerequisite.", description="Fetch it."),
        dependency_state=[],
        tool_grant=list(tool_grant),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


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


def _ready_result(facts=None, basis="wiki_derived"):
    return {
        "status": "ready",
        "result": {
            "certainty_basis": basis,
            "confidence": 1.0,
            "facts": facts or {"found": True},
        }
    }


async def test_round_1_ready_completes_immediately(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_ready_result()])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 0
    assert len(adapter.calls) == 1


async def test_one_round_of_tool_calls_then_ready_happy_path(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "123456", "entity_type": "course"}}]
        },
        _ready_result({"key": "value"})
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
    assert len(adapter.calls) == 2
    assert len(result.tool_audit_trail) == 1


async def test_tool_called_twice_in_same_round_with_different_arguments_does_not_clobber(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}},
                {"tool_name": "get_entity", "arguments": {"entity_id": "222", "entity_type": "course"}}
            ]
        },
        _ready_result()
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 2
    
    assert len(result.tool_audit_trail) == 2
    args = [t.arguments for t in result.tool_audit_trail]
    assert any(a.get("entity_id") == "111" for a in args)
    assert any(a.get("entity_id") == "222" for a in args)

async def test_malformed_tool_requests_repaired_before_execution(fake_llm_adapter_factory):
    # A live-eval run found the model routinely emitting tool_requests with
    # the wrong keys (e.g. "name"/"params" instead of "tool_name"/
    # "arguments"). Previously that request just silently failed inside
    # execute_tool_round, wasting the whole round. Now the round output goes
    # through the same validate/repair loop the final result already gets.
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [{"name": "get_entity", "params": {"entity_id": "111", "entity_type": "course"}}],
        },
        # Repair call: the model is re-prompted with the schema + errors and
        # fixes the key names.
        {
            "status": "need_tools",
            "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}],
        },
        _ready_result(),
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    # The repaired request reached the real tool call (registry.call_count
    # only increments on an actual invocation) instead of being skipped as
    # unresolvable, which is what happened before this fix.
    assert registry.call_count == 1
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].tool_name == "get_entity"
    # round1 (malformed) + repair + finalize ready = 3 LLM calls.
    assert len(adapter.calls) == 3


async def test_tool_not_in_grant_skipped_without_aborting_round(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "search_knowledge", "arguments": {"query": "q"}}, # Not granted
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}  # Granted
            ]
        },
        _ready_result()
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(tool_grant=("get_entity",)),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1  # Only get_entity was actually executed
    
    assert len(result.tool_audit_trail) == 2
    # search_knowledge should be ok=False
    assert result.tool_audit_trail[0].tool_name == "search_knowledge"
    assert result.tool_audit_trail[0].output_ok is False


async def test_tool_call_that_raises_skipped_without_aborting_round(fake_llm_adapter_factory):
    class ThrowingRegistry(_CountingToolRegistry):
        def get(self, name: str):
            descriptor = self._inner.get(name)
            if name == "search_knowledge":
                async def _throw(*args, **kwargs):
                    raise RuntimeError("simulated error")
                return descriptor.model_copy(update={"callable": _throw})
            return super().get(name)

    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "search_knowledge", "arguments": {"query": "q"}},
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}
            ]
        },
        _ready_result()
    ])
    registry = ThrowingRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(result.tool_audit_trail) == 2
    assert result.tool_audit_trail[0].tool_name == "search_knowledge"
    assert result.tool_audit_trail[0].output_ok is False


async def test_round_budget_exhausted_forces_finalize_and_fails_closed_if_no_result(fake_llm_adapter_factory):
    # Model always wants more tools, never status=ready
    responses = [
        {"status": "need_tools", "tool_requests": []} for _ in range(_MAX_ROUNDS)
    ]
    # The last round is forced to finalize, but the model ignores it and returns no result
    adapter = fake_llm_adapter_factory(responses)
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert len(adapter.calls) == _MAX_ROUNDS
    assert any("round_budget_exhausted" in w for w in result.warnings)
    
    # Check that the last round's prompt actually included the finalize instruction
    last_prompt = adapter.calls[-1]["user_prompt"]
    assert "NO MORE TOOL CALLS" in last_prompt


async def test_malformed_result_on_finalize_triggers_repair(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "ready",
            "result": {"certainty_basis": "official_record"} # Missing required 'confidence' and 'facts'
        },
        # Repair call response
        {
            "certainty_basis": "official_record",
            "confidence": 1.0,
            "facts": {"found": True}
        }
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(adapter.calls) == 2
    repair_prompt = adapter.calls[1]["user_prompt"]
    assert "schema validation" in repair_prompt


async def test_repair_exhausted_fails_closed(fake_llm_adapter_factory):
    bad_response = {
        "status": "ready",
        "result": {"certainty_basis": "official_record"} # Missing 'facts'
    }
    bad_repair = {"certainty_basis": "official_record"}
    adapter = fake_llm_adapter_factory([bad_response, bad_repair, bad_repair])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("schema_repair_exhausted" in w for w in result.warnings)


async def test_transient_llm_failure_mid_loop_salvages_accumulated_tool_results():
    """A transient `llm_call_failed` on a round's LLM call, AFTER earlier
    rounds already fetched facts, must finalize on those facts instead of
    discarding the whole step. Regression for the multi_prereq live-eval case
    where a mid-loop transport blip failed step 1a with an empty audit trail
    and forced an expensive Planner re-plan.
    """
    adapter = _NeedToolsThenTransientFailAdapter(
        [{"tool_name": "get_entity", "arguments": {"entity_id": "123456", "entity_type": "course"}}]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    # Finalized rather than failed.
    assert result.status == "succeeded"
    assert result.result is not None
    # The facts gathered before the blip survive.
    assert result.result["facts"], "salvaged facts must not be empty"
    assert len(result.tool_audit_trail) == 1
    # Degradation is explicit and honestly low-confidence, so a downstream
    # success-check treats this as partial rather than fully trustworthy.
    assert result.certainty.confidence == _DEGRADED_FINALIZE_CONFIDENCE
    assert any("retrieval_degraded_partial_finalize" in w for w in result.warnings)
    # Exactly two LLM calls: the need_tools round + the failing round. The
    # salvage itself spends NO extra LLM call.
    assert len(adapter.calls) == 2


async def test_transient_llm_failure_before_any_tools_fails_closed():
    """When the transient failure hits before any tool has run, there is
    nothing to salvage, so the step must still fail closed rather than
    fabricate an empty-facts answer."""
    adapter = _AlwaysTransientFailAdapter()
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert not any("retrieval_degraded_partial_finalize" in w for w in result.warnings)
    assert registry.call_count == 0


async def test_returns_subagent_result_shape_matching_generic_paths_output(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_ready_result()])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status in ("succeeded", "partial", "failed")
    assert result.certainty is not None
    assert isinstance(result.assumptions, list)
    assert isinstance(result.warnings, list)
    assert isinstance(result.tool_audit_trail, list)
    assert result.needs_another_round is False


# ── Fact grounding ───────────────────────────────────────────────────────────
#
# Retrieval FETCHES; it cannot compute. Measured live (2026-07-16) it computed
# anyway -- a 17-number sum done in its head, wrong (63.0; truth 62.5), stamped
# confidence 1.0, and indistinguishable from a fetched fact once in state. The
# tell is `source`: a real fact cites a TOOL, that one cited a sentence.


def _need_get_entity() -> dict[str, Any]:
    """Round 1: make a real `get_entity` call, so the audit trail names a tool.

    Groundedness is only decidable against a trail that recorded something --
    with no tool called, the guard deliberately abstains.
    """
    return {
        "status": "need_tools",
        "tool_requests": [
            {"tool_name": "get_entity", "arguments": {"entity_id": "123456", "entity_type": "course"}}
        ],
    }


async def test_fabricated_fact_is_dropped_on_the_shape_the_model_actually_emits(fake_llm_adapter_factory):
    """The regression the previous unit tests could not see.

    They called `_drop_ungrounded_facts` directly with `facts` as a LIST, and
    passed. But nothing hands this guard a list: `facts` is declared
    `{"type": "object"}`, so `_flatten_fact_list_to_object` has already turned
    the model's list into a dict keyed by label by the time the guard runs
    (`_normalize_result` -> `_validate_schema` -> guard). The guard opened with
    `if not isinstance(facts, list): return candidate, []` -- so it returned
    immediately, every call, and had never once fired in production.

    Measured live (2026-07-16, `credits_remaining`): this exact fact reached
    state with `warnings: []` and `tool_audit_trail: ['get_entity']` -- a trail
    naming a tool, a source naming none -- and composition published 63.0. The
    student's real total is 62.5; the model's own transcribed list, one field
    above, sums to 62.5.

    So this test feeds the list the model really emits and drives the real
    entry point, which is the only way the flattening is in the path at all.
    This file's docstring already said every scenario goes through
    `run_retrieval_subagent`; those three tests were the only ones that did not,
    and they were the ones that lied.
    """
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        {
            "status": "ready",
            "result": {
                "certainty_basis": "official_record",
                "confidence": 1.0,
                # A list, exactly as the live run's retrieval emitted it.
                "facts": [
                    {
                        "key": "completedCourses",
                        "value": [{"courseNumber": "00940224", "creditsEarned": 4.0}],
                        "source": "get_entity completed_courses for user 6a586297a1a0209ebc175675",
                        "confidence": 1.0,
                    },
                    {
                        "key": "totalCreditsEarned",
                        "value": 63.0,
                        "source": "sum of creditsEarned across all 17 completed courses",
                        "confidence": 1.0,
                    },
                ],
            },
        },
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    facts = result.result["facts"]
    assert "totalCreditsEarned" not in facts, (
        "retrieval cannot compute; a fact citing mental arithmetic must not survive"
    )
    assert "completedCourses" in facts, "the fetched fact beside it must be untouched"
    assert any("totalCreditsEarned" in w for w in result.warnings)


async def test_a_cited_tool_survives_the_model_dressing_up_the_name(fake_llm_adapter_factory):
    """Substring, not equality: `get_entity(student_profile)` is an honest
    citation of a call that happened, and must not be mistaken for a fabrication."""
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        {
            "status": "ready",
            "result": {
                "certainty_basis": "official_record",
                "confidence": 1.0,
                "facts": [
                    {"key": "degreeId", "value": "x", "source": "get_entity(student_profile)", "confidence": 1.0},
                    {"key": "grade", "value": 85, "source": "get_entity: completed_courses", "confidence": 1.0},
                ],
            },
        },
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert set(result.result["facts"]) == {"degreeId", "grade"}
    assert result.warnings == []


async def test_a_fact_carrying_no_source_at_all_is_kept(fake_llm_adapter_factory):
    """`facts` is only `{"type": "object"}` -- a bare `{"degreeId": "x"}` with no
    per-fact `source` is a legal, common shape. There is no citation to judge
    there, so the guard must abstain: dropping it would discard genuinely
    fetched data on the grounds that the model was terse.

    The guard adjudicates CITATIONS, not facts. Only a source that names
    something, where that something is no tool we called, is a fabrication tell.
    """
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        {
            "status": "ready",
            "result": {
                "certainty_basis": "official_record",
                "confidence": 1.0,
                "facts": {"degreeId": "6a477d511f64e5fd20129b44", "currentSemesterCode": "2025-2"},
            },
        },
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert set(result.result["facts"]) == {"degreeId", "currentSemesterCode"}
    assert result.warnings == []


async def test_nothing_is_dropped_when_no_tool_was_recorded(fake_llm_adapter_factory):
    """Conservative by design: an empty audit trail is a salvage/cache path, not
    evidence of fabrication. This guard exists to catch the invented fact standing
    amongst real ones -- not to adjudicate a block that recorded no calls."""
    adapter = fake_llm_adapter_factory([
        {
            "status": "ready",
            "result": {
                "certainty_basis": "wiki_derived",
                "confidence": 1.0,
                "facts": [{"key": "k", "value": 1, "source": "somewhere", "confidence": 1.0}],
            },
        },
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert "k" in result.result["facts"]
    assert result.warnings == []
