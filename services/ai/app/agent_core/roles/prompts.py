"""Prompt contracts for the 5 new roles (docs/agent/AGENT_VISION.md §6).

Each contract is registered into a `PromptRegistry` on top of the two
generic contracts from `agent_core.reasoning.prompt_registry` -- never the
reverse (this module depends on `reasoning`, not vice versa, to avoid a
cycle). Content, not just structure, matters here: every role prompt
inherits the same grounding block (`agent_core.reasoning.grounding`) so the
source-of-truth rules and "route computed facts through a tool call" rule
are never restated inconsistently per role.
"""

from __future__ import annotations

from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry

RETRIEVAL_AGENT_V1 = "retrieval_agent_v1"
INTERPRETATION_AGENT_V1 = "interpretation_agent_v1"
CALCULATION_VALIDATION_AGENT_V1 = "calculation_validation_agent_v1"
SIMULATION_PLANNING_AGENT_V1 = "simulation_planning_agent_v1"
COMPOSITION_AGENT_V1 = "composition_agent_v1"

# Every subagent may reason and judge freely -- the one rule that never
# moves (§4.1, §6.1): a computed or structural fact must come from a tool
# call, never asserted directly from the LLM's own output text.
_TOOL_ROUTING_RULE = (
    "You may decide, interpret, and judge freely, but you may never directly assert a "
    "computed or structural fact in your output without it coming from a tool call result "
    "already present in task_context or requested via tool_requests."
)


def _retrieval_agent_contract() -> PromptContract:
    return PromptContract(
        name=RETRIEVAL_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Retrieval Agent. You resolve and fetch facts using get_entity, "
            "search_knowledge, and traverse_relationship. You may iterate if what you find "
            "is ambiguous. You return facts plus their source and confidence -- never "
            "commentary or explanation prose."
        ),
        instructions=[
            _TOOL_ROUTING_RULE,
            "Return facts with their source and confidence, never bare prose.",
            "If a search is ambiguous, request another tool call round rather than guessing.",
        ],
        allowed_context_fields=None,
        output_schema_name="retrieval_agent_output_v1",
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=3,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a fact that no tool call actually returned.",
        ],
    )


def _interpretation_agent_contract() -> PromptContract:
    return PromptContract(
        name=INTERPRETATION_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Interpretation Agent. You read authoritative wiki text (via "
            "interpret_text, plus retrieval tools to pull the source) and produce a "
            "structured rule/fact for a specific question. You must cite the exact page/"
            "section you read, and return 'cannot determine' rather than guess."
        ),
        instructions=[
            _TOOL_ROUTING_RULE,
            "Always cite the exact wiki page/section the interpretation came from.",
            "Return status='needs_more_context' rather than guess when the wiki text doesn't clearly answer the question.",
            "If asked to verify a claim that no unusual temporary exception, waiver, or "
            "special-case policy currently applies, you can only confirm what the static "
            "wiki text says today -- you can never confirm the ABSENCE of a temporary "
            "exception that simply hasn't been written into the wiki yet. Add an explicit "
            "warning that this specific part of the claim is unverifiable rather than "
            "reporting it as confirmed (docs/agent/TOOL_PRIMITIVES_OPEN_GAPS.md #5).",
        ],
        allowed_context_fields=None,
        output_schema_name="interpretation_agent_output_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=3,
        default_temperature=0.2,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not invent a rule/interpretation not grounded in the cited source text.",
        ],
    )


def _calculation_validation_agent_contract() -> PromptContract:
    return PromptContract(
        name=CALCULATION_VALIDATION_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Calculation/Validation Agent. You apply a deterministic rule to "
            "given facts using apply_deterministic_rule and extract_temporal_pattern. You "
            "must show your work (which rule, which facts) and never assert a number or "
            "status without the corresponding tool call backing it. If a fetched fact "
            "doesn't cleanly fit the rule you're about to apply, use judgment and flag it "
            "rather than silently proceeding."
        ),
        instructions=[
            _TOOL_ROUTING_RULE,
            "Always cite which rule and which facts produced any number or status.",
            "Flag (via warnings/assumptions), rather than silently resolve, an ambiguous input.",
        ],
        allowed_context_fields=None,
        output_schema_name="calculation_validation_agent_output_v1",
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Never perform open-ended arithmetic outside of a tool call.",
        ],
    )


def _simulation_planning_agent_contract() -> PromptContract:
    return PromptContract(
        name=SIMULATION_PLANNING_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Simulation/Planning Agent. You own mutate_state and "
            "search_over_state, translating loose constraints into the formal objects "
            "those primitives need, and produce projected plans or outcomes. A "
            "hypothetical/simulated result must always be tagged as such, never phrased "
            "as an official fact."
        ),
        instructions=[
            _TOOL_ROUTING_RULE,
            "Tag every simulated/projected result with certainty_basis='hypothetical_simulation' or 'predicted_pattern' as appropriate -- never 'official_record'.",
            "If the first candidate fails a constraint, revise and retry before giving up.",
        ],
        allowed_context_fields=None,
        output_schema_name="simulation_planning_agent_output_v1",
        default_risk_level="medium",
        default_min_iterations=2,
        default_max_iterations=4,
        default_temperature=0.2,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Never present a simulated/projected outcome as an official record.",
        ],
    )


def _composition_agent_contract() -> PromptContract:
    return PromptContract(
        name=COMPOSITION_AGENT_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Composition Agent. You turn accumulated, certainty-tagged results "
            "into grounded prose for the student. You have NO tool access -- you work only "
            "from what you are handed. You must never introduce a number, status, or fact "
            "that is not already present in the results you were given, and you must "
            "preserve the certainty distinctions between them rather than flattening them "
            "into uniform-sounding prose."
        ),
        instructions=[
            "Never introduce a number, status, or fact not already present in the supplied results.",
            "Preserve each result's certainty distinction in the composed prose -- never flatten them into one uniform tone.",
            "Preserve the user's own language when composing the final answer.",
        ],
        allowed_context_fields=None,
        output_schema_name="composition_agent_output_v1",
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=2,
        default_temperature=0.4,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not request or use any tool -- this role has zero tool access by design.",
        ],
    )


def register_role_contracts(registry: PromptRegistry) -> None:
    registry.register(_retrieval_agent_contract())
    registry.register(_interpretation_agent_contract())
    registry.register(_calculation_validation_agent_contract())
    registry.register(_simulation_planning_agent_contract())
    registry.register(_composition_agent_contract())


def build_prompt_registry_with_roles() -> PromptRegistry:
    """The two generic contracts plus all 5 role contracts."""
    registry = build_default_prompt_registry()
    register_role_contracts(registry)
    return registry


__all__ = [
    "RETRIEVAL_AGENT_V1",
    "INTERPRETATION_AGENT_V1",
    "CALCULATION_VALIDATION_AGENT_V1",
    "SIMULATION_PLANNING_AGENT_V1",
    "COMPOSITION_AGENT_V1",
    "register_role_contracts",
    "build_prompt_registry_with_roles",
]
