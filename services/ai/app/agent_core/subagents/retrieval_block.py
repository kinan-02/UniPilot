"""`RetrievalReasoningBlock` -- a purpose-built, alternate
dispatch target for the `retrieval` role
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

Extends `BaseReasoningBlock` to implement a bounded tool-observation loop
instead of two independent nested loops.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import Field

from app.agent_core.planning.state import CertaintyTag, ToolInvocationRecord
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter, LLMAdapterError
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.subagents.fact_projection import build_call_handles, project_facts
from app.agent_core.subagents.schemas import SubagentContextPackage, SubagentResult
from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry

logger = logging.getLogger(__name__)

_RETRIEVAL_ROUND_V1 = "retrieval_round_v1"
_RETRIEVAL_OUTPUT_SCHEMA_NAME = "retrieval_agent_output_v1"

_RETRIEVAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "certainty_basis": {
            "type": "string",
            "enum": [
                "official_record",
                "wiki_derived",
                "predicted_pattern",
                "llm_interpretation",
                "hypothetical_simulation",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_ref": {
            "type": ["object", "null"],
            "properties": {
                "page": {"type": "string"},
                "section": {"type": ["string", "null"]},
                "reasoning_path": {"type": ["string", "null"]},
            },
            "required": ["page"],
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "object"},
    },
    "required": ["certainty_basis", "confidence", "facts"],
}

# What the MODEL emits. `_RETRIEVAL_OUTPUT_SCHEMA` above stays exactly as it
# was -- it is the shape the rest of the pipeline consumes (`state_index`, the
# calculation block's `_unwrap_fact_envelope`) and the shape
# `_salvage_on_round_call_failure` hand-builds. Projection changes who AUTHORS a
# fact, never what downstream receives, so the two shapes are now distinct:
# selectors in, facts out.
#
# `facts` is an ARRAY here on purpose, and that is load-bearing beyond taste:
# `result_normalizer._recover_facts_list_and_missing_certainty` rewrites a list
# into an object only for a property the schema declares object-typed. Declaring
# selectors as an array is what keeps that recovery -- which keys by `key` and
# reads `value` -- from mangling a selector list that deliberately has no
# `value`.
#
# Deliberately NOT `additionalProperties: False`. A model that bolts a stray
# `"value": 63.5` onto a selector is harmless: `project_facts` reads only
# key/from/path, so the number is inert and never reaches state. Forbidding it
# in the schema would instead turn a harmless extra key into a hard validation
# error and a repair loop -- and out-of-schema keys were measured live at ~10
# per run. The guarantee lives in the resolver, not the schema.
_RETRIEVAL_SELECTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "from": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["key", "from", "path"],
            },
        },
        "source_ref": {
            "type": ["object", "null"],
            "properties": {
                "page": {"type": "string"},
                "section": {"type": ["string", "null"]},
                "reasoning_path": {"type": ["string", "null"]},
            },
            "required": ["page"],
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["facts"],
}

# Weakest-first. A step is only as certain as the least certain call it read --
# the same min-aggregation convention `compose_answer._aggregate_certainty` and
# `result_normalizer._flatten_fact_list_to_object` already use.
_BASIS_STRENGTH: tuple[str, ...] = (
    "official_record",
    "wiki_derived",
    "predicted_pattern",
    "llm_interpretation",
    "hypothetical_simulation",
)


def _weakest_basis(bases: list[str]) -> str:
    """The certainty a projected step actually earned, taken from the envelopes
    of the calls it read rather than from the model's say-so.

    Falls back to `llm_interpretation` only when no referenced envelope declared
    a basis at all -- which is the same conservative default
    `result_normalizer` applies, but reached only when nothing better is known
    rather than whenever the model happened to omit the field.
    """
    known = [basis for basis in bases if basis in _BASIS_STRENGTH]
    if not known:
        return "llm_interpretation"
    return max(known, key=_BASIS_STRENGTH.index)


_MAX_ROUNDS = 3

# Confidence stamped on a step that had to finalize on already-gathered tool
# results because a round's LLM call failed transiently (see
# `_salvage_on_round_call_failure`). Deliberately low: the facts are real but
# no final synthesis pass judged their sufficiency, so a downstream
# success-check should treat the step as partial, not fully trustworthy.
_DEGRADED_FINALIZE_CONFIDENCE = 0.3


def _retrieval_round_contract() -> PromptContract:
    return PromptContract(
        name=_RETRIEVAL_ROUND_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Retrieval Agent. You resolve and fetch facts using get_entity, "
            "search_knowledge, and traverse_relationship, plus higher-level tools that bundle "
            "several of those into one call. You may iterate if what you find is ambiguous. "
            "You do not carry data: you POINT AT it. Your result names, for each fact, which "
            "recorded call holds it and where inside that call it lives -- the value itself is "
            "read out of the recorded tool result for you. Never commentary or explanation prose."
        ),
        instructions=[
            "Each entry in `facts` is a SELECTOR, never a value: {\"key\": <short label you "
            "choose>, \"from\": <a call_N handle from tool_results>, \"path\": <dotted path into "
            "that call's recorded result, e.g. \"data.completedCourses\">}. There is no `value` "
            "field. You are not copying the data out; you are saying where it already is.",
            "Give each fact a short semantic label matching the tool's own field name (e.g. "
            "'currentSemester', 'courseCode') as its `key`. Never use a whole sentence as a key -- "
            "a downstream success-criteria check or calculation step matches on the label.",
            "A selector is a PATH -- it walks to a location and stops. It cannot sum, count, "
            "filter, compare, or combine. If the step needs a total, a tally, a subset, or a "
            "derived yes/no, you cannot produce it: select the RAW records it would be derived "
            "from and let the calculation step derive it. Handing over the raw list is the "
            "complete and correct answer to 'how many credits has the student earned' -- the "
            "arithmetic is not yours, and a total you worked out in your head is exactly the "
            "error this design exists to make impossible.",
            "Point at the deepest path that holds the whole answer, and no deeper. If a document "
            "already groups what you need (e.g. `data.academicPath`), select that one path rather "
            "than picking its fields apart.",
            "If a granted tool's own name/description already bundles the multi-step chain you'd "
            "otherwise assemble by hand (e.g. get_course_profile instead of get_entity followed by "
            "several traverse_relationship calls; get_track_requirements instead of get_entity "
            "followed by traverse_relationship; get_policy_answer instead of search_knowledge "
            "followed by an interpretation step), call that one tool instead -- it does the same "
            "work in one round instead of several.",
            "Courses are keyed by their numeric code (use it directly), but a track, program, or "
            "faculty is keyed by a catalog SLUG (e.g. 'track-electrical-engineering') that is NOT "
            "the same as a student's programSlug or a plain program name -- slug formats vary (some "
            "carry a 'track-' prefix, some do not; a bare programSlug can even resolve to a faculty, "
            "not the track). When a step needs a track/program/faculty entity and you have only a "
            "name or a profile's programSlug, resolve the exact slug with a SINGLE search_knowledge "
            "call first, then get_entity (or get_track_requirements) on the slug it returns. Never "
            "guess or transform a name/programSlug into an entity id and retry get_entity with "
            "variant after variant -- one search resolves it; retried guesses only burn rounds.",
            "If a search is ambiguous, request another tool call round rather than guessing.",
            "A record that was fetched successfully but has a field that is null/unset (e.g. a "
            "student profile with no declared program), or a list that came back empty (e.g. a "
            "semester plan with no enrolments), is a CONFIDENT, fully resolved fact -- 'this is "
            "genuinely absent' -- not an ambiguous or incomplete search. Select that path and "
            "finalize rather than spending another round re-fetching the same record or searching "
            "elsewhere for a value the source has already confirmed does not exist.",
            "Output must be either a tool request (status='need_tools', provide tool_requests) OR "
            "a final result (status='ready', provide result matching the required schema).",
        ],
        allowed_context_fields=None,
        output_schema_name=_RETRIEVAL_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=_MAX_ROUNDS,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            # Kept as a statement of intent, not as the enforcement. Asking a
            # model not to fabricate is what the old citation guard effectively
            # did, and it could only ever catch a model that confessed. A
            # selector has no value field, so this rule is now true by
            # construction rather than by compliance.
            "Never select a path for data a tool did not return; if the answer is not in a "
            "recorded result, request the tool that would fetch it.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_retrieval_round_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


class _RetrievalBlockInput(BaseReasoningBlockInput):
    tool_grant: list[str] = Field(default_factory=list)


class _RetrievalBlockOutput(BaseReasoningBlockOutput):
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)
    rounds_used: int = 0


class RetrievalReasoningBlock(BaseReasoningBlock):
    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        tool_call_cache: ToolCallCache | None = None,
        unresolvable_registry: UnresolvableEntityRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or _build_prompt_registry(), **kwargs
        )
        self._tool_registry = tool_registry
        self._tool_call_cache = tool_call_cache
        self._unresolvable_registry = unresolvable_registry

    async def _run_internal(
        self, block_input: _RetrievalBlockInput, telemetry: RunTelemetry
    ) -> _RetrievalBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or _RETRIEVAL_ROUND_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        system_prompt = _build_system_prompt(contract)

        round_num = 0
        tool_results_so_far: dict[str, dict] = {}
        tool_audit_trail: list[ToolInvocationRecord] = []

        # The schema for the intermediate round calls to decide between status ready/need_tools
        round_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ready", "need_tools"]},
                "tool_requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["tool_name", "arguments"],
                    },
                },
                "result": _RETRIEVAL_SELECTOR_SCHEMA,
            },
            "required": ["status"],
        }

        while round_num < _MAX_ROUNDS:
            round_num += 1
            is_final_round = round_num == _MAX_ROUNDS

            available_tools_with_schemas = []
            for t_name in block_input.tool_grant:
                try:
                    desc = self._tool_registry.get(t_name)
                    available_tools_with_schemas.append({
                        "name": desc.name,
                        "description": desc.description,
                        "input_schema": desc.input_model.model_json_schema(),
                    })
                except Exception:
                    available_tools_with_schemas.append({"name": t_name})

            # Handles are the reference space a selector's `from` names. The
            # underlying result key is `f"{tool_name}:{json.dumps(arguments)}"`
            # -- faithful, and far too fiddly to ask a model to echo back
            # exactly; making it reproduce one would reintroduce, in the
            # reference, the very transcription selectors exist to remove.
            handles = build_call_handles(tool_results_so_far)
            payload = {
                "objective": block_input.objective,
                "task_context": block_input.task_context,
                "tool_results": {
                    handle: tool_results_so_far[key] for handle, key in handles.items()
                },
                "available_tools": available_tools_with_schemas,
            }
            if is_final_round:
                payload["instruction"] = "NO MORE TOOL CALLS. You must finalize with what you have. Return status='ready' and populate the result."

            user_prompt = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            try:
                call_result = await self._invoke_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    params=params,
                    response_schema=round_schema,
                    phase=f"retrieval_round_{round_num}",
                    block_input=block_input,
                    telemetry=telemetry,
                )
            except LLMAdapterError as exc:
                salvaged = self._salvage_on_round_call_failure(
                    exc,
                    tool_results_so_far=tool_results_so_far,
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )
                if salvaged is not None:
                    return salvaged
                raise

            # Simple fallback normalization if the LLM output is malformed
            parsed = call_result.parsed or {}
            status = parsed.get("status")

            if status == "need_tools" and not is_final_round:
                requests = parsed.get("tool_requests") or []
                requests = await self._repair_tool_requests_if_needed(
                    parsed,
                    requests,
                    round_schema=round_schema,
                    block_input=block_input,
                    telemetry=telemetry,
                    tool_registry=self._tool_registry,
                )
                tool_results_so_far, new_records = await execute_tool_round(
                    tool_requests=requests,
                    tool_grant=block_input.tool_grant,
                    tool_registry=self._tool_registry,
                    tool_results_so_far=tool_results_so_far,
                    log_prefix="retrieval",
                    tool_call_cache=self._tool_call_cache,
                    unresolvable_registry=self._unresolvable_registry,
                )
                tool_audit_trail.extend(new_records)
                continue

            # status == "ready" OR is_final_round
            candidate_result = parsed.get("result")
            if candidate_result is None:
                return self._retrieval_failed_output(
                    reason="round_budget_exhausted_no_result" if is_final_round else "status_ready_but_no_result",
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )

            candidate = self._normalize_result(candidate_result, output_schema=_RETRIEVAL_SELECTOR_SCHEMA)
            validation = self._validate_schema(candidate, _RETRIEVAL_SELECTOR_SCHEMA)

            if not validation.valid:
                repair_outcome = await self._repair_schema(
                    initial_result=candidate,
                    initial_errors=validation.errors,
                    output_schema=_RETRIEVAL_SELECTOR_SCHEMA,
                    max_attempts=2,
                    block_input=block_input,
                    telemetry=telemetry,
                )
                if not repair_outcome.valid:
                    return self._retrieval_failed_output(
                        reason=f"schema_repair_exhausted: {'; '.join(repair_outcome.errors[:5])}",
                        tool_audit_trail=tool_audit_trail,
                        rounds_used=round_num,
                    )
                candidate = repair_outcome.result

            # Runs at this one point, AFTER any schema repair, so a repair pass
            # cannot re-introduce what it strips. The old second guard
            # (`_drop_ungrounded_facts`) is gone: it adjudicated a
            # model-authored `source` string, and projection means no such
            # string exists to adjudicate.
            candidate, out_of_contract = _drop_out_of_contract_keys(candidate, _RETRIEVAL_SELECTOR_SCHEMA)

            outcome = project_facts(candidate.get("facts"), tool_results_so_far, handles)

            # A step that resolved nothing produced nothing, and must not report
            # otherwise. CAUGHT LIVE (2026-07-16, `presupposition_conflict` step
            # 1a): every fact was thrown away and the step still returned
            # `succeeded` at confidence 0.9, so the Planner recorded a success,
            # never re-fetched, and the student's degree context vanished from
            # the turn without a single visible symptom. Failing sends it to the
            # Monitor, which replans with the whole plan in view -- the recovery
            # path this orchestrator is built around.
            if not outcome.facts:
                return self._retrieval_failed_output(
                    reason=f"no_facts_projected: {'; '.join(outcome.errors[:5]) or 'no selectors returned'}",
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )

            confidence = min(outcome.confidences) if outcome.confidences else 1.0
            projected = {
                "certainty_basis": _weakest_basis(outcome.bases),
                "confidence": confidence,
                "source_ref": candidate.get("source_ref"),
                "assumptions": candidate.get("assumptions") or [],
                "facts": outcome.facts,
            }

            # Defensive, exactly as the salvage path validates its own
            # hand-built result: this dict is assembled here, so a future change
            # to either schema can never silently start emitting a shape
            # downstream cannot read.
            projected_validation = self._validate_schema(projected, _RETRIEVAL_OUTPUT_SCHEMA)
            if not projected_validation.valid:
                logger.error(
                    "retrieval_projected_result_invalid errors=%s", projected_validation.errors[:5]
                )
                return self._retrieval_failed_output(
                    reason=f"projected_result_invalid: {'; '.join(projected_validation.errors[:3])}",
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )

            # Partial resolution is a real result plus a visible caveat -- some
            # selectors landed, so the step has facts, but the ones that missed
            # are surfaced rather than quietly absent.
            return _RetrievalBlockOutput(
                status="completed",
                schema_valid=True,
                result=projected,
                confidence=confidence,
                warnings=[f"retrieval_selector_unresolved: {error}" for error in outcome.errors]
                + [f"retrieval_dropped_out_of_contract_key: {key}" for key in out_of_contract],
                tool_audit_trail=tool_audit_trail,
                rounds_used=round_num,
            )

        # Should never reach here due to the `is_final_round` check, but just in case:
        return self._retrieval_failed_output(
            reason="round_budget_exhausted_unexpectedly",
            tool_audit_trail=tool_audit_trail,
            rounds_used=round_num,
        )

    def _salvage_on_round_call_failure(
        self,
        exc: LLMAdapterError,
        *,
        tool_results_so_far: dict[str, dict],
        tool_audit_trail: list[ToolInvocationRecord],
        rounds_used: int,
    ) -> _RetrievalBlockOutput | None:
        """Finalize on already-gathered tool results when a round's LLM call
        fails, instead of discarding the whole step.

        A round call that raises `LLMAdapterError` -- a transient transport
        blip surfaced as `llm_call_failed`, or a parse failure that already
        exhausted `_invoke_llm`'s own retry -- would otherwise propagate to
        `run()` and blow the step away as `internal_error`, throwing out every
        fact the earlier rounds already fetched and forcing an expensive
        Planner re-plan (a live-eval run reproduced exactly this: step 1a died
        with an empty audit trail on one transient blip).

        When at least one tool result was already gathered, those results ARE a
        usable, if incomplete, answer: package them as `facts` at a
        deliberately low confidence with an explicit degradation assumption, so
        a downstream success-check treats the step as partial rather than the
        turn losing the work entirely -- costing NO extra LLM call. With
        nothing gathered yet (the failure hit the very first round), there is
        nothing to salvage: return `None` so the caller re-raises and the step
        fails closed exactly as before.
        """
        if not tool_results_so_far:
            return None

        salvaged_result = {
            "certainty_basis": "wiki_derived",
            "confidence": _DEGRADED_FINALIZE_CONFIDENCE,
            "facts": dict(tool_results_so_far),
            "assumptions": [
                f"Retrieval degraded: the reasoning model was unreachable ({exc}) after "
                f"{rounds_used} round(s); finalized on the tool results already gathered "
                "without a final synthesis pass."
            ],
        }
        # The salvaged shape is hand-built to satisfy the output schema;
        # validate it defensively so a future schema change can never let a
        # malformed salvage escape as if it were a real result.
        if not self._validate_schema(salvaged_result, _RETRIEVAL_OUTPUT_SCHEMA).valid:
            return None

        logger.warning(
            "retrieval_round_call_failed_salvaged",
            extra={"error": str(exc), "rounds_used": rounds_used, "facts_count": len(tool_results_so_far)},
        )
        return _RetrievalBlockOutput(
            status="completed",
            schema_valid=True,
            result=salvaged_result,
            confidence=_DEGRADED_FINALIZE_CONFIDENCE,
            warnings=[f"retrieval_degraded_partial_finalize: {exc}"],
            tool_audit_trail=tool_audit_trail,
            rounds_used=rounds_used,
        )

    def _retrieval_failed_output(
        self, *, reason: str, tool_audit_trail: list[ToolInvocationRecord] | None = None, rounds_used: int = 0
    ) -> _RetrievalBlockOutput:
        return _RetrievalBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"retrieval_failed: {reason}"],
            tool_audit_trail=tool_audit_trail or [],
            rounds_used=rounds_used,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _RetrievalBlockOutput:
        return self._retrieval_failed_output(reason=f"reasoning_block_failed: {reason}")


def _drop_out_of_contract_keys(
    candidate: dict[str, Any], output_schema: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Project the result onto the keys the schema actually declares.

    Projection closed the front door: `facts` entries are selectors, so a
    fabricated number cannot be written into one. This closes the side door --
    a top-level key the schema never declared.

    CAUGHT LIVE (2026-07-16, ise_correctness). Retrieval returned the 17
    completed courses perfectly, then appended a key that appears nowhere in
    `_RETRIEVAL_OUTPUT_SCHEMA`:

        "metadata": {"total_courses": 17, "total_credits_earned": 63.5}

    No tool computed that total (`get_entity` returns the raw list and nothing
    else); the model summed the list in its head and got it wrong -- the real
    total is 62.5. `metadata` carries no `source`, so the groundedness guard had
    nothing to judge and never looked at it anyway; the schema declares no
    `additionalProperties: false`, so it validated cleanly; and it inherited the
    block's `certainty_basis: official_record` / `confidence: 1.0`. A guess wore
    an official record's badge all the way to the student, and that same run's
    plausibility checker then trusted it over the deterministic engine.

    Measured across that run, the model put SEVEN distinct undeclared keys on
    retrieval results (`metadata`, `status`, `notes`, `missing`, `warnings`,
    `certainty`, `source`) in 10 places. That volume is why this PROJECTS rather
    than validates: adding `additionalProperties: false` to the schema would fire
    `_repair_schema` on nearly every retrieval, buying loops and latency to fix a
    shape we are about to discard anyway. Dropping is decidable in code, costs no
    LLM call, and cannot loop.

    Verified before writing this: `run_retrieval_subagent` reads only
    `certainty_basis`, `confidence`, `source_ref`, `assumptions` and `facts`, and
    the block itself reads only `confidence` -- every one a declared key. Nothing
    downstream consumes an undeclared one, so nothing real is lost.

    The dropped key NAME is surfaced as a warning; the value never is. That is
    deliberate -- see `_implausible_output` in the calculation block, where
    letting a model's prose (carrying exactly this fabricated 63.5) reach the
    Planner turned a hallucination into an instruction.
    """
    allowed = set((output_schema.get("properties") or {}).keys())
    if not allowed:
        return candidate, []
    dropped = [key for key in candidate if key not in allowed]
    if not dropped:
        return candidate, []
    logger.warning("retrieval_dropped_out_of_contract_keys keys=%s declared=%s", dropped, sorted(allowed))
    return {key: value for key, value in candidate.items() if key in allowed}, dropped


async def run_retrieval_subagent(
    *,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    llm_call_params: LLMCallParameters | None = None,
) -> SubagentResult:
    block_input = _RetrievalBlockInput(
        block_id=block_id,
        agent_name="retrieval",
        objective=context_package.structured_fields.goal,
        task_context={
            "rendered_prompt": context_package.rendered_prompt,
            "structured_fields": context_package.structured_fields.model_dump(),
            "dependency_state": [entry.to_dependency_view() for entry in context_package.dependency_state],
        },
        output_schema_name=_RETRIEVAL_OUTPUT_SCHEMA_NAME,
        output_schema=_RETRIEVAL_OUTPUT_SCHEMA,
        tool_grant=list(context_package.tool_grant),
        **({"llm_call_parameters": llm_call_params} if llm_call_params else {}),
    )
    block = RetrievalReasoningBlock(llm_adapter=llm_adapter, tool_registry=tool_registry, tool_call_cache=tool_call_cache, unresolvable_registry=unresolvable_registry)
    output = await block.run(block_input)

    status: Literal["succeeded", "partial", "failed"] = (
        "succeeded" if output.status == "completed" and output.result is not None else "failed"
    )

    certainty = None
    assumptions = []
    if output.result is not None:
        basis = output.result.get("certainty_basis", "wiki_derived")
        confidence = output.result.get("confidence", 1.0)
        source_ref_dict = output.result.get("source_ref")
        
        # Pydantic validation handles this gracefully via CertaintyTag instantiation below.
        certainty = CertaintyTag(
            basis=basis,
            confidence=confidence,
            source_ref=source_ref_dict,
        )
        assumptions = output.result.get("assumptions", [])
    else:
        certainty = CertaintyTag(basis="wiki_derived", confidence=0.0)

    return SubagentResult(
        status=status,
        result=output.result,
        certainty=certainty,
        assumptions=assumptions,
        warnings=list(output.warnings),
        tool_audit_trail=output.tool_audit_trail,
        needs_another_round=False,
    )


__all__ = [
    "_RETRIEVAL_ROUND_V1",
    "_RETRIEVAL_OUTPUT_SCHEMA_NAME",
    "RetrievalReasoningBlock",
    "run_retrieval_subagent",
]
