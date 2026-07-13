"""`interpret_text` -- LLM-reasoning extraction of a rule/fact from wiki prose
(docs/agent/AGENT_VISION.md §5, primitive 4). One of only two primitives
where an LLM call is intrinsic to the operation itself (§4).

`source` is treated as a wiki slug -- fetched via `get_entity(entity_type=
"wiki_page", entity_id=source)`, the generic wiki-entity catch-all that
works for any real slug (course/track/program/minor/faculty/concept),
exactly like `search_over_state` already composes `get_entity` rather than
reading the graph directly. No new data access path was invented.

Follows `request_understanding.py`'s `BaseReasoningBlock` pattern (single-
shot, no tools, schema-validate-then-repair) with **one deliberate
behavioral difference confirmed with the user**: `request_understanding.py`
always fails *open* (falls back to a usable default so a turn is never
blocked); `interpret_text` must fail *closed* per §5.1 -- any failure path
(source not found, LLM unavailable, schema never becomes valid, or the LLM
itself reports `status="cannot_determine"`) returns `ok=False`, never a
best-guess interpretation.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.agent_core.planning.state import CertaintyTag, SourceRef
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "interpret_text"

INTERPRET_TEXT_V1 = "interpret_text_v1"
_OUTPUT_SCHEMA_NAME = "interpret_text_output_v1"
_MAX_SOURCE_CHARS = 6000
_MAX_SCHEMA_REPAIR_ATTEMPTS = 2
# This primitive builds its own `ChatLLMAdapter()` (see `run_interpret_text`
# below) rather than receiving one threaded through from a caller-configured
# `reasoning_config` -- so unlike every other reasoning-block call site in
# this codebase (Boundary Handler, Planner, subagent roles), nothing bounds
# its underlying LLM call unless set explicitly here. Without this, `timeout`
# stays `None` all the way to the LangChain/OpenAI client, which falls back
# to the SDK's own default -- long enough that a real network stall hangs
# the entire turn well past any of this codebase's own per-component
# timeouts, invisible to logging since it never goes through the caller's
# adapter (found via a live-eval run: a 300s test-level cutoff was the only
# thing that ever stopped a get_policy_answer call stuck in here).
_TIMEOUT_SECONDS = 30.0

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["determined", "cannot_determine"]},
        "answer": {"type": ["string", "null"]},
        "cited_section": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["status", "answer", "cited_section", "confidence"],
    "additionalProperties": False,
}


class InterpretTextInput(BaseModel):
    source: str
    question: str


class _InterpretTextBlockInput(BaseReasoningBlockInput):
    source_slug: str
    source_content: str


class _InterpretTextBlockOutput(BaseReasoningBlockOutput):
    determined: bool = False
    answer: str | None = None
    cited_section: str | None = None


def _interpret_text_contract() -> PromptContract:
    return PromptContract(
        name=INTERPRET_TEXT_V1,
        version="1.0.0",
        role_prompt=(
            "You are the interpret_text primitive for the UniPilot Agent, a Technion "
            "academic advising assistant. You are given the full text of one wiki page "
            "and one specific question. Read the text closely and answer only from what "
            "it actually says.\n\n"
            "You must cite the exact section/heading the answer came from. If the text "
            "does not clearly answer the question, set status to 'cannot_determine' -- "
            "never guess, never fill a gap with outside knowledge, never infer a rule "
            "the text doesn't actually state."
        ),
        instructions=[
            "Use only the supplied source text -- never outside knowledge, never a prior turn.",
            "status='determined' requires a real citation in cited_section; never leave "
            "cited_section null when status='determined'.",
            "status='cannot_determine' requires answer and cited_section to both be null.",
            "confidence reflects how directly and unambiguously the text answers the "
            "question -- reserve 0.9+ for an explicit, unambiguous statement; a source "
            "that implies but doesn't state the answer should score much lower, or be "
            "'cannot_determine' instead.",
        ],
        allowed_context_fields=None,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        default_risk_level="medium",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not invent a rule or fact not actually present in the source text.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_interpret_text_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: _InterpretTextBlockInput) -> str:
    payload = {
        "question": block_input.objective,
        "source_slug": block_input.source_slug,
        "source_text": block_input.source_content,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class InterpretTextReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails closed: any raised error, an LLM call
    that never becomes schema-valid, or an explicit `cannot_determine`
    verdict all resolve to `determined=False` -- never a guessed answer.
    """

    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or _build_prompt_registry(), **kwargs
        )

    async def _run_internal(
        self, block_input: _InterpretTextBlockInput, telemetry: RunTelemetry
    ) -> _InterpretTextBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or INTERPRET_TEXT_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)

        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=_build_user_prompt(block_input),
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )

        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if not validation.valid:
            repair_outcome = await self._repair_schema(
                initial_result=normalized,
                initial_errors=validation.errors,
                output_schema=block_input.output_schema,
                max_attempts=_MAX_SCHEMA_REPAIR_ATTEMPTS,
                block_input=block_input,
                telemetry=telemetry,
            )
            if not repair_outcome.valid:
                return self._cannot_determine_output(reason="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_output(normalized)

    def _to_output(self, normalized: dict[str, Any]) -> _InterpretTextBlockOutput:
        status = normalized.get("status")
        try:
            confidence = max(0.0, min(1.0, float(normalized.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        answer = normalized.get("answer")
        cited_section = normalized.get("cited_section")

        # Schema-valid but semantically hollow (a determined verdict with no
        # real citation) still fails closed -- schema validation alone can't
        # express "cited_section required when status='determined'".
        if status != "determined" or not (isinstance(answer, str) and answer.strip()) or not (
            isinstance(cited_section, str) and cited_section.strip()
        ):
            return self._cannot_determine_output(reason="model_reported_cannot_determine")

        return _InterpretTextBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=confidence,
            determined=True,
            answer=answer,
            cited_section=cited_section,
        )

    def _cannot_determine_output(self, *, reason: str) -> _InterpretTextBlockOutput:
        return _InterpretTextBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"interpret_text_cannot_determine: {reason}"],
            determined=False,
            answer=None,
            cited_section=None,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _InterpretTextBlockOutput:
        return self._cannot_determine_output(reason=f"reasoning_block_failed: {reason}")


async def run_interpret_text(payload: InterpretTextInput) -> ToolOutputEnvelope:
    source = (payload.source or "").strip()
    question = (payload.question or "").strip()
    if not source:
        return ToolOutputEnvelope(ok=False, data=None, error="source_required")
    if not question:
        return ToolOutputEnvelope(ok=False, data=None, error="question_required")

    entity_result = await run_get_entity(GetEntityInput(entity_type="wiki_page", entity_id=source))
    if not entity_result.ok:
        return ToolOutputEnvelope(ok=False, data=None, error=f"source_not_found: {source}")

    content = str(entity_result.data.get("content") or "")[:_MAX_SOURCE_CHARS]

    llm_adapter = ChatLLMAdapter()
    if not llm_adapter.is_available():
        return ToolOutputEnvelope(ok=False, data=None, error="llm_unavailable")

    block = InterpretTextReasoningBlock(llm_adapter=llm_adapter)
    block_input = _InterpretTextBlockInput(
        block_id=f"interpret_text:{source}",
        agent_name="interpret_text",
        objective=question,
        source_slug=source,
        source_content=content,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        output_schema=_OUTPUT_SCHEMA,
        prompt_contract_name=INTERPRET_TEXT_V1,
        llm_call_parameters=LLMCallParameters(timeout=_TIMEOUT_SECONDS),
    )
    output = await block.run(block_input)

    if not output.determined:
        return ToolOutputEnvelope(ok=False, data=None, error="cannot_determine")

    return ToolOutputEnvelope(
        ok=True,
        data={
            "question": question,
            "source": source,
            "answer": output.answer,
            "citedSection": output.cited_section,
        },
        certainty=CertaintyTag(
            basis="llm_interpretation",
            confidence=output.confidence,
            source_ref=SourceRef(page=source, section=output.cited_section),
        ),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Extract a rule/fact/interpretation from wiki prose for a specific question. "
    "Must return 'cannot determine' rather than guess; must cite the exact source read.",
    input_model=InterpretTextInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_interpret_text,
)
