"""`CalculationValidationReasoningBlock` -- a purpose-built, alternate
dispatch target for the `calculation_validation` role
(docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 2).

Extends `BaseReasoningBlock` (the same pattern already used by
`RequestUnderstandingReasoningBlock` and `ComposeAnswerReasoningBlock`)
instead of routing through the generic multi-pass `ReasoningBlock` +
`tool_loop.py` machinery every other specialist role shares -- "compose a
correct expression tree" is a genuinely different shape of work than "fetch
something, iterate if ambiguous."

Control flow (see the plan doc for the full rationale):
    1. Draft   -- one LLM call produces an `ExpressionNode` tree.
    2. Validate -- `validate_expression_tree`, in-process, zero LLM cost.
    3. Repair  -- bounded (`_MAX_REPAIR_ATTEMPTS`) LLM calls if invalid,
                  each given `validate_expression_tree`'s own error list.
    4. Execute -- call `apply_deterministic_rule` exactly once, via the
                  normal `tool_registry` (this block is not a special case
                  for *permissions*, only for *control flow*).
    5. Return  -- the tool's own `{result, trace}` becomes this block's
                  `result`; certainty is always `official_record`.

`run_calculation_validation_subagent` is a drop-in alternate to
`subagents.run.run_subagent` -- same signature shape, same `SubagentResult`
return type -- so `task_handler.py`'s downstream handling needs zero changes
regardless of which path produced the result.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import Field, ValidationError

from app.agent_core.planning.state import CertaintyTag, StateEntry, ToolInvocationRecord
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter, LLMAdapterError
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.subagents.schemas import SubagentContextPackage, SubagentResult
from app.agent_core.tools.primitives.expression_tree import ExpressionNode, validate_expression_tree
from app.agent_core.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger(__name__)

CALCULATION_VALIDATION_DRAFT_V1 = "calculation_validation_draft_v1"
CALCULATION_VALIDATION_REPAIR_V1 = "calculation_validation_repair_v1"
CALCULATION_PLAUSIBILITY_V1 = "calculation_plausibility_v1"
_EXPRESSION_OUTPUT_SCHEMA_NAME = "calculation_validation_expression_v1"
_PLAUSIBILITY_OUTPUT_SCHEMA_NAME = "calculation_plausibility_v1"
_EXPRESSION_TREE_SCHEMA: dict[str, Any] = ExpressionNode.model_json_schema()
_MAX_REPAIR_ATTEMPTS = 2
# How many times an implausible result may be re-drafted (each re-draft feeds
# the plausibility critique back to the model) before we stop and return the
# computed number flagged as `partial`. One is enough to fix the common
# mistakes (a spurious filter, a hardcoded const) without unbounded spend.
_MAX_PLAUSIBILITY_REDRAFTS = 1
_TOOL_NAME = "apply_deterministic_rule"

_PLAUSIBILITY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plausible": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["plausible", "reason"],
    "additionalProperties": False,
}

_OPERATOR_TABLE = """
OPERATOR VOCABULARY (a leaf is either {"const": <literal>} or {"ref": "<facts key>"}):
- const is a LITERAL value you already know and are supplying yourself -- a number (3.5),
  a string (e.g. "Spring Semester 2025/2026", a semester/status/category label you're comparing
  against), or a boolean. Use const for any value that is NOT itself one of the keys in `facts`.
- ref is the exact KEY NAME of an entry already present in `facts` -- never a literal value, and
  never a value copied FROM inside a fact (e.g. if facts["current_semester"] holds the string
  "Spring Semester 2025/2026", the literal "Spring Semester 2025/2026" itself is a const, not a
  ref -- only "current_semester" is a valid ref).
- A comparison like "is X equal to a specific known label/threshold" is {"op": "compare", "left":
  {"ref": "X"}, "comparator": "==", "right": {"const": "the known label"}} -- the right side is
  almost always a const, not a ref, unless you are comparing two DIFFERENT facts to each other.
- sum:      {"op": "sum", "of": <node>, "field": "<name>", "filter": {<optional equality map>}}
- count:    {"op": "count", "of": <node>, "filter": {<optional equality map>}}
- average:  {"op": "average", "of": <node>, "field": "<name>", "filter": {<optional equality map>}}
- add / subtract / multiply / divide: {"op": "<name>", "left": <node>, "right": <node>}
- compare:  {"op": "compare", "left": <node>, "comparator": "<one of >=,>,<=,<,==,!=>", "right": <node>}
""".strip()


class _CalculationValidationBlockInput(BaseReasoningBlockInput):
    facts: dict[str, Any] = Field(default_factory=dict)
    tool_grant: list[str] = Field(default_factory=list)


class _CalculationValidationBlockOutput(BaseReasoningBlockOutput):
    expression_used: dict[str, Any] | None = None
    trace: list[str] = Field(default_factory=list)
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)


def _calculation_validation_draft_contract() -> PromptContract:
    return PromptContract(
        name=CALCULATION_VALIDATION_DRAFT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Calculation-Validation Agent's drafting pass. Given the objective and "
            "the already-retrieved facts, produce ONE expression tree that computes the answer, "
            "using only the small operator vocabulary below -- never open-ended arithmetic, "
            "never a formula in prose.\n\n"
            f"{_OPERATOR_TABLE}"
        ),
        instructions=[
            "Reference facts only by the exact keys given in `facts` -- never invent a `ref` "
            "that isn't present there.",
            "Prefer the smallest tree that answers the objective.",
            "Never assert a computed number directly -- only ever produce the expression tree; "
            "the tool executes it.",
            "Return only the JSON expression tree matching the required schema -- no markdown "
            "fences, no prose outside the JSON.",
        ],
        allowed_context_fields=None,
        output_schema_name=_EXPRESSION_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a `ref` or fact not present in the supplied facts.",
            "Never perform open-ended arithmetic outside of the given operator vocabulary.",
        ],
    )


def _calculation_validation_repair_contract() -> PromptContract:
    return PromptContract(
        name=CALCULATION_VALIDATION_REPAIR_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Calculation-Validation Agent's repair pass. The previous expression "
            "tree failed structural validation. You are given the previous tree and the exact "
            "list of validation errors (which node, what's wrong). Fix only the structural/"
            "reference errors listed; do not change what the expression computes. Return only "
            "the corrected JSON expression tree -- no markdown fences, no prose.\n\n"
            f"{_OPERATOR_TABLE}"
        ),
        instructions=[
            "Fix only the errors listed -- do not change the expression's intent.",
            "Never invent a `ref` not present in the given facts.",
            "Return only valid JSON matching the required schema.",
        ],
        allowed_context_fields=None,
        output_schema_name=_EXPRESSION_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a fact to satisfy the schema.",
        ],
    )


def _calculation_plausibility_contract() -> PromptContract:
    return PromptContract(
        name=CALCULATION_PLAUSIBILITY_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Calculation-Validation Agent's plausibility checker. A deterministic "
            "engine already computed a RESULT by evaluating an EXPRESSION over the available "
            "FACTS. The arithmetic is correct by construction -- your ONLY job is to judge whether "
            "the expression actually answers the OBJECTIVE, i.e. whether it operated on the RIGHT "
            "data in the RIGHT way. You do not recompute anything.\n\n"
            "Flag the result implausible (plausible=false) when the expression is a valid but "
            "WRONG way to answer the objective -- for example: it applies a `filter` that narrows a "
            "total to a single record when the objective asks for an aggregate over all of them; it "
            "aggregates the wrong field; it hardcodes a `const` for a quantity that should have been "
            "computed from a fact; or the numeric result is grossly inconsistent with the inputs "
            "(e.g. a 'total completed credits' far smaller than a single course's worth given many "
            "courses). Otherwise plausible=true."
        ),
        instructions=[
            "Judge intent-vs-expression, never the arithmetic -- assume the engine summed/subtracted correctly.",
            "In `reason`, name the concrete flaw and, when you can, the fix (e.g. 'drop the "
            "courseNumber filter -- the objective asks for the total across all completed courses'), "
            "so a re-draft has something specific to correct.",
            "When genuinely unsure, prefer plausible=true -- do not block a reasonable computation "
            "over a stylistic quibble.",
            "Return only valid JSON matching the required schema.",
        ],
        allowed_context_fields=None,
        output_schema_name=_PLAUSIBILITY_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_calculation_validation_draft_contract())
    registry.register(_calculation_validation_repair_contract())
    registry.register(_calculation_plausibility_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_draft_user_prompt(block_input: _CalculationValidationBlockInput) -> str:
    payload = {
        "objective": block_input.objective,
        "rendered_prompt": block_input.task_context.get("rendered_prompt"),
        "facts": block_input.facts,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _build_repair_user_prompt(*, previous_expression: dict[str, Any] | None, errors: list[str]) -> str:
    payload = {
        "instruction": "Fix only the structural/reference errors listed; do not change what the expression computes.",
        "previous_expression": previous_expression,
        "validation_errors": errors,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _build_plausibility_user_prompt(
    block_input: _CalculationValidationBlockInput, *, expression: dict[str, Any], result: dict[str, Any]
) -> str:
    payload = {
        "objective": block_input.objective,
        "rendered_prompt": block_input.task_context.get("rendered_prompt"),
        "facts": block_input.facts,
        "expression_evaluated": expression,
        "result": result,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _build_redraft_user_prompt(
    block_input: _CalculationValidationBlockInput,
    *,
    previous_expression: dict[str, Any] | None,
    critique: str,
) -> str:
    payload = {
        "instruction": (
            "The previous expression was structurally valid and evaluated successfully, but a "
            "plausibility review found it does NOT correctly answer the objective. Re-draft a "
            "corrected expression tree that fixes the flaw described in `plausibility_critique`. "
            "Reference facts only by the exact keys given in `facts`."
        ),
        "objective": block_input.objective,
        "facts": block_input.facts,
        "previous_expression": previous_expression,
        "plausibility_critique": critique,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _parse_and_validate_tree(
    candidate: dict[str, Any] | None, facts: dict[str, Any]
) -> tuple[ExpressionNode | None, list[str]]:
    if not isinstance(candidate, dict):
        return None, ["invalid_expression_shape: draft output is not a JSON object"]
    try:
        node = ExpressionNode.model_validate(candidate)
    except ValidationError as exc:
        return None, [f"invalid_expression_shape: {exc}"]

    errors = validate_expression_tree(node, facts=facts)
    if errors:
        return None, errors
    return node, []


class CalculationValidationReasoningBlock(BaseReasoningBlock):
    """Draft -> validate -> repair (bounded) -> execute-once -- see module
    docstring for the full control-flow rationale."""

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        prompt_registry: PromptRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or _build_prompt_registry(), **kwargs
        )
        self._tool_registry = tool_registry

    async def _run_internal(
        self, block_input: _CalculationValidationBlockInput, telemetry: RunTelemetry
    ) -> _CalculationValidationBlockOutput:
        node, errors = await self._draft_valid_expression(block_input, telemetry)
        if node is None:
            return self._calculation_failed_output(
                reason=f"expression_repair_exhausted: {'; '.join(errors[:5])}"
            )

        if _TOOL_NAME not in block_input.tool_grant:
            logger.warning("calculation_validation_tool_not_in_grant tool=%s", _TOOL_NAME)
            return self._calculation_failed_output(reason=f"{_TOOL_NAME}_not_in_tool_grant")
        try:
            descriptor = self._tool_registry.get(_TOOL_NAME)
        except ToolNotFoundError:
            logger.warning("calculation_validation_tool_not_registered tool=%s", _TOOL_NAME)
            return self._calculation_failed_output(reason=f"{_TOOL_NAME}_not_registered")

        # Draft -> evaluate -> plausibility-check loop. The deterministic engine
        # computes the arithmetic correctly, but a valid tree can still be the
        # WRONG computation for the objective (a spurious filter, a hardcoded
        # const). The targeted LLM plausibility check -- the ONE LLM check we keep
        # on a per-step result, precisely because semantic correctness of a
        # computed number is the one thing no schema can catch -- feeds its
        # critique back into a bounded re-draft. On exhaustion we still keep the
        # computed number, flagged so the wrapper marks the step partial.
        last_data: dict[str, Any] = {}
        last_record: ToolInvocationRecord | None = None
        plausibility_reason = ""
        for attempt in range(_MAX_PLAUSIBILITY_REDRAFTS + 1):
            envelope, record = await self._execute_expression(node, block_input, descriptor)
            last_record = record
            if envelope is None or not envelope.ok:
                reason = "tool_call_raised" if envelope is None else f"tool_call_failed: {envelope.error}"
                return self._calculation_failed_output(
                    reason=reason, tool_audit_trail=[record] if record else []
                )
            last_data = envelope.data or {}

            plausible, plausibility_reason = await self._check_result_plausibility(
                block_input,
                expression=node.model_dump(exclude_none=True),
                result=last_data,
                telemetry=telemetry,
            )
            if plausible:
                return self._completed_output(last_data, node=node, record=record)
            if attempt >= _MAX_PLAUSIBILITY_REDRAFTS:
                break

            redraft_node, _ = await self._draft_valid_expression(
                block_input,
                telemetry,
                critique=plausibility_reason,
                previous=node.model_dump(exclude_none=True),
            )
            if redraft_node is None:
                break  # could not produce a valid alternative -- keep the flagged result
            node = redraft_node

        # Budget spent (or the re-draft failed to validate): we DO have a number,
        # but it is flagged implausible -> the wrapper maps this to partial.
        return self._implausible_output(last_data, node=node, reason=plausibility_reason, record=last_record)

    async def _draft_valid_expression(
        self,
        block_input: _CalculationValidationBlockInput,
        telemetry: RunTelemetry,
        *,
        critique: str | None = None,
        previous: dict[str, Any] | None = None,
    ) -> tuple[ExpressionNode | None, list[str]]:
        """Draft (or, when `critique` is given, RE-draft against a plausibility
        critique) an expression tree, then repair it up to `_MAX_REPAIR_ATTEMPTS`
        times against `validate_expression_tree`'s structural errors. Returns a
        valid node, or `(None, errors)` if a valid tree could not be produced."""
        if critique is None:
            contract = self._resolve_prompt_contract(
                block_input.prompt_contract_name or CALCULATION_VALIDATION_DRAFT_V1
            )
            user_prompt = _build_draft_user_prompt(block_input)
            phase = "draft"
        else:
            contract = self._resolve_prompt_contract(CALCULATION_VALIDATION_DRAFT_V1)
            user_prompt = _build_redraft_user_prompt(block_input, previous_expression=previous, critique=critique)
            phase = "redraft"
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        draft_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=user_prompt,
            params=params,
            response_schema=_EXPRESSION_TREE_SCHEMA,
            phase=phase,
            block_input=block_input,
            telemetry=telemetry,
        )
        candidate = self._normalize_result(draft_result.parsed, output_schema=_EXPRESSION_TREE_SCHEMA)
        node, errors = _parse_and_validate_tree(candidate, block_input.facts)

        attempts = 0
        while node is None and attempts < _MAX_REPAIR_ATTEMPTS:
            attempts += 1
            repair_contract = self._resolve_prompt_contract(CALCULATION_VALIDATION_REPAIR_V1)
            repair_params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, repair_contract)
            repair_result = await self._invoke_llm(
                system_prompt=_build_system_prompt(repair_contract),
                user_prompt=_build_repair_user_prompt(previous_expression=candidate, errors=errors),
                params=repair_params,
                response_schema=_EXPRESSION_TREE_SCHEMA,
                phase=f"repair_attempt{attempts}",
                block_input=block_input,
                telemetry=telemetry,
            )
            candidate = self._normalize_result(repair_result.parsed, output_schema=_EXPRESSION_TREE_SCHEMA)
            node, errors = _parse_and_validate_tree(candidate, block_input.facts)
        return node, errors

    async def _execute_expression(
        self, node: ExpressionNode, block_input: _CalculationValidationBlockInput, descriptor: Any
    ) -> tuple[Any | None, ToolInvocationRecord | None]:
        """Evaluate a validated tree via `apply_deterministic_rule` once. Returns
        `(envelope, record)`; `(None, record)` when the tool call itself raised."""
        tool_arguments = {
            "rule": {"type": "expression", "expression": node.model_dump(exclude_none=True)},
            "facts": block_input.facts,
        }
        try:
            tool_input = descriptor.input_model(**tool_arguments)
            envelope = await descriptor.callable(tool_input)
        except Exception:  # noqa: BLE001 -- a tool bug must never crash the subagent
            logger.exception("calculation_validation_tool_call_raised", extra={"toolName": _TOOL_NAME})
            return None, ToolInvocationRecord(tool_name=_TOOL_NAME, arguments=tool_arguments, output_ok=False)
        record = ToolInvocationRecord(
            tool_name=_TOOL_NAME,
            arguments=tool_arguments,
            output_ok=envelope.ok,
            output_certainty=envelope.certainty,
        )
        logger.info("calculation_validation_tool_invoked ok=%s error=%s", envelope.ok, envelope.error)
        return envelope, record

    async def _check_result_plausibility(
        self,
        block_input: _CalculationValidationBlockInput,
        *,
        expression: dict[str, Any],
        result: dict[str, Any],
        telemetry: RunTelemetry,
    ) -> tuple[bool, str]:
        """Targeted LLM check: does `expression` correctly answer the objective,
        or is it a valid-but-wrong computation? Fails OPEN (plausible) on any
        checker error or malformed verdict -- a flaky checker must never discard
        a real computed result."""
        contract = self._resolve_prompt_contract(CALCULATION_PLAUSIBILITY_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        try:
            call_result = await self._invoke_llm(
                system_prompt=_build_system_prompt(contract),
                user_prompt=_build_plausibility_user_prompt(block_input, expression=expression, result=result),
                params=params,
                response_schema=_PLAUSIBILITY_OUTPUT_SCHEMA,
                phase="plausibility",
                block_input=block_input,
                telemetry=telemetry,
            )
        except LLMAdapterError:
            logger.warning("calculation_validation_plausibility_check_unavailable")
            return True, "plausibility_check_unavailable"

        normalized = self._normalize_result(call_result.parsed, output_schema=_PLAUSIBILITY_OUTPUT_SCHEMA)
        if not self._validate_schema(normalized, _PLAUSIBILITY_OUTPUT_SCHEMA).valid:
            return True, "plausibility_check_malformed"
        plausible = normalized.get("plausible")
        if not isinstance(plausible, bool):
            return True, "plausibility_check_malformed"
        return plausible, str(normalized.get("reason") or "")

    def _completed_output(
        self, data: dict[str, Any], *, node: ExpressionNode, record: ToolInvocationRecord | None
    ) -> _CalculationValidationBlockOutput:
        return _CalculationValidationBlockOutput(
            status="completed",
            schema_valid=True,
            result=data,
            confidence=1.0,
            expression_used=node.model_dump(exclude_none=True),
            trace=list(data.get("trace") or []),
            tool_audit_trail=[record] if record else [],
        )

    def _implausible_output(
        self, data: dict[str, Any], *, node: ExpressionNode, reason: str, record: ToolInvocationRecord | None
    ) -> _CalculationValidationBlockOutput:
        """A correctly-evaluated result the plausibility check still judged the
        WRONG computation after the re-draft budget was spent. Keep the number
        (`completed`, so it is not discarded) but flag it;
        `run_calculation_validation_subagent` maps the flag to a `partial` step
        so the orchestrator replans rather than reporting it as fact."""
        return _CalculationValidationBlockOutput(
            status="completed",
            schema_valid=True,
            result=data,
            confidence=0.3,
            warnings=[f"calculation_implausible: {reason}"],
            expression_used=node.model_dump(exclude_none=True),
            trace=list(data.get("trace") or []),
            tool_audit_trail=[record] if record else [],
        )

    def _calculation_failed_output(
        self, *, reason: str, tool_audit_trail: list[ToolInvocationRecord] | None = None
    ) -> _CalculationValidationBlockOutput:
        return _CalculationValidationBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"calculation_validation_failed: {reason}"],
            expression_used=None,
            trace=[],
            tool_audit_trail=tool_audit_trail or [],
        )

    def _failed_output(
        self, block_input: BaseReasoningBlockInput, *, reason: str
    ) -> _CalculationValidationBlockOutput:
        return self._calculation_failed_output(reason=f"reasoning_block_failed: {reason}")


def _unwrap_fact_envelope(value: Any) -> Any:
    """Retrieval facts arrive wrapped as `{key, value, source, confidence}`
    (the canonical retrieval-block shape -- see `orchestrator/state_index.py`).
    The expression evaluator does a single-hop `facts[ref]` lookup with no
    dotted-path traversal, so a list/number fact left inside its envelope
    resolves to the wrapper dict -- producing `of_not_a_list` (or a ref that
    can't be summed/counted) no matter how the expression is retried. Unwrap to
    the inner `.value` so `{"ref": "completedCourses"}` binds to the actual
    list. Only a genuine envelope (both `key` and `value` present) is unwrapped;
    any other dict fact is left untouched."""
    if isinstance(value, dict) and "key" in value and "value" in value:
        return value["value"]
    return value


_MAX_FACT_PROMOTION_DEPTH = 5


def _promote_inner_facts(data: Any, facts: dict[str, Any], *, depth: int = 0) -> None:
    """Promote a dependency's actual fetched values to the single-hop `facts`
    map (additive -- `setdefault` never overwrites an existing `step_id` key or
    an already-promoted fact), each unwrapped from its
    `{key, value, source, confidence}` envelope.

    A retrieval/interpretation dependency exposes its values under
    `data["facts"]`. A step routed to a multi-specialist pipeline instead
    aggregates its sub-steps one level deeper, under
    `data["sub_results"][<sub_step_id>]["facts"]` (with no top-level `facts`
    key), and a nested subplan can stack another pipeline inside that -- so we
    recurse through `sub_results` too. Without this, a pipeline-produced list
    (e.g. `completedCourses`) stays buried and a downstream expression's
    `{"ref": "completedCourses"}` can never bind, failing as `of_not_a_list`
    with `List-valued facts available: []` (observed live: ISE
    `credits_remaining`). Depth-bounded purely as a cycle-free safety cap."""
    if not isinstance(data, dict) or depth > _MAX_FACT_PROMOTION_DEPTH:
        return
    inner_facts = data.get("facts")
    if isinstance(inner_facts, dict):
        for key, value in inner_facts.items():
            facts.setdefault(key, _unwrap_fact_envelope(value))
    sub_results = data.get("sub_results")
    if isinstance(sub_results, dict):
        for sub in sub_results.values():
            _promote_inner_facts(sub, facts, depth=depth + 1)


def _flatten_dependency_facts(dependency_state: list[StateEntry]) -> dict[str, Any]:
    """Flatten a calc-validation step's dependencies into the single-hop `facts`
    map the expression evaluator binds `ref`s against.

    Each dependency is keyed by its `step_id`; its actual fetched values are
    promoted to the top level via `_promote_inner_facts` (which reaches through
    both a direct `data["facts"]` map and a routed pipeline's nested
    `data["sub_results"]`), so a fact fetched as `completedCourses` is directly
    ref-able as `{"ref": "completedCourses"}`."""
    facts: dict[str, Any] = {}
    for entry in dependency_state:
        facts[entry.step_id] = entry.data
        _promote_inner_facts(entry.data, facts)
    return facts


async def run_calculation_validation_subagent(
    *,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    llm_call_params: LLMCallParameters | None = None,
) -> SubagentResult:
    """Same signature/return type as `subagents.run.run_subagent` -- a
    drop-in alternate dispatch target, not a parallel result type."""
    # `dependency_state` entries are already successfully referenced this way
    # by the model today (its own tool-call arguments already say things
    # like "source: completed_courses record (user_id ...) + course entity
    # 00950120") -- flattening by step_id gives it a smaller, cleaner
    # surface to build expressions against than raw `dependency_state`.
    facts = _flatten_dependency_facts(context_package.dependency_state)

    block_input = _CalculationValidationBlockInput(
        block_id=block_id,
        agent_name="calculation_validation",
        objective=context_package.structured_fields.goal,
        task_context={
            "rendered_prompt": context_package.rendered_prompt,
            "structured_fields": context_package.structured_fields.model_dump(),
        },
        output_schema_name=_EXPRESSION_OUTPUT_SCHEMA_NAME,
        output_schema=_EXPRESSION_TREE_SCHEMA,
        facts=facts,
        tool_grant=list(context_package.tool_grant),
        **({"llm_call_parameters": llm_call_params} if llm_call_params else {}),
    )
    block = CalculationValidationReasoningBlock(llm_adapter=llm_adapter, tool_registry=tool_registry)
    output = await block.run(block_input)

    # A `completed` output that the plausibility check flagged carries a number
    # but should not be reported as fact -- surface it as `partial` so the
    # orchestrator replans, exactly as it would for any other unmet step.
    status: Literal["succeeded", "partial", "failed"]
    if output.status == "completed" and output.result is not None:
        implausible = any(str(w).startswith("calculation_implausible") for w in output.warnings)
        status = "partial" if implausible else "succeeded"
    else:
        status = "failed"

    return SubagentResult(
        status=status,
        result=output.result,
        certainty=CertaintyTag(basis="official_record", confidence=output.confidence),
        assumptions=[],
        warnings=list(output.warnings),
        tool_audit_trail=output.tool_audit_trail,
        needs_another_round=False,
    )


__all__ = [
    "CALCULATION_VALIDATION_DRAFT_V1",
    "CALCULATION_VALIDATION_REPAIR_V1",
    "CalculationValidationReasoningBlock",
    "run_calculation_validation_subagent",
]
