"""Tests for `RetrievalReasoningBlock`/`run_retrieval_subagent`
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_retrieval_subagent` entry point.

Retrieval emits SELECTORS, not values (see `subagents/fact_projection.py`), so
these drive a stubbed tool layer that returns a known envelope -- a selector has
to have something real to point at, and a test whose tool call fails is testing
the error path, not the happy one.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent_core.certainty import CertaintyTag
from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.subagents.retrieval_block import (
    _DEGRADED_FINALIZE_CONFIDENCE,
    _MAX_ROUNDS,
    run_retrieval_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolRegistry

# What the stubbed `get_entity` returns. Shaped like the real thing: the payload
# under `data`, and a certainty the TOOL declares -- `get_entity` really does
# return `CertaintyTag(basis="official_record", confidence=1.0)` for a Mongo
# entity, which is the value projection reads instead of asking the model.
_COURSE_ENVELOPE = ToolOutputEnvelope(
    ok=True,
    data={"courseNumber": "123456", "credits": 3.0, "prereqs": {"logic": "OR", "courses": ["111", "222"]}},
    certainty=CertaintyTag(basis="official_record", confidence=1.0),
)


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
    """Real descriptors (so argument validation still runs), stubbed callables.

    The default registry's `get_entity` reaches Mongo, which no unit test has --
    every call would come back `ok=False`, and a selector into a failed envelope
    tests the error path. Stubbing the callable keeps the input model, the grant
    check, and the audit trail real while making the DATA deterministic.
    """

    def __init__(self, inner: ToolRegistry, *, envelope: ToolOutputEnvelope = _COURSE_ENVELOPE) -> None:
        self._inner = inner
        self.call_count = 0
        self._envelope = envelope

    def get(self, name: str):
        descriptor = self._inner.get(name)

        async def _stub_callable(_payload):
            self.call_count += 1
            return self._envelope

        return descriptor.model_copy(update={"callable": _stub_callable})

    def has(self, name: str) -> bool:
        return self._inner.has(name)


def _need_get_entity(entity_id: str = "123456") -> dict[str, Any]:
    return {
        "status": "need_tools",
        "tool_requests": [
            {"tool_name": "get_entity", "arguments": {"entity_id": entity_id, "entity_type": "course"}}
        ],
    }


def _ready_selecting(*selectors: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """A finalize round: the model points at data, it never carries it."""
    result: dict[str, Any] = {
        "facts": list(selectors) or [{"key": "courseNumber", "from": "call_1", "path": "data.courseNumber"}]
    }
    result.update(extra)
    return {"status": "ready", "result": result}


async def test_one_round_of_tool_calls_then_ready_happy_path(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_need_get_entity(), _ready_selecting()])
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
    # The value came out of the recorded envelope, not out of the model.
    assert result.result["facts"]["courseNumber"]["value"] == "123456"


async def test_the_value_is_read_from_the_envelope_not_taken_from_the_model(fake_llm_adapter_factory):
    """CAUGHT LIVE (2026-07-16, `credits_remaining`).

    Retrieval used to author the values, and authored `totalCreditsEarned: 63.0`
    -- a 17-number sum done in its head, wrong (the truth is 62.5), stamped
    confidence 1.0 and indistinguishable from a fetched fact once in state.

    A selector has no `value` field. Even if the model bolts one on, projection
    reads only key/from/path, so the number it made up cannot reach state.
    """
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting(
            {
                "key": "credits",
                "from": "call_1",
                "path": "data.credits",
                "value": 63.0,  # a lie, bolted onto a selector
            }
        ),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert result.result["facts"]["credits"]["value"] == 3.0, "the envelope's value must win"
    assert "63.0" not in json.dumps(result.result, default=str)


async def test_a_nested_object_is_selected_by_one_path(fake_llm_adapter_factory):
    """`academicPath` is a real nested object on the student profile, so grouped
    data needs no composite selector -- one fact, one path."""
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting({"key": "prereqs", "from": "call_1", "path": "data.prereqs"}),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.result["facts"]["prereqs"]["value"] == {"logic": "OR", "courses": ["111", "222"]}


async def test_certainty_is_taken_from_the_tool_that_served_the_data(fake_llm_adapter_factory):
    """CAUGHT LIVE (2026-07-16, `presupposition_conflict` step 1a).

    The result omitted `certainty_basis`, so `result_normalizer`'s defaults
    backfilled `llm_interpretation` -- tagging a plain `get_entity` read as model
    guesswork while the tool had already declared `official_record` at 1.0. The
    envelope knew; nobody asked it. Now nobody asks the model.
    """
    adapter = fake_llm_adapter_factory([_need_get_entity(), _ready_selecting()])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0
    assert result.result["facts"]["courseNumber"]["source"].startswith("get_entity(")


async def test_a_step_that_resolves_nothing_fails_instead_of_reporting_success(fake_llm_adapter_factory):
    """CAUGHT LIVE (2026-07-16, `presupposition_conflict` step 1a).

    Every fact was thrown away and the step still returned `succeeded` at
    confidence 0.9 with `facts: {}`. The Planner recorded a success, never
    re-fetched, and the student's degree context vanished from the turn with no
    visible symptom. A step that produced nothing must say so, so the Monitor
    can replan.
    """
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting({"key": "totalCreditsEarned", "from": "call_1", "path": "data.totalCreditsEarned"}),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("no_facts_projected" in w for w in result.warnings)
    assert any("does not exist" in w for w in result.warnings)


async def test_a_ready_with_no_tool_calls_has_nothing_to_point_at(fake_llm_adapter_factory):
    """Retrieval FETCHES. A finalize that called no tool has, by construction,
    nothing to select from -- and previously would have returned whatever facts
    the model felt like inventing. There is no handle to name, so it fails."""
    adapter = fake_llm_adapter_factory([_ready_selecting()])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert registry.call_count == 0
    assert any("no_facts_projected" in w for w in result.warnings)


async def test_a_partially_resolved_step_keeps_what_landed_and_surfaces_what_did_not(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting(
            {"key": "courseNumber", "from": "call_1", "path": "data.courseNumber"},
            {"key": "bogus", "from": "call_1", "path": "data.nope"},
        ),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert set(result.result["facts"]) == {"courseNumber"}
    assert any("retrieval_selector_unresolved" in w and "bogus" in w for w in result.warnings)


async def test_tool_called_twice_in_same_round_with_different_arguments_does_not_clobber(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}},
                {"tool_name": "get_entity", "arguments": {"entity_id": "222", "entity_type": "course"}},
            ],
        },
        # Two distinct calls -> two distinct handles.
        _ready_selecting(
            {"key": "first", "from": "call_1", "path": "data.courseNumber"},
            {"key": "second", "from": "call_2", "path": "data.courseNumber"},
        ),
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
    assert set(result.result["facts"]) == {"first", "second"}


async def test_malformed_tool_requests_repaired_before_execution(fake_llm_adapter_factory):
    # A live-eval run found the model routinely emitting tool_requests with the
    # wrong keys (e.g. "name"/"params" instead of "tool_name"/"arguments").
    # Previously that request just silently failed inside execute_tool_round,
    # wasting the whole round. Now the round output goes through the same
    # validate/repair loop the final result already gets.
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
        _ready_selecting(),
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
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].tool_name == "get_entity"
    # round1 (malformed) + repair + finalize ready = 3 LLM calls.
    assert len(adapter.calls) == 3


async def test_tool_not_in_grant_skipped_without_aborting_round(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "search_knowledge", "arguments": {"query": "q"}},  # Not granted
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}},  # Granted
            ],
        },
        _ready_selecting(),
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
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}},
            ],
        },
        # search_knowledge raised, so its envelope is the failure shape and
        # call_2 is the one with real data.
        _ready_selecting({"key": "courseNumber", "from": "call_2", "path": "data.courseNumber"}),
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
    responses = [{"status": "need_tools", "tool_requests": []} for _ in range(_MAX_ROUNDS)]
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
        _need_get_entity(),
        {"status": "ready", "result": {}},  # missing required 'facts'
        # Repair call response
        {"facts": [{"key": "courseNumber", "from": "call_1", "path": "data.courseNumber"}]},
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(adapter.calls) == 3
    repair_prompt = adapter.calls[2]["user_prompt"]
    assert "schema validation" in repair_prompt


async def test_repair_exhausted_fails_closed(fake_llm_adapter_factory):
    bad_response = {"status": "ready", "result": {}}  # missing 'facts'
    bad_repair: dict[str, Any] = {}
    adapter = fake_llm_adapter_factory([_need_get_entity(), bad_response, bad_repair, bad_repair])
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
    """A transient `llm_call_failed` on a round's LLM call, AFTER earlier rounds
    already fetched facts, must finalize on those facts instead of discarding the
    whole step. Regression for the multi_prereq live-eval case where a mid-loop
    transport blip failed step 1a with an empty audit trail and forced an
    expensive Planner re-plan.

    The salvage path hand-builds the OUTPUT shape directly (it has no model round
    to emit selectors), which is why `_RETRIEVAL_OUTPUT_SCHEMA` survives
    projection unchanged.
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
    """When the transient failure hits before any tool has run, there is nothing
    to salvage, so the step must still fail closed rather than fabricate an
    empty-facts answer."""
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
    adapter = fake_llm_adapter_factory([_need_get_entity(), _ready_selecting()])
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


# --- Out-of-contract keys --------------------------------------------------
# Projection closed the `facts` door; this closes the side door the model went
# round it by. Drives the real entry point, because the guard only runs inside
# the normalize/validate/repair path.


async def test_out_of_contract_metadata_key_is_dropped(fake_llm_adapter_factory):
    """The exact payload from the 2026-07-16 `completed_courses` run.

    The model appended a key that appears in no schema, carrying an aggregate no
    tool computed (the 17 courses total 62.5, not 63.5), which then inherited the
    block's `official_record`/1.0 and outranked the deterministic calculator.
    Selectors mean it can no longer put a number in `facts` -- this proves it
    cannot put one beside `facts` either.
    """
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting(metadata={"total_courses": 17, "total_credits_earned": 63.5}),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert "metadata" not in result.result
    # The fabricated total must be gone from the payload entirely, not merely
    # moved -- it is the number that reached the student.
    assert "63.5" not in json.dumps(result.result, default=str)
    assert any("retrieval_dropped_out_of_contract_key: metadata" in w for w in result.warnings)
    # ...and the genuinely fetched data is untouched.
    assert "courseNumber" in result.result["facts"]


async def test_declared_keys_all_survive_the_projection(fake_llm_adapter_factory):
    """The projection must strip only what the contract never promised."""
    adapter = fake_llm_adapter_factory([
        _need_get_entity(),
        _ready_selecting(
            source_ref={"page": "some-page", "section": None, "reasoning_path": None},
            assumptions=["assumed the spring term"],
            notes="chatter that is not in the contract",
        ),
    ])

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=_CountingToolRegistry(build_default_tool_registry()),
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert "notes" not in result.result
    assert set(result.result) == {"certainty_basis", "confidence", "source_ref", "assumptions", "facts"}
    # These are read by `run_retrieval_subagent` -- dropping one silently
    # downgrades every downstream certainty judgement.
    assert result.assumptions == ["assumed the spring term"]
