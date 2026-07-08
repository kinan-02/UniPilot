"""Registry of versioned prompt contracts used by `ReasoningBlock`.

A `PromptContract` centralizes the role/system prompt, instructions, safety
rules, and default execution parameters for one reasoning task type — so
prompts stay reviewable in one place instead of being inlined at call sites.

`PromptContract`/`PromptRegistry` and the two contracts below
(`GENERIC_REASONING_BLOCK_V1`, `SCHEMA_REPAIR_V1`) are ported verbatim from
`services/agent/app/agent/reasoning/prompt_registry.py` — both are fully
generic (no dependency on any specific role's vocabulary), unlike the ~15
other contracts that file defined for `services/agent`'s old roles (task
understanding, the old Planner, the old 3 specialists), none of which are
ported here. The 5 new roles' contracts live in `app.agent_core.roles.prompts`
(a one-way dependency on this module, never the reverse, to avoid a cycle)
and are layered onto `build_default_prompt_registry()`'s output by
`roles.prompts.build_prompt_registry_with_roles()`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent_core.reasoning.schemas import ReasoningRiskLevel

GENERIC_REASONING_BLOCK_V1 = "generic_reasoning_block_v1"
SCHEMA_REPAIR_V1 = "schema_repair_v1"


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
    # `None` (the default) means every pass reuses the identical system prompt.
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


def build_default_prompt_registry() -> PromptRegistry:
    """Fresh `PromptRegistry` with only the two generic, role-agnostic contracts.

    Callers that need the 5 role contracts too should use
    `app.agent_core.roles.prompts.build_prompt_registry_with_roles()` instead,
    which layers them onto this base.
    """
    registry = PromptRegistry()
    registry.register(_generic_reasoning_block_contract())
    registry.register(_schema_repair_contract())
    return registry


__all__ = [
    "GENERIC_REASONING_BLOCK_V1",
    "SCHEMA_REPAIR_V1",
    "PromptContract",
    "PromptContractNotFoundError",
    "PromptRegistry",
    "build_default_prompt_registry",
]
