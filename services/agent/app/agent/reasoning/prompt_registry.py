"""Registry of versioned prompt contracts used by `ReasoningBlock`.

A `PromptContract` centralizes the role/system prompt, instructions, safety
rules, and default execution parameters for one reasoning task type — so
prompts stay reviewable in one place instead of being inlined at call sites.
"""

from __future__ import annotations

from typing import get_args

from pydantic import BaseModel, Field

from app.agent.llm_prompts import (
    build_entity_extractor_system,
    build_intent_classifier_system,
    build_preference_extractor_system,
    build_retrieval_validator_system,
    build_shared_grounding_block,
)
from app.agent.reasoning.schemas import ReasoningRiskLevel
from app.agent.schemas import AgentIntent

GENERIC_REASONING_BLOCK_V1 = "generic_reasoning_block_v1"
SCHEMA_REPAIR_V1 = "schema_repair_v1"
INTENT_CLASSIFIER_V1 = "intent_classifier_v1"
PREFERENCE_EXTRACTOR_V1 = "preference_extractor_v1"
ENTITY_EXTRACTOR_V1 = "entity_extractor_v1"
ANSWER_VALIDATOR_V1 = "answer_validator_v1"
RESPONSE_COMPOSER_V1 = "response_composer_v1"
TASK_UNDERSTANDING_V1 = "task_understanding_v1"
PLANNER_AGENT_V1 = "planner_agent_v1"
PLANNER_REPAIR_V1 = "planner_repair_v1"
SPECIALIST_GRADUATION_PROGRESS_V1 = "specialist_graduation_progress_v1"
SPECIALIST_COURSE_CATALOG_V1 = "specialist_course_catalog_v1"
SPECIALIST_REQUIREMENT_EXPLANATION_V1 = "specialist_requirement_explanation_v1"
DYNAMIC_AGENT_V1 = "dynamic_agent_v1"
SYNTHESIS_COMPOSER_V1 = "synthesis_composer_v1"
FINAL_ANSWER_JUDGE_V1 = "final_answer_judge_v1"

# Phase 2 §"Prompt safety requirements" — every role-specific contract below
# includes these verbatim (in addition to whatever the generic contract adds).
_PHASE_2_SAFETY_RULES: list[str] = [
    "Think internally. Do not reveal chain-of-thought.",
    "Return only valid JSON matching the requested schema.",
    "Use only the supplied context.",
    "Do not invent academic requirements, catalog rules, prerequisites, course "
    "offerings, degree rules, transcript data, or completed courses.",
    "Do not claim that a write action was completed unless the deterministic "
    "system confirms it.",
    "If information is missing, uncertain, or unsupported, say so through the "
    "structured output.",
    "Preserve the user's language when producing user-facing text.",
]


class PromptContract(BaseModel):
    """Versioned, reviewable prompt definition for one reasoning task type."""

    name: str
    version: str
    role_prompt: str
    instructions: list[str] = Field(default_factory=list)
    allowed_context_fields: list[str] | None = None
    output_schema_name: str
    default_risk_level: ReasoningRiskLevel = "medium"
    default_min_iterations: int = 2
    default_max_iterations: int = 3
    default_temperature: float = 0.2
    safety_rules: list[str] = Field(default_factory=list)
    # Optional, per-pass system-prompt additions keyed by the exact labels
    # `reasoning_block._pass_label` produces ("understand" / "draft" / "final").
    # `None` (the default, left unset by every contract below) means every
    # pass reuses the identical system prompt — today's behavior, unchanged.
    # A contract that sets this can give its "draft" pass different
    # instructions than its "final" pass (e.g. an adversarial self-check)
    # without adding another LLM call — see `reasoning_block._build_system_prompt`.
    pass_role_instructions: dict[str, list[str]] | None = None


class PromptContractNotFoundError(KeyError):
    """Raised when `PromptRegistry.get` is called with an unknown contract name."""


class PromptRegistry:
    """In-memory registry mapping a prompt contract name to its `PromptContract`."""

    def __init__(self) -> None:
        self._contracts: dict[str, PromptContract] = {}

    def register(self, contract: PromptContract, *, overwrite: bool = False) -> None:
        if not overwrite and contract.name in self._contracts:
            raise ValueError(f"prompt_contract_already_registered: {contract.name}")
        self._contracts[contract.name] = contract

    def get(self, name: str) -> PromptContract:
        try:
            return self._contracts[name]
        except KeyError as exc:
            raise PromptContractNotFoundError(name) from exc

    def has(self, name: str) -> bool:
        return name in self._contracts

    def names(self) -> list[str]:
        return sorted(self._contracts)


def _generic_reasoning_block_contract() -> PromptContract:
    return PromptContract(
        name=GENERIC_REASONING_BLOCK_V1,
        version="1.0.0",
        role_prompt=(
            "You are an internal reasoning module for the UniPilot Agent, a Technion "
            "academic advising assistant. You think step by step internally, but you "
            "NEVER reveal your internal reasoning, chain-of-thought, or private notes. "
            "You respond only with the single JSON object requested for this pass — "
            "no markdown fences, no prose outside the JSON."
        ),
        instructions=[
            "Think internally; never reveal chain-of-thought or private reasoning text.",
            "Return only valid JSON matching the requested response shape for this pass.",
            "Use only the information supplied in task_context, available_tools, "
            "constraints, and success_criteria — never invent facts.",
            "Never invent or guess academic requirements, course numbers, prerequisites, "
            "credits, offerings, or graduation status that are not present in the context.",
            "Never claim that a write action (save, update, delete, submit) was completed "
            "— this module only reasons and drafts; it does not execute actions.",
            "If required information is missing from task_context, set status to "
            "'needs_more_context' and list the missing items instead of guessing.",
            "If completing the objective requires calling a tool that is not already "
            "reflected in task_context, set status to 'needs_more_context' or "
            "'needs_tool' and populate tool_requests instead of fabricating a result.",
            "On the final pass, respect the required output_schema exactly when "
            "populating the 'result' field.",
        ],
        allowed_context_fields=None,
        output_schema_name="reasoning_pass_payload_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.2,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate academic data not present in the supplied context.",
            "Do not assert that any write/mutation has happened.",
        ],
    )


def _schema_repair_contract() -> PromptContract:
    return PromptContract(
        name=SCHEMA_REPAIR_V1,
        version="1.0.0",
        role_prompt=(
            "You are a strict JSON structure repair assistant. The previous output "
            "failed schema validation. Fix only the structure so it matches the "
            "required JSON schema exactly. Do not add new facts. Do not change the "
            "meaning of the content. Return only valid JSON matching the schema — no "
            "markdown fences, no prose."
        ),
        instructions=[
            "Fix only the structure/shape of the previous output.",
            "Do not add new facts or invent values that were not already present.",
            "Do not change the meaning of any field's content.",
            "Return only valid JSON matching the required schema.",
        ],
        allowed_context_fields=None,
        output_schema_name="caller_defined",
        default_risk_level="medium",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate data to satisfy the schema.",
        ],
    )


def _intent_classifier_contract() -> PromptContract:
    valid_intents = sorted(get_args(AgentIntent))
    return PromptContract(
        name=INTENT_CLASSIFIER_V1,
        version="1.0.0",
        role_prompt=build_intent_classifier_system(valid_intents=valid_intents),
        instructions=list(_PHASE_2_SAFETY_RULES),
        allowed_context_fields=["student_message", "rules_guess", "valid_intents"],
        output_schema_name="intent_classifier_output_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.0,
        safety_rules=[
            "Pick exactly one intent from the allowed list already described in the role prompt.",
            "Never invent an intent value outside the allowed list.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _preference_extractor_contract() -> PromptContract:
    return PromptContract(
        name=PREFERENCE_EXTRACTOR_V1,
        version="1.0.0",
        role_prompt=build_preference_extractor_system(),
        instructions=list(_PHASE_2_SAFETY_RULES),
        allowed_context_fields=["student_message", "already_detected_entities"],
        output_schema_name="preference_extractor_output_v1",
        default_risk_level="low",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.0,
        safety_rules=[
            "Never invent a course number, semester code, or preference not stated or "
            "clearly implied by the student message.",
            "Do not overwrite fields already present in already_detected_entities.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _entity_extractor_contract() -> PromptContract:
    return PromptContract(
        name=ENTITY_EXTRACTOR_V1,
        version="1.0.0",
        role_prompt=build_entity_extractor_system(),
        instructions=list(_PHASE_2_SAFETY_RULES),
        allowed_context_fields=["student_message", "already_detected_entities"],
        output_schema_name="entity_extractor_output_v1",
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Never invent a course number, track, or program that isn't stated or "
            "clearly implied by the student message.",
            "Populate at most one field — the single entity the message is about.",
            "Do not overwrite fields already present in already_detected_entities.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _answer_validator_contract() -> PromptContract:
    return PromptContract(
        name=ANSWER_VALIDATOR_V1,
        version="1.0.0",
        role_prompt=build_retrieval_validator_system(),
        instructions=list(_PHASE_2_SAFETY_RULES),
        allowed_context_fields=["student_question", "retrieval_summary"],
        output_schema_name="answer_validator_output_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.0,
        safety_rules=[
            "Prefer marking retrieval insufficient over guessing when key data is missing.",
            "gaps must name concrete missing data, not vague statements.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _response_composer_contract() -> PromptContract:
    return PromptContract(
        name=RESPONSE_COMPOSER_V1,
        version="1.0.0",
        role_prompt=(
            "You are UniPilot Agent — the student-facing academic advisor for the "
            "Technion. You polish and explain deterministic backend results into a "
            "clear, student-friendly reply. You do NOT recalculate requirements, "
            "eligibility, plans, or any numeric/status value — those are already "
            "final and authoritative.\n\n" + build_shared_grounding_block()
        ),
        instructions=[
            *_PHASE_2_SAFETY_RULES,
            "Only rewrite/improve the explanation text. Never change structured "
            "blocks, proposed actions, source lists, numeric credit values, "
            "requirement statuses, prerequisite statuses, offering statuses, "
            "transcript rows, saved plan IDs, or action IDs — those are supplied "
            "for context only and remain deterministic.",
            "Open with a direct answer to the student's question, then supporting "
            "detail drawn only from the supplied baseline answer and context.",
            "Do not repeat raw JSON or internal field names in the reply text.",
        ],
        allowed_context_fields=[
            "workflow_intent",
            "baseline_answer",
            "structured_blocks_summary",
            "profile_summary",
            "warnings",
            "assumptions",
            "used_sources",
            "validation_status",
            "wiki_context",
            "style_guidance",
            "language_instruction",
        ],
        output_schema_name="response_composer_output_v1",
        default_risk_level="low",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.15,
        safety_rules=[
            "The deterministic payload (blocks, actions, sources, numbers, statuses) "
            "remains authoritative; only the explanation text may be rewritten.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _task_understanding_contract() -> PromptContract:
    valid_intents = sorted(get_args(AgentIntent))
    role_prompt = (
        "You are the UniPilot Task Understanding Agent.\n\n"
        "Your job is to deeply understand the user's academic task before "
        "planning or workflow execution.\n\n" + build_shared_grounding_block()
    )
    return PromptContract(
        name=TASK_UNDERSTANDING_V1,
        version="1.0.0",
        role_prompt=role_prompt,
        instructions=[
            "You must: identify the user's actual goal.",
            "You must: normalize the request.",
            "You must: classify primary and secondary intents using only "
            f"supported intent values ({', '.join(valid_intents)}).",
            "You must: extract task-relevant entities.",
            "You must: identify missing context.",
            "You must: identify assumptions.",
            "You must: estimate task complexity.",
            "You must: recommend an autonomy level.",
            "You must: identify whether clarification is needed.",
            "You must: identify whether the user is asking for a write or update.",
            "You must: preserve the user's language.",
            "You must: return only valid JSON matching the schema.",
            "You must not: invent academic requirements.",
            "You must not: invent course facts.",
            "You must not: invent transcript data.",
            "You must not: invent completed courses.",
            "You must not: claim that a write action has happened.",
            "You must not: choose unsupported intent values.",
            "You must not: run tools.",
            "You must not: answer the user directly.",
            "You must not: expose chain-of-thought.",
            "Think internally. Do not reveal chain-of-thought.",
            "Return only valid JSON.",
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=[
            "user_message",
            "conversation_summary",
            "recent_messages",
            "existing_entities",
            "existing_assumptions",
            "deterministic_intent",
            "deterministic_intent_confidence",
            "deterministic_entities",
            "user_profile_summary",
            "attachment_metadata",
            "supported_intents",
            "supported_workflows",
            "locale_hint",
        ],
        output_schema_name="task_understanding_output_v1",
        default_risk_level="medium",
        default_min_iterations=3,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "This agent only understands the task; it does not solve it, run "
            "tools, or produce a final user-facing answer.",
            "If the task is unclear or context is missing, prefer "
            "'needs_more_context' / clarifying_questions over guessing.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _planner_agent_contract() -> PromptContract:
    role_prompt = (
        "You are the UniPilot Planner Agent.\n\n"
        "Your job is to convert a validated task understanding into an "
        "optimized, capability-aware execution plan.\n\n" + build_shared_grounding_block()
    )
    return PromptContract(
        name=PLANNER_AGENT_V1,
        version="1.0.0",
        role_prompt=role_prompt,
        instructions=[
            "You must: use only capabilities listed in the supplied CapabilityRegistry summary.",
            "You must: divide the task into small, meaningful subtasks.",
            "You must: assign each subtask to exactly one capability.",
            "You must: define dependencies between subtasks.",
            "You must: define required context sections for each subtask.",
            "You must: define success criteria for each subtask.",
            "You must: define validation requirements.",
            "You must: identify whether user confirmation is needed.",
            "You must: preserve deterministic academic services as the source of truth.",
            "You must: prefer existing deterministic workflows when they already solve the task.",
            "You must: avoid unnecessary agents/tools.",
            "You must: return only valid JSON matching the planner schema.",
            "You must not: invent capabilities.",
            "You must not: invent tools.",
            "You must not: invent academic requirements.",
            "You must not: invent course facts.",
            "You must not: invent transcript data.",
            "You must not: invent completed courses.",
            "You must not: claim any write has happened.",
            "You must not: answer the user directly.",
            "You must not: execute tools.",
            "You must not: execute workflows.",
            "You must not: create action proposals.",
            "You must not: expose chain-of-thought.",
            "You may optionally attach dynamic_agent_spec to a read-only analyze/validate subtask "
            "when the subtask is diagnostic, shadow-only, and can be handled by the fixed block library.",
            "You must: set dynamic_agent_spec.shadow_only=true for every proposed spec.",
            "You must: use only allowed reasoning patterns: single_pass, tool_observation_loop, compare_and_synthesize.",
            "You must: use only observations from the approved observation registry.",
            "You must not: propose dynamic_agent_spec for write/save/import/confirm tasks.",
            "You must not: propose dynamic_agent_spec that creates action proposals.",
            "You must not: generate code, scripts, or executable logic in any field.",
            "You must not: propose dynamic_agent_spec for transcript import writes, semester plan saves, "
            "profile updates, or action confirmation/rejection flows.",
            "Think internally. Do not reveal chain-of-thought.",
            "Return only valid JSON.",
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=[
            "user_message",
            "task_understanding",
            "deterministic_intent",
            "deterministic_entities",
            "conversation_entities",
            "conversation_assumptions",
            "capability_registry_summary",
            "legacy_workflow_plan",
            "profile_summary",
        ],
        output_schema_name="planner_output_v1",
        default_risk_level="high",
        default_min_iterations=3,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "This agent only plans; it never executes a subtask, tool, or workflow.",
            "Deterministic academic services remain the source of truth for facts and eligibility.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _planner_repair_contract() -> PromptContract:
    role_prompt = (
        "You are the UniPilot Planner in warm repair mode.\n\n"
        "You are given a prior plan snapshot, a compact delta describing what "
        "changed, monitor decision metadata, confirmed clarification answers, "
        "and current constraints.\n\n" + build_shared_grounding_block()
    )
    return PromptContract(
        name=PLANNER_REPAIR_V1,
        version="1.0.0",
        role_prompt=role_prompt,
        instructions=[
            "Decide repair vs regeneration.",
            "Preserve still-valid subtasks when possible.",
            "Revise only invalidated parts when repair is enough.",
            "Regenerate only when the user goal changed or the old plan is no longer valid.",
            "Return structured JSON only.",
            "You must not: invent academic requirements.",
            "You must not: invent transcript data.",
            "You must not: invent course catalog facts.",
            "You must not: perform writes.",
            "You must not: create proposed actions.",
            "You must not: expose chain-of-thought.",
            "You must not: output raw context.",
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=[
            "prior_plan_snapshot",
            "execution_deltas",
            "monitor_decision",
            "confirmed_clarifications",
            "requested_mode_hint",
            "dry_run",
        ],
        output_schema_name="planner_repair_output_v1",
        default_risk_level="high",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "Warm repair is diagnostic unless explicitly promoted in a later phase.",
            "Deterministic academic services remain the source of truth.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


# ---------------------------------------------------------------------------
# Phase 10 — read-only specialist agents. All three share the exact same
# "must"/"must not" instruction set (verbatim per the Phase 10 spec) and
# allowed context fields (matching `specialists.base.build_task_context`'s
# shape exactly) — only the role line, output schema name, and risk level
# differ per agent.
# ---------------------------------------------------------------------------

_SPECIALIST_MUST_INSTRUCTIONS: list[str] = [
    "You must: solve only the assigned subtask.",
    "You must: use only the supplied compiled context and deterministic observations.",
    "You must: preserve deterministic academic services as source of truth.",
    "You must: identify missing context.",
    "You must: surface uncertainty.",
    "You must: produce structured JSON only.",
    "You must: include warnings when information is incomplete.",
    "You must not: invent academic rules, catalog facts, prerequisites, offerings, "
    "completed courses, transcript rows, or degree requirements.",
    "You must not: claim that a write happened.",
    "You must not: create action proposals.",
    "You must not: answer outside your assigned scope.",
    "You must not: invent capabilities.",
    "You must not: call unavailable tools.",
    "You must not: perform writes.",
    "You must not: create proposed actions.",
    "You must not: expose chain-of-thought.",
    "You must not: return unstructured prose.",
    "Think internally. Do not reveal chain-of-thought.",
    "Return only valid JSON matching the specialist output schema.",
    # Phase 12 — Specialist Tool Observation Layer (still shadow-only): the
    # observation-gathering itself never calls an LLM, so these are purely
    # instructions for how the specialist must treat any observations it is
    # handed, not a description of new specialist behavior.
    "You may use deterministic_observations as trusted read-only observations.",
    "If an observation conflicts with the compiled context, prefer the deterministic "
    "observation and surface the conflict in warnings.",
    "Do not invent observations.",
    "Do not request unavailable tools.",
    # Phase 13 — Bounded Specialist Tool-Request Loop (still shadow-only): the
    # only "tool" a specialist may ever request is one more Phase 12
    # observation from the fixed, per-specialist observation registry — never
    # an arbitrary tool, function call, write, or proposed action.
    "You may request additional read-only observations only by returning "
    "status=\"needs_tool\" with tool_requests.",
    "Allowed tool_requests are observation requests only.",
    "Each tool request's tool_name must be the exact observation name you need, and "
    "purpose must explain why it is needed.",
    "Do not request arbitrary tools.",
    "Do not request writes.",
    "Do not request proposed actions.",
    "Do not request raw catalog dumps, raw transcript rows, raw PDFs, raw context, or full blocks.",
    "If the needed observation is not available, return missing_context or a warning instead of guessing.",
    "After observations are supplied, produce final structured output on the next pass.",
]

# Phase 14 — Controlled Specialist Text Promotion: only `graduation_progress_agent`
# is instructed to (optionally) populate `result.answer_text` — the other two
# specialist contracts are unchanged. Appended only to that one contract's
# instructions, never to `_SPECIALIST_MUST_INSTRUCTIONS` (shared by all three).
_GRADUATION_PROGRESS_ANSWER_TEXT_INSTRUCTIONS: list[str] = [
    "When you can safely do so, include a short, final natural-language answer "
    "in result.answer_text.",
    "answer_text must be based only on supplied compiled context, deterministic "
    "observations, and approved tool-loop observations.",
    "Do not invent academic rules, degree requirements, completed courses, course "
    "facts, or transcript data in answer_text.",
    "Do not claim in answer_text that any write/save/import happened.",
    "Do not include proposed actions in answer_text.",
]

_SPECIALIST_ALLOWED_CONTEXT_FIELDS: list[str] = [
    "objective",
    "user_message",
    "compiled_context",
    "dependency_outputs",
    "deterministic_observations",
    "success_criteria",
    "validation_requirements",
]


def _specialist_role_prompt(role_line: str) -> str:
    return (
        f"{role_line}\n\n"
        "You are a UniPilot specialist academic agent.\n\n" + build_shared_grounding_block()
    )


def _specialist_graduation_progress_contract() -> PromptContract:
    return PromptContract(
        name=SPECIALIST_GRADUATION_PROGRESS_V1,
        version="1.0.0",
        role_prompt=_specialist_role_prompt("You are the UniPilot Graduation Progress Specialist Agent."),
        instructions=[
            *_SPECIALIST_MUST_INSTRUCTIONS,
            *_GRADUATION_PROGRESS_ANSWER_TEXT_INSTRUCTIONS,
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=list(_SPECIALIST_ALLOWED_CONTEXT_FIELDS),
        output_schema_name="specialist_graduation_progress_output_v1",
        default_risk_level="high",
        default_min_iterations=3,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "This agent only reasons about graduation progress already computed "
            "deterministically; it never recalculates credits, requirement status, "
            "or graduation eligibility itself.",
            "Deterministic academic services remain the source of truth for facts and eligibility.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _specialist_course_catalog_contract() -> PromptContract:
    return PromptContract(
        name=SPECIALIST_COURSE_CATALOG_V1,
        version="1.0.0",
        role_prompt=_specialist_role_prompt("You are the UniPilot Course Catalog Specialist Agent."),
        instructions=[*_SPECIALIST_MUST_INSTRUCTIONS, *_PHASE_2_SAFETY_RULES],
        allowed_context_fields=list(_SPECIALIST_ALLOWED_CONTEXT_FIELDS),
        output_schema_name="specialist_course_catalog_output_v1",
        default_risk_level="medium",
        default_min_iterations=3,
        default_max_iterations=3,
        default_temperature=0.15,
        safety_rules=[
            "This agent only reasons about course/catalog/offering data already "
            "present in compiled_context; it never invents a course, prerequisite, "
            "or offering.",
            "Deterministic academic services remain the source of truth for catalog facts.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _specialist_requirement_explanation_contract() -> PromptContract:
    return PromptContract(
        name=SPECIALIST_REQUIREMENT_EXPLANATION_V1,
        version="1.0.0",
        role_prompt=_specialist_role_prompt("You are the UniPilot Requirement Explanation Specialist Agent."),
        instructions=[*_SPECIALIST_MUST_INSTRUCTIONS, *_PHASE_2_SAFETY_RULES],
        allowed_context_fields=list(_SPECIALIST_ALLOWED_CONTEXT_FIELDS),
        output_schema_name="specialist_requirement_explanation_output_v1",
        default_risk_level="medium",
        default_min_iterations=3,
        default_max_iterations=3,
        default_temperature=0.15,
        safety_rules=[
            "This agent only explains a degree requirement bucket using data already "
            "present in compiled_context; it never invents a requirement or rule.",
            "Deterministic academic services remain the source of truth for degree requirements.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


_DYNAMIC_AGENT_ALLOWED_CONTEXT_FIELDS: list[str] = [
    "spec_id",
    "agent_name",
    "role",
    "objective",
    "task_brief",
    "compiled_context",
    "deterministic_observations",
    "dependency_outputs",
    "allowed_observations",
    "allowed_capabilities",
    "boundaries",
    "success_criteria",
    "assumptions",
]


def _dynamic_agent_contract() -> PromptContract:
    return PromptContract(
        name=DYNAMIC_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            "You are a dynamically constructed UniPilot sub-agent.\n\n"
            + build_shared_grounding_block()
        ),
        instructions=[
            "You must solve only the assigned TaskBrief objective.",
            "Use only the supplied task brief, compiled context, deterministic observations, "
            "dependency outputs, allowed observations/tools, and allowed blocks.",
            "You must not invent academic rules, course facts, transcript rows, or degree requirements.",
            "You must not perform writes or create proposed actions.",
            "You must not claim any write/save/import/update happened.",
            "You must not expose chain-of-thought or request arbitrary tools.",
            "You must not exceed your assigned scope.",
            "Return only valid JSON matching the dynamic agent output schema.",
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=list(_DYNAMIC_AGENT_ALLOWED_CONTEXT_FIELDS),
        output_schema_name="dynamic_agent_output_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.15,
        safety_rules=[
            "Dynamic agents are configuration, not code generation — never invent capabilities.",
            "Deterministic academic services remain the source of truth for facts and eligibility.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _synthesis_composer_contract() -> PromptContract:
    role_prompt = (
        "You are the UniPilot Synthesis / Final Answer Composer.\n\n"
        "You are given compact evidence from deterministic workflows, specialists, "
        "dynamic agents, monitor, clarification, and plan repair.\n\n"
        + build_shared_grounding_block()
    )
    return PromptContract(
        name=SYNTHESIS_COMPOSER_V1,
        version="1.0.0",
        role_prompt=role_prompt,
        instructions=[
            "Reconcile the evidence.",
            "Prefer authoritative deterministic academic facts.",
            "Preserve confirmed user preferences.",
            "Surface uncertainty.",
            "Avoid unsupported claims.",
            "Produce a concise candidate answer.",
            "You must not: invent degree requirements.",
            "You must not: invent catalog facts.",
            "You must not: invent transcript data.",
            "You must not: invent completed courses.",
            "You must not: claim writes/saves/imports happened.",
            "You must not: create proposed actions.",
            "You must not: expose chain-of-thought.",
            "You must not: output raw context.",
            "You must not: output raw diagnostics.",
            "You must not: output raw blocks.",
            "Return valid JSON only.",
            *_PHASE_2_SAFETY_RULES,
        ],
        allowed_context_fields=[
            "userGoal",
            "normalizedRequest",
            "workflowSummary",
            "evidenceItems",
            "monitorSummary",
            "clarificationSummary",
            "planRepairSummary",
            "dryRun",
        ],
        output_schema_name="synthesis_output_v1",
        default_risk_level="high",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "Synthesis is diagnostic-only in Phase 21 — safe_to_promote must remain false.",
            "Deterministic academic services remain the source of truth.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def _final_answer_judge_contract() -> PromptContract:
    return PromptContract(
        name=FINAL_ANSWER_JUDGE_V1,
        version="1.0.0",
        role_prompt=(
            "You are an evaluation judge for UniPilot academic advisor answers. "
            "Compare the agent final answer against the supplied key facts from the "
            "wiki ground truth. Classify each fact as present, partial, missing, or "
            "contradicted. Provide short evidence excerpts only."
        ),
        instructions=[
            *_PHASE_2_SAFETY_RULES,
            "Judge only the final answer text; do not invent missing facts.",
            "Mark contradicted when the answer states a conflicting grade, credit total, "
            "course code, track count, or OR/AND regulatory logic.",
            "Return valid JSON only.",
        ],
        allowed_context_fields=[
            "userRequest",
            "correctSummary",
            "keyFacts",
            "finalAnswer",
            "evaluationNotes",
            "sourceWikiPages",
        ],
        output_schema_name="final_answer_judge_output_v1",
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Eval-only contract — never used in production student turns.",
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def build_default_prompt_registry() -> PromptRegistry:
    """Return a fresh `PromptRegistry` pre-populated with all Phase 1-21 contracts."""
    registry = PromptRegistry()
    registry.register(_generic_reasoning_block_contract())
    registry.register(_schema_repair_contract())
    registry.register(_intent_classifier_contract())
    registry.register(_preference_extractor_contract())
    registry.register(_entity_extractor_contract())
    registry.register(_answer_validator_contract())
    registry.register(_response_composer_contract())
    registry.register(_task_understanding_contract())
    registry.register(_planner_agent_contract())
    registry.register(_planner_repair_contract())
    registry.register(_specialist_graduation_progress_contract())
    registry.register(_specialist_course_catalog_contract())
    registry.register(_specialist_requirement_explanation_contract())
    registry.register(_dynamic_agent_contract())
    registry.register(_synthesis_composer_contract())
    registry.register(_final_answer_judge_contract())
    return registry
