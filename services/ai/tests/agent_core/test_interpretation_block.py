"""Tests for `InterpretationReasoningBlock`/`run_interpretation_subagent`
(docs/agent/agent_plans/INTERPRETATION_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_interpretation_subagent`
entry point. Uses in-file stub tools (rather than the real `interpret_text`/
`get_entity`, which need a configured academic graph engine not available in
this unit-test environment) so success/failure/citation content is directly
controllable -- mirrors `test_tool_round.py`'s own approach.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.subagents.interpretation_block import (
    _MAX_ROUNDS,
    _MIN_ROUNDS,
    run_interpretation_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry


class _FakeInput(BaseModel):
    source: str = ""
    question: str = ""


def _make_registry(*, ok: bool = True, page: str = "retake-policy") -> ToolRegistry:
    registry = ToolRegistry()

    async def _interpret_text(payload: _FakeInput, _ok: bool = ok, _page: str = page) -> ToolOutputEnvelope:
        if not _ok:
            return ToolOutputEnvelope(ok=False, data=None, error="cannot_determine")
        return ToolOutputEnvelope(
            ok=True,
            data={"question": payload.question, "source": payload.source, "answer": "Up to 2 retakes allowed.", "citedSection": "Retakes"},
        )

    registry.register(
        ToolDescriptor(
            name="interpret_text",
            description="test stub",
            input_model=_FakeInput,
            output_model=ToolOutputEnvelope,
            side_effect="read",
            callable=_interpret_text,
        )
    )
    return registry


def _context_package(tool_grant=("interpret_text", "get_entity", "search_knowledge")) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="How many times can I retake this course?",
        structured_fields=StepInstructionFields(goal="Interpret the retake policy.", description="Interpret it."),
        dependency_state=[],
        tool_grant=list(tool_grant),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


def _need_tools(tool_name="interpret_text", arguments=None):
    return {
        "status": "need_tools",
        "tool_requests": [{"tool_name": tool_name, "arguments": arguments or {"source": "retake-policy", "question": "q"}}],
    }


def _ready_result(page="retake-policy"):
    return {
        "status": "ready",
        "result": {
            "certainty_basis": "llm_interpretation",
            "confidence": 0.9,
            "source_ref": {"page": page, "section": "Retakes"},
            "assumptions": [],
            "answer": "Up to 2 retakes allowed.",
        },
    }


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


async def test_round_1_ready_is_not_honored_even_with_a_well_formed_result(fake_llm_adapter_factory):
    assert _MIN_ROUNDS == 2
    adapter = fake_llm_adapter_factory([_ready_result(), _need_tools(), _ready_result()])
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    # Round 1's premature "ready" is ignored; round 2 calls a tool; round 3 finalizes.
    assert len(adapter.calls) == 3
    assert result.status == "succeeded"
    assert registry.call_count == 1


async def test_happy_path_tool_call_then_finalize(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_need_tools(), _ready_result()])
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
    assert result.certainty.source_ref.page == "retake-policy"
    assert len(result.tool_audit_trail) == 1


async def test_malformed_tool_requests_repaired_before_execution(fake_llm_adapter_factory):
    # Same fix as retrieval_block's -- a round's tool_requests previously
    # went straight to execute_tool_round unvalidated, so wrong keys (e.g.
    # "name"/"params" instead of "tool_name"/"arguments") silently wasted
    # the whole round. Now it's repaired first via the shared
    # `_repair_tool_requests_if_needed` helper.
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "need_tools",
                "tool_requests": [{"name": "interpret_text", "params": {"source": "retake-policy", "question": "q"}}],
            },
            {
                "status": "need_tools",
                "tool_requests": [{"tool_name": "interpret_text", "arguments": {"source": "retake-policy", "question": "q"}}],
            },
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].tool_name == "interpret_text"
    # round1 (malformed) + repair + round2 (finalize) = 3 LLM calls.
    assert len(adapter.calls) == 3


async def test_tool_not_in_grant_skipped_without_aborting_round(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "need_tools",
                "tool_requests": [
                    {"tool_name": "search_knowledge", "arguments": {"query": "q"}},
                    {"tool_name": "interpret_text", "arguments": {"source": "retake-policy", "question": "q"}},
                ],
            },
            _ready_result(),
        ]
    )
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(tool_grant=("interpret_text",)),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1  # only interpret_text actually executed
    assert len(result.tool_audit_trail) == 2
    assert result.tool_audit_trail[0].tool_name == "search_knowledge"
    assert result.tool_audit_trail[0].output_ok is False


async def test_interpret_text_cannot_determine_is_a_normal_failed_but_executed_call(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_need_tools(), _need_tools(), {"status": "need_tools", "tool_requests": []}])
    registry = _CountingToolRegistry(_make_registry(ok=False))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    # Never a successfully-interpreted source -> forced finalize on the last
    # round produces no result -> fails closed.
    assert result.status == "failed"
    assert registry.call_count >= 1
    assert all(record.output_ok is False for record in result.tool_audit_trail)


async def test_no_source_ever_interpreted_fails_closed_missing_required_source_ref(fake_llm_adapter_factory):
    # Model tries to finalize on the forced final round with an answer but no
    # source_ref -- schema requires it, so this must fail, never fabricate a
    # citation.
    adapter = fake_llm_adapter_factory(
        [
            _need_tools(),
            {
                "status": "ready",
                "result": {
                    "certainty_basis": "llm_interpretation",
                    "confidence": 0.5,
                    "answer": "Probably up to 2 retakes.",
                },
            },
        ]
    )
    registry = _CountingToolRegistry(_make_registry(ok=False))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"


async def test_gap5_warning_surfaces_in_final_subagent_result(fake_llm_adapter_factory):
    ready_with_warning = _ready_result()
    ready_with_warning["warnings"] = [
        "Cannot confirm the absence of a temporary exception; only static wiki text was checked."
    ]
    adapter = fake_llm_adapter_factory([_need_tools(), ready_with_warning])
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert any("temporary exception" in w for w in result.warnings)


async def test_malformed_result_on_finalize_triggers_repair(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _need_tools(),
            {
                "status": "ready",
                "result": {"certainty_basis": "llm_interpretation"},  # missing confidence/source_ref/answer
            },
            {
                "certainty_basis": "llm_interpretation",
                "confidence": 0.9,
                "source_ref": {"page": "retake-policy", "section": "Retakes"},
                "answer": "Up to 2 retakes allowed.",
            },
        ]
    )
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(adapter.calls) == 3


async def test_repair_exhausted_fails_closed(fake_llm_adapter_factory):
    bad_response = {"status": "ready", "result": {"certainty_basis": "llm_interpretation"}}
    bad_repair = {"certainty_basis": "llm_interpretation"}
    adapter = fake_llm_adapter_factory([_need_tools(), bad_response, bad_repair, bad_repair])
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("schema_repair_exhausted" in w for w in result.warnings)


async def test_returns_subagent_result_shape_matching_the_generic_paths_output(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_need_tools(), _ready_result()])
    registry = _CountingToolRegistry(_make_registry(ok=True))

    result = await run_interpretation_subagent(
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
    assert _MAX_ROUNDS == 3
