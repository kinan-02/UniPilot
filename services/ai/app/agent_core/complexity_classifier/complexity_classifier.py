"""Complexity Classifier (Dynamic Reasoning Effort): lightweight
BaseReasoningBlock that classifies the cognitive complexity of a request
based on the Request Understanding output. Single-shot, zero tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters

logger = logging.getLogger(__name__)

COMPLEXITY_CLASSIFIER_V1 = "complexity_classifier_v1"
COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA_NAME = "complexity_classifier_output_v1"

COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cognitive_complexity": {
            "type": "string",
            "enum": ["low", "medium", "high", "max"],
        },
    },
    "required": ["cognitive_complexity"],
    "additionalProperties": False,
}

_MAX_SCHEMA_REPAIR_ATTEMPTS = 2
_TIMEOUT_SECONDS = 10.0

_VALID_TIERS = frozenset({"low", "medium", "high", "max"})
_DEFAULT_TIER = "medium"


class ComplexityClassifierInput(BaseReasoningBlockInput):
    sub_asks: list[str]
    constraints: list[str]
    open_questions: list[str]
    implies_action_request: bool
    confidence: float


class ComplexityClassifierOutput(BaseReasoningBlockOutput):
    cognitive_complexity: str = "medium"


def _complexity_classifier_contract() -> PromptContract:
    return PromptContract(
        name=COMPLEXITY_CLASSIFIER_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Complexity Classifier for the UniPilot Agent. Your one job: "
            "given the structured output of the Request Understanding layer, assess "
            "how much planning effort this request will require."
        ),
        instructions=[
            "You receive the Request Understanding output: sub_asks, constraints, "
            "open_questions, implies_action_request, and confidence. Based on these, "
            "classify the cognitive_complexity of the PLANNING task — not the question's "
            "surface difficulty, but how many reasoning steps, data source cross-references, "
            "and logical deductions the Planner will need to produce a correct plan.",
            "'low': The request asks for 1-2 straightforward facts that can be looked up "
            "directly. No cross-referencing between different data sources is needed to "
            "produce the answer. Typically 1 sub_ask with no constraints. "
            "Examples: 'what courses have I completed', 'what is the retake policy', "
            "'what is course X'.",
            "'medium': The request requires cross-referencing 2-3 data sources or "
            "evaluating a rule or prerequisite against the student's own data. Steps will "
            "have dependencies between them. Typically 1-2 sub_asks that require comparing "
            "or matching facts from different sources. "
            "Examples: 'am I eligible for course X', 'how am I progressing toward my "
            "requirements', 'what prerequisites am I missing'.",
            "'high': The request involves hypothetical reasoning ('what if I fail X'), "
            "simulation of cascading effects, or comprehensive audit across many "
            "requirements. The answer requires projecting consequences, evaluating many "
            "rules simultaneously, or reasoning about scenarios that haven't happened yet. "
            "Examples: 'if I fail course X, how does that affect Y', 'what courses should "
            "I take next semester to stay on track for graduation'.",
            "'max': The request demands comprehensive optimization or planning across the "
            "student's entire academic situation with multiple interacting constraints. "
            "Reserve this for the most complex possible requests that require global-scope "
            "reasoning across the student's full degree. "
            "Examples: 'build me a complete semester plan that satisfies all remaining "
            "requirements while keeping my course load balanced and my GPA above 80'.",
            "When in doubt between two adjacent tiers, choose the higher one — it is safer "
            "to over-allocate reasoning resources than to under-allocate and produce a "
            "lower-quality plan.",
        ],
        allowed_context_fields=None,
        output_schema_name=COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[],
    )


def build_complexity_classifier_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_complexity_classifier_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt]
    if contract.instructions:
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.extend(f"- {item}" for item in contract.instructions)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: ComplexityClassifierInput) -> str:
    payload = {
        "sub_asks": block_input.sub_asks,
        "constraints": block_input.constraints,
        "open_questions": block_input.open_questions,
        "implies_action_request": block_input.implies_action_request,
        "confidence": block_input.confidence,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class ComplexityClassifierReasoningBlock(BaseReasoningBlock):
    """Single-shot, zero tools. Falls back to 'medium' on any failure."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_complexity_classifier_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: ComplexityClassifierInput, telemetry: RunTelemetry
    ) -> ComplexityClassifierOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or COMPLEXITY_CLASSIFIER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        user_prompt = _build_user_prompt(block_input)

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
        self, normalized: dict[str, Any], block_input: ComplexityClassifierInput
    ) -> ComplexityClassifierOutput:
        tier = str(normalized.get("cognitive_complexity") or _DEFAULT_TIER)
        if tier not in _VALID_TIERS:
            logger.warning("complexity_classifier_invalid_tier_in_output tier=%s", tier)
            tier = _DEFAULT_TIER

        return ComplexityClassifierOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0,
            cognitive_complexity=tier,
        )

    def _fallback_output(
        self, block_input: ComplexityClassifierInput, *, extra_warning: str | None = None
    ) -> ComplexityClassifierOutput:
        warnings = ["complexity_classifier_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return ComplexityClassifierOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            cognitive_complexity=_DEFAULT_TIER,
        )

    def _failed_output(
        self, block_input: BaseReasoningBlockInput, *, reason: str
    ) -> ComplexityClassifierOutput:
        assert isinstance(block_input, ComplexityClassifierInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def classify_complexity(
    *,
    sub_asks: list[str],
    constraints: list[str],
    open_questions: list[str],
    implies_action_request: bool,
    confidence: float,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> str:
    """Classify cognitive complexity. Returns one of 'low', 'medium', 'high', 'max'.
    Falls back to 'medium' on any failure."""
    block = ComplexityClassifierReasoningBlock(llm_adapter=llm_adapter)
    block_input = ComplexityClassifierInput(
        block_id=block_id,
        agent_name="complexity_classifier",
        objective="Classify the cognitive complexity of the planning task.",
        sub_asks=sub_asks,
        constraints=constraints,
        open_questions=open_questions,
        implies_action_request=implies_action_request,
        confidence=confidence,
        output_schema_name=COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA_NAME,
        output_schema=COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA,
        prompt_contract_name=COMPLEXITY_CLASSIFIER_V1,
        llm_call_parameters=LLMCallParameters(
            thinking_enabled=False,
            reasoning_effort="low",
            timeout=_TIMEOUT_SECONDS,
            max_retries=1,
        ),
    )
    output = await block.run(block_input)
    tier = output.cognitive_complexity
    if tier not in _VALID_TIERS:
        logger.warning("complexity_classifier_invalid_tier tier=%s defaulting=%s", tier, _DEFAULT_TIER)
        return _DEFAULT_TIER
    return tier


__all__ = [
    "COMPLEXITY_CLASSIFIER_V1",
    "COMPLEXITY_CLASSIFIER_OUTPUT_SCHEMA_NAME",
    "ComplexityClassifierReasoningBlock",
    "classify_complexity",
]
