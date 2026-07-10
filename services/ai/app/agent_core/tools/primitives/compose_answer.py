"""`compose_answer` -- turns structured, certainty-tagged results into grounded
prose (docs/agent/AGENT_VISION.md §5, primitive 9a). The other of only two
primitives where an LLM call is intrinsic to the operation itself (§4).

**Implemented standalone for now, per explicit user instruction** -- does
NOT reuse `agent_core.synthesis.synthesis.compose_answer` (the Orchestrator-
level entry point that runs the "Composition" role via the subagent/role
machinery, requires a `user_goal`, and consumes real `StateEntry` objects).
That reconciliation is deferred to when the subagent/role layer itself is
wired up; this primitive has its own self-contained `BaseReasoningBlock`
shape, following `request_understanding.py`'s/`interpret_text.py`'s pattern,
and its own fact-shape contract (see `_InterpretedFact` below) rather than
requiring a full `StateEntry`.

Fails closed (consistent with `interpret_text.py`, though AGENT_VISION §5.1
only names `apply_deterministic_rule`/`interpret_text` explicitly): a
malformed input fact, an unavailable LLM, or a schema/repair failure all
return `ok=False` rather than a degraded "best effort" composition that
might not actually be grounded in what it was given.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyBasis, CertaintyTag
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning.result_normalizer import GENERIC_BLANK_FIELD_PLACEHOLDER
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "compose_answer"

COMPOSE_ANSWER_V1 = "compose_answer_v1"
_OUTPUT_SCHEMA_NAME = "compose_answer_output_v1"
_MAX_SCHEMA_REPAIR_ATTEMPTS = 2

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer_text": {"type": "string"}},
    "required": ["answer_text"],
    "additionalProperties": False,
}

_VALID_CERTAINTY_BASES: frozenset[str] = frozenset(
    {"official_record", "wiki_derived", "predicted_pattern", "llm_interpretation", "hypothetical_simulation"}
)


class ComposeAnswerInput(BaseModel):
    facts_with_certainty: list[dict[str, Any]] = Field(default_factory=list)


class _InterpretedFact(BaseModel):
    """One validated `facts_with_certainty` entry. `data` and `certainty`
    are required -- a fact with no certainty tag is exactly the kind of
    ungrounded input this primitive must refuse rather than silently
    default a certainty for.
    """

    data: dict[str, Any]
    certainty: CertaintyTag
    label: str | None = None


class _ComposeAnswerBlockInput(BaseReasoningBlockInput):
    facts: list[_InterpretedFact]


class _ComposeAnswerBlockOutput(BaseReasoningBlockOutput):
    answer_text: str | None = None


def _validate_and_parse_facts(raw_facts: list[dict[str, Any]]) -> tuple[list[_InterpretedFact] | None, str | None]:
    if not raw_facts:
        return None, "facts_required"

    parsed: list[_InterpretedFact] = []
    for index, fact in enumerate(raw_facts):
        if not isinstance(fact, dict) or "data" not in fact:
            return None, f"fact_{index}_missing_data"
        certainty = fact.get("certainty")
        if not isinstance(certainty, dict) or certainty.get("basis") not in _VALID_CERTAINTY_BASES:
            return None, f"fact_{index}_missing_or_invalid_certainty"
        try:
            parsed.append(_InterpretedFact.model_validate(fact))
        except Exception:  # noqa: BLE001 -- malformed input must fail closed, never raise
            return None, f"fact_{index}_invalid_shape"
    return parsed, None


def _compose_answer_contract() -> PromptContract:
    return PromptContract(
        name=COMPOSE_ANSWER_V1,
        version="1.0.0",
        role_prompt=(
            "You are the compose_answer primitive for the UniPilot Agent, a Technion "
            "academic advising assistant. You are given a list of structured facts, each "
            "already tagged with its own certainty (basis + confidence). Your only job is "
            "to weave them into one coherent, grounded, well-organized answer for the "
            "student -- in the same language the facts/question are in.\n\n"
            "You have no tool access and receive no other context. You must never "
            "introduce a number, status, or fact that is not already present in the "
            "supplied facts, and you must preserve each fact's certainty distinction in "
            "the composed prose (e.g. distinguish an official record from a prediction) "
            "rather than flattening everything into uniform-sounding prose."
        ),
        instructions=[
            "Never introduce a number, status, or fact not already present in the supplied facts.",
            "Preserve each fact's certainty distinction (official record vs. wiki-derived "
            "vs. predicted vs. hypothetical vs. LLM-interpreted) in the composed prose -- "
            "never flatten them into one uniform tone.",
            "Never claim a write/mutation happened.",
            "Organize the answer clearly; do not just concatenate the facts verbatim.",
        ],
        allowed_context_fields=None,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.4,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a fact not present in the supplied results.",
            "Do not request or use any tool -- this primitive has zero tool access by design.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_compose_answer_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: _ComposeAnswerBlockInput) -> str:
    payload = {
        "facts": [fact.model_dump(mode="json") for fact in block_input.facts],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class ComposeAnswerReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools, zero tool grant by design."""

    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or _build_prompt_registry(), **kwargs
        )

    async def _run_internal(
        self, block_input: _ComposeAnswerBlockInput, telemetry: RunTelemetry
    ) -> _ComposeAnswerBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or COMPOSE_ANSWER_V1)
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
                return self._composition_failed_output(reason="schema_validation_failed")
            normalized = repair_outcome.result

        answer_text = normalized.get("answer_text")
        # `_normalize_result` (shared across every `BaseReasoningBlock`
        # subclass) substitutes a blank *required* string field with
        # `GENERIC_BLANK_FIELD_PLACEHOLDER` ("unknown") before schema
        # validation ever runs -- so a genuinely blank `answer_text` never
        # reaches here as an empty string, it reaches here as literally
        # "unknown". Both must be treated as "no usable answer."
        if (
            not (isinstance(answer_text, str) and answer_text.strip())
            or answer_text == GENERIC_BLANK_FIELD_PLACEHOLDER
        ):
            return self._composition_failed_output(reason="empty_answer_text")

        return _ComposeAnswerBlockOutput(
            status="completed", schema_valid=True, result=normalized, confidence=1.0, answer_text=answer_text
        )

    def _composition_failed_output(self, *, reason: str) -> _ComposeAnswerBlockOutput:
        return _ComposeAnswerBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"compose_answer_failed: {reason}"],
            answer_text=None,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _ComposeAnswerBlockOutput:
        return self._composition_failed_output(reason=f"reasoning_block_failed: {reason}")


def _aggregate_certainty(facts: list[_InterpretedFact]) -> CertaintyTag:
    weakest = min(facts, key=lambda fact: fact.certainty.confidence)
    bases: set[CertaintyBasis] = {fact.certainty.basis for fact in facts}
    basis: CertaintyBasis = bases.pop() if len(bases) == 1 else "llm_interpretation"
    return CertaintyTag(basis=basis, confidence=weakest.certainty.confidence)


async def run_compose_answer(payload: ComposeAnswerInput) -> ToolOutputEnvelope:
    facts, error = _validate_and_parse_facts(payload.facts_with_certainty)
    if error:
        return ToolOutputEnvelope(ok=False, data=None, error=error)

    llm_adapter = ChatLLMAdapter()
    if not llm_adapter.is_available():
        return ToolOutputEnvelope(ok=False, data=None, error="llm_unavailable")

    block = ComposeAnswerReasoningBlock(llm_adapter=llm_adapter)
    block_input = _ComposeAnswerBlockInput(
        block_id="compose_answer",
        agent_name="compose_answer",
        objective="Compose a grounded answer from the supplied certainty-tagged facts.",
        facts=facts,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        output_schema=_OUTPUT_SCHEMA,
        prompt_contract_name=COMPOSE_ANSWER_V1,
    )
    output = await block.run(block_input)

    if output.answer_text is None:
        return ToolOutputEnvelope(ok=False, data=None, error="composition_failed")

    return ToolOutputEnvelope(
        ok=True,
        data={"answerText": output.answer_text, "factCount": len(facts)},
        certainty=_aggregate_certainty(facts),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Compose grounded prose from accumulated, certainty-tagged results -- "
    "honoring every certainty tag rather than flattening them into uniform-sounding prose.",
    input_model=ComposeAnswerInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_compose_answer,
)
