"""Request Understanding (docs/agent/AGENT_VISION.md §3): the first layer --
turns the raw user message into the goal the Planner works from, or decides
the request is out of scope before the Planner ever runs.

Its own concrete `BaseReasoningBlock` shape (§6.2): single-shot, no tools --
there's no tool feedback loop to iterate against, just a decisive judgment
call. Its own prompt contract and tuned parameters replace the earlier
placeholder that borrowed the generic default contract.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, LLMCallParameters
from app.agent_core.request_understanding.schemas import (
    ConversationTurn,
    RequestUnderstandingReasoningBlockInput,
    RequestUnderstandingReasoningBlockOutput,
)

logger = logging.getLogger(__name__)

REQUEST_UNDERSTANDING_V1 = "request_understanding_v1"

REQUEST_UNDERSTANDING_OUTPUT_SCHEMA_NAME = "request_understanding_output_v1"

REQUEST_UNDERSTANDING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "in_scope": {"type": "boolean"},
        "sub_asks": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "implies_action_request": {"type": "boolean"},
        "decline_message": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": [
        "in_scope",
        "sub_asks",
        "constraints",
        "open_questions",
        "implies_action_request",
        "decline_message",
        "confidence",
    ],
    "additionalProperties": False,
}

_MAX_SCHEMA_REPAIR_ATTEMPTS = 2
# Same rationale as the classifier's/success-check's own timeout: a single,
# single-shot decision should never fall through to the LLM adapter's own
# much larger default timeout (the gap behind a real 8+ minute live hang).
_TIMEOUT_SECONDS = 30.0


def _request_understanding_contract() -> PromptContract:
    return PromptContract(
        name=REQUEST_UNDERSTANDING_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Request Understanding layer for the UniPilot Agent, a Technion "
            "academic advising assistant. Your one job: read the student's raw message "
            "(plus any recent conversation turns) and produce a structured breakdown for "
            "the Planner, or decide the request is out of scope.\n\n"
            "Resolve references to prior turns (e.g. 'what about that other one') using "
            "conversation_history so each sub_ask stands on its own without it. If the "
            "student asks about more than one thing in one message, list every distinct "
            "ask separately -- never merge them into one or silently drop one. You do not "
            "decompose the request into steps and you do not ask a clarifying question "
            "yourself -- both are the Planner's job; note genuine ambiguities in "
            "open_questions instead."
        ),
        instructions=[
            "Set in_scope=true whenever ANY part of the request is in-scope Technion "
            "academic-advising content (courses, requirements, degree planning, policies, "
            "what-if scenarios) -- even if the message also contains an unrelated, "
            "off-topic ask (e.g. 'what courses do I need, and also write me a poem'). In "
            "that mixed case, sub_asks must include only the in-scope part(s) -- silently "
            "drop the off-topic part rather than declining the whole message. Only set "
            "in_scope=false when NONE of the request is in-scope.",
            "An ambiguous, underspecified, or dangling reference (e.g. 'what about the "
            "other one') is NOT a reason to set in_scope=false. If it's plausibly an "
            "in-scope academic question, set in_scope=true, do your best with the "
            "sub_ask, and note the ambiguity in open_questions instead. Never use "
            "decline_message to ask the student to clarify something -- that is asking a "
            "clarifying question yourself, which this layer never does; clarification is "
            "only ever the Planner's job.",
            "When in_scope=true, sub_asks must list every distinct thing asked as its own "
            "self-contained string, and decline_message must be null.",
            "When in_scope=false, sub_asks/constraints/open_questions must be empty and "
            "decline_message must be a short, polite, direct explanation.",
            "constraints are boundary conditions that limit what a valid answer can look "
            "like (e.g. 'must graduate within one year', 'no summer courses') -- they are "
            "never just a rephrasing of a sub_ask. Example: sub_ask 'recommend courses "
            "for next semester' + constraint 'must graduate within one year' is correct; "
            "a constraint like 'courses must be for next semester' is WRONG because it "
            "only restates the sub_ask. If nothing genuinely constrains the answer beyond "
            "what the sub_ask already says, leave constraints empty.",
            "open_questions capture genuine ambiguity in what the student means or "
            "intends -- e.g. a dangling reference to something not established in this "
            "message or conversation_history, or a request whose interpretation genuinely "
            "varies depending on unstated intent. Do NOT use open_questions for ordinary "
            "facts that simply need to be looked up to answer the request (e.g. which "
            "track the student is in, which courses they've already completed) -- "
            "resolving those is normal retrieval work for a later step, not an ambiguity "
            "in the request itself. Leave empty whenever the request's meaning is clear, "
            "even if answering it will require looking up information.",
            "implies_action_request=true means the student is asking you to actually "
            "perform or record a state change on their behalf right now -- e.g. 'register "
            "me for X', 'add this to my plan', 'update my saved schedule', 'submit this'. "
            "Asking for information, a recommendation, or advice -- e.g. 'what courses do "
            "I need', 'can you recommend courses for next semester', 'what should I take' "
            "-- is NOT an action request even though it's phrased as a request for help: "
            "set implies_action_request=false for these. Only set it true when the "
            "request itself names a concrete state-changing operation.",
            "Confidence reflects how certain you are of BOTH the in_scope decision and the "
            "sub_asks/constraints breakdown. Reserve 0.9+ for genuinely unambiguous cases. "
            "A request that is academic-adjacent but asks for a non-advising service (e.g. "
            "drafting an email or document on the student's behalf) is a real judgment "
            "call on scope, not a certainty -- score confidence around 0.5-0.7 for these, "
            "never reflexively high just because the decision was easy to make.",
            "Never decompose the request into steps yourself.",
        ],
        allowed_context_fields=None,
        output_schema_name=REQUEST_UNDERSTANDING_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate scope beyond Technion academic advising.",
        ],
    )


def build_request_understanding_prompt_registry() -> PromptRegistry:
    """The two generic contracts plus this layer's own -- mirrors
    `roles.prompts.build_prompt_registry_with_roles()`'s pattern."""
    registry = build_default_prompt_registry()
    registry.register(_request_understanding_contract())
    return registry


def _render_user_goal(sub_asks: list[str]) -> str:
    """Deterministic rendering, never LLM output -- guarantees `user_goal`
    can never drift from `sub_asks` (§7.1's "one structured decision, one
    rendering" pattern, applied here to avoid asking the LLM for two
    independently-hallucinatable descriptions of the same intent).
    """
    if not sub_asks:
        return ""
    if len(sub_asks) == 1:
        return sub_asks[0]
    return "; ".join(sub_asks)


def _build_system_prompt(contract: PromptContract) -> str:
    """Renders the contract's `role_prompt` + `instructions` + `safety_rules`
    into the actual system prompt. `role_prompt` alone was previously all
    that reached the model -- `instructions`/`safety_rules` were defined on
    the contract but never rendered anywhere, so every field-semantics rule
    written there (what counts as `implies_action_request`, how `constraints`
    differs from a `sub_ask`, confidence calibration) was silently never
    seen by the LLM.
    """
    lines = [contract.role_prompt]
    if contract.instructions:
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.extend(f"- {item}" for item in contract.instructions)
    if contract.safety_rules:
        lines.append("")
        lines.append("SAFETY RULES:")
        lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: RequestUnderstandingReasoningBlockInput) -> str:
    payload = {
        "objective": block_input.objective,
        "original_user_message": block_input.original_user_message,
        "conversation_history": [turn.model_dump() for turn in block_input.conversation_history],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class RequestUnderstandingReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Always fails open: any raised error, or a
    result that never becomes schema-valid, or a schema-valid-but-hollow
    combination (`in_scope=true` with no `user_goal`, or `in_scope=false`
    with no `decline_message`) all resolve to the same fallback -- treat
    the raw message as in-scope and let the Planner see it.
    """

    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_request_understanding_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: RequestUnderstandingReasoningBlockInput, telemetry: RunTelemetry
    ) -> RequestUnderstandingReasoningBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or REQUEST_UNDERSTANDING_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        user_prompt = _build_user_prompt(block_input)

        # `LLMAdapterError` here is intentionally left uncaught -- it
        # propagates to `run()`'s outer "never raises" wrapper, which calls
        # `_failed_output` below. That keeps the fail-open fallback in one
        # place instead of duplicated across a local try/except here too.
        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=user_prompt,
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
                return self._fallback_output(block_input, extra_warning="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_output(normalized, block_input)

    def _to_output(
        self, normalized: dict[str, Any], block_input: RequestUnderstandingReasoningBlockInput
    ) -> RequestUnderstandingReasoningBlockOutput:
        in_scope = bool(normalized.get("in_scope", True))
        sub_asks = [str(item) for item in (normalized.get("sub_asks") or []) if str(item).strip()]
        constraints = [str(item) for item in (normalized.get("constraints") or []) if str(item).strip()]
        open_questions = [str(item) for item in (normalized.get("open_questions") or []) if str(item).strip()]
        implies_action_request = bool(normalized.get("implies_action_request", False))
        decline_message = normalized.get("decline_message")
        try:
            confidence = float(normalized.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        # Schema-valid but semantically hollow -- schema validation alone
        # can't express "sub_asks required when in_scope=true" (would need
        # a conditional if/then schema). Fail open rather than return a
        # usable-looking but empty result.
        if in_scope and not sub_asks:
            return self._fallback_output(block_input, extra_warning="in_scope_true_without_usable_sub_asks")
        if not in_scope and not (isinstance(decline_message, str) and decline_message.strip()):
            return self._fallback_output(block_input, extra_warning="in_scope_false_without_usable_decline_message")

        return RequestUnderstandingReasoningBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=confidence,
            in_scope=in_scope,
            user_goal=_render_user_goal(sub_asks) if in_scope else None,
            decline_message=decline_message if not in_scope else None,
            sub_asks=sub_asks if in_scope else [],
            constraints=constraints if in_scope else [],
            open_questions=open_questions if in_scope else [],
            implies_action_request=implies_action_request if in_scope else False,
        )

    def _fallback_output(
        self, block_input: RequestUnderstandingReasoningBlockInput, *, extra_warning: str | None = None
    ) -> RequestUnderstandingReasoningBlockOutput:
        """The one fail-open result every failure path resolves to: treat
        the raw message as the one sub_ask, in-scope, and let the Planner
        see it. This layer's own reasoning failing must never block the
        turn.
        """
        warnings = ["request_understanding_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        fallback_sub_asks = [block_input.original_user_message]
        return RequestUnderstandingReasoningBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            in_scope=True,
            user_goal=_render_user_goal(fallback_sub_asks),
            decline_message=None,
            sub_asks=fallback_sub_asks,
            constraints=[],
            open_questions=[],
            implies_action_request=False,
        )

    def _failed_output(
        self, block_input: BaseReasoningBlockInput, *, reason: str
    ) -> RequestUnderstandingReasoningBlockOutput:
        """Overridden: called by `run()`'s outer wrapper when `_run_internal`
        raises (e.g. `LLMAdapterError` propagating from `_invoke_llm`).
        A raised exception here must fail open too, not just return a bare
        `status="failed"`.
        """
        assert isinstance(block_input, RequestUnderstandingReasoningBlockInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def understand_request(
    *,
    original_user_message: str,
    conversation_history: list[ConversationTurn] | None = None,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> RequestUnderstandingReasoningBlockOutput:
    """Convenience wrapper -- constructs the block + its typed input and runs
    it, mirroring `planning.planner.build_next_plan_steps()`'s own pattern of
    a plain function wrapping a reasoning-block class.
    """
    block = RequestUnderstandingReasoningBlock(llm_adapter=llm_adapter)
    block_input = RequestUnderstandingReasoningBlockInput(
        block_id=block_id,
        agent_name="request_understanding",
        objective="Turn the raw user message into a clear goal statement for the Planner, or decide it's out of scope.",
        original_user_message=original_user_message,
        conversation_history=conversation_history or [],
        output_schema_name=REQUEST_UNDERSTANDING_OUTPUT_SCHEMA_NAME,
        output_schema=REQUEST_UNDERSTANDING_OUTPUT_SCHEMA,
        prompt_contract_name=REQUEST_UNDERSTANDING_V1,
        llm_call_parameters=LLMCallParameters(timeout=_TIMEOUT_SECONDS),
    )
    return await block.run(block_input)


__all__ = [
    "REQUEST_UNDERSTANDING_V1",
    "REQUEST_UNDERSTANDING_OUTPUT_SCHEMA_NAME",
    "REQUEST_UNDERSTANDING_OUTPUT_SCHEMA",
    "RequestUnderstandingReasoningBlock",
    "build_request_understanding_prompt_registry",
    "understand_request",
]
