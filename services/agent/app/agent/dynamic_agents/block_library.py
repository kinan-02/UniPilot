"""Deterministic default block library for dynamic agents (Phase 15).

Every block is fixed, inspectable, read-only, and side-effect free. The
`AgentBuilder` assembles agents exclusively from blocks registered here —
never from generated code.
"""

from __future__ import annotations

from app.agent.dynamic_agents.schemas import AgentReasoningPattern, BlockDescriptor

CONTEXT_FILTER_BLOCK = "context_filter_block"
SINGLE_PASS_REASONING_BLOCK = "single_pass_reasoning_block"
TOOL_OBSERVATION_LOOP_BLOCK = "tool_observation_loop_block"
OUTPUT_SCHEMA_VALIDATION_BLOCK = "output_schema_validation_block"
SAFETY_VALIDATION_BLOCK = "safety_validation_block"
REFLECTION_REVISION_BLOCK = "reflection_revision_block"
COMPARISON_SYNTHESIS_BLOCK = "comparison_synthesis_block"
COMPACT_OUTPUT_SUMMARIZATION_BLOCK = "compact_output_summarization_block"
CLARIFICATION_NEED_CHECK_BLOCK = "clarification_need_check_block"

_ALL_PATTERNS: list[AgentReasoningPattern] = [
    "single_pass",
    "tool_observation_loop",
    "reflect_and_revise",
    "compare_and_synthesize",
    "structured_extraction",
    "clarification_assessment",
]

_SINGLE_PASS_PATTERNS: list[AgentReasoningPattern] = ["single_pass", "structured_extraction"]
_OBSERVATION_LOOP_PATTERNS: list[AgentReasoningPattern] = ["tool_observation_loop"]
_REFLECTION_PATTERNS: list[AgentReasoningPattern] = ["reflect_and_revise"]
_COMPARE_PATTERNS: list[AgentReasoningPattern] = ["compare_and_synthesize"]
_CLARIFICATION_PATTERNS: list[AgentReasoningPattern] = ["clarification_assessment"]
_REASONING_PATTERNS: list[AgentReasoningPattern] = [
    "single_pass",
    "tool_observation_loop",
    "reflect_and_revise",
    "compare_and_synthesize",
    "structured_extraction",
]


class BlockLibrary:
    """In-memory, insertion-ordered catalog of reusable dynamic-agent blocks."""

    def __init__(self) -> None:
        self._blocks: dict[str, BlockDescriptor] = {}

    def register(self, block: BlockDescriptor, *, overwrite: bool = False) -> None:
        if not overwrite and block.name in self._blocks:
            raise ValueError(f"block_already_registered: {block.name}")
        self._blocks[block.name] = block

    def get(self, name: str) -> BlockDescriptor | None:
        return self._blocks.get(name)

    def require(self, name: str) -> BlockDescriptor:
        block = self.get(name)
        if block is None:
            raise KeyError(f"unknown_block: {name}")
        return block

    def has(self, name: str) -> bool:
        return name in self._blocks

    def list_names(self) -> list[str]:
        return list(self._blocks)

    def list_blocks(self) -> list[BlockDescriptor]:
        return list(self._blocks.values())

    def blocks_for_pattern(self, pattern: AgentReasoningPattern) -> list[BlockDescriptor]:
        return [block for block in self._blocks.values() if pattern in block.compatible_reasoning_patterns]


class BlockNotFoundError(KeyError):
    """Raised when a requested block name is unknown."""


DEFAULT_BLOCKS_BY_PATTERN: dict[AgentReasoningPattern, tuple[str, ...]] = {
    "single_pass": (
        CONTEXT_FILTER_BLOCK,
        SINGLE_PASS_REASONING_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
    "tool_observation_loop": (
        CONTEXT_FILTER_BLOCK,
        TOOL_OBSERVATION_LOOP_BLOCK,
        SINGLE_PASS_REASONING_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
    "compare_and_synthesize": (
        CONTEXT_FILTER_BLOCK,
        SINGLE_PASS_REASONING_BLOCK,
        COMPARISON_SYNTHESIS_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
    "reflect_and_revise": (
        CONTEXT_FILTER_BLOCK,
        SINGLE_PASS_REASONING_BLOCK,
        REFLECTION_REVISION_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
    "structured_extraction": (
        CONTEXT_FILTER_BLOCK,
        SINGLE_PASS_REASONING_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
    "clarification_assessment": (
        CONTEXT_FILTER_BLOCK,
        CLARIFICATION_NEED_CHECK_BLOCK,
        OUTPUT_SCHEMA_VALIDATION_BLOCK,
        SAFETY_VALIDATION_BLOCK,
        COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    ),
}


def build_default_block_library() -> BlockLibrary:
    """Fresh registry with the Phase 15 block set in deterministic order."""
    library = BlockLibrary()
    descriptors = (
        BlockDescriptor(
            name=CONTEXT_FILTER_BLOCK,
            block_type="context_filter",
            description="Filter compiled context to the sections allowed by the AgentSpec context contract.",
            when_to_use="Always first — restricts context before any reasoning or observation work.",
            when_not_to_use="Never skip when a context contract is present.",
            required_inputs=["compiled_context", "context_contract"],
            produced_outputs=["filtered_context"],
            compatible_reasoning_patterns=list(_ALL_PATTERNS),
            read_only=True,
            side_effect_level="none",
        ),
        BlockDescriptor(
            name=SINGLE_PASS_REASONING_BLOCK,
            block_type="reasoning",
            description="One ReasoningBlock pass using the dynamic_agent_v1 prompt contract.",
            when_to_use="Default reasoning for single-pass and synthesis patterns.",
            when_not_to_use="When a multi-round observation loop is required instead.",
            required_inputs=["task_brief", "filtered_context", "deterministic_observations"],
            produced_outputs=["reasoning_result"],
            compatible_reasoning_patterns=_REASONING_PATTERNS,
            read_only=True,
            side_effect_level="none",
            can_call_reasoning_block=True,
        ),
        BlockDescriptor(
            name=TOOL_OBSERVATION_LOOP_BLOCK,
            block_type="observation_loop",
            description="Bounded observation tool-request loop using only spec-allowed observations.",
            when_to_use="When reasoning_pattern is tool_observation_loop.",
            when_not_to_use="For single-pass patterns with no additional observations needed.",
            required_inputs=["task_brief", "filtered_context", "allowed_observations"],
            produced_outputs=["augmented_observations"],
            compatible_reasoning_patterns=_OBSERVATION_LOOP_PATTERNS,
            read_only=True,
            side_effect_level="none",
            can_use_observations=True,
        ),
        BlockDescriptor(
            name=OUTPUT_SCHEMA_VALIDATION_BLOCK,
            block_type="validation",
            description="Validate structured output against the dynamic agent JSON schema.",
            when_to_use="After reasoning or synthesis blocks produce a candidate result.",
            when_not_to_use="Before any candidate structured output exists.",
            required_inputs=["reasoning_result", "output_schema"],
            produced_outputs=["validated_result"],
            compatible_reasoning_patterns=list(_ALL_PATTERNS),
            read_only=True,
            side_effect_level="none",
            can_validate_output=True,
        ),
        BlockDescriptor(
            name=SAFETY_VALIDATION_BLOCK,
            block_type="validation",
            description="Strip proposed actions, enforce shadow-only, and apply validation policy checks.",
            when_to_use="After output schema validation, before summarization.",
            when_not_to_use="Before structured output exists.",
            required_inputs=["validated_result", "validation_policy"],
            produced_outputs=["safe_result"],
            compatible_reasoning_patterns=list(_ALL_PATTERNS),
            read_only=True,
            side_effect_level="none",
            can_validate_output=True,
        ),
        BlockDescriptor(
            name=REFLECTION_REVISION_BLOCK,
            block_type="reflection",
            description="Optional reflect-and-revise pass (conservative single revision in Phase 15).",
            when_to_use="When reasoning_pattern is reflect_and_revise.",
            when_not_to_use="For simple single-pass tasks.",
            required_inputs=["reasoning_result", "task_brief"],
            produced_outputs=["revised_result"],
            compatible_reasoning_patterns=_REFLECTION_PATTERNS,
            read_only=True,
            side_effect_level="none",
            can_call_reasoning_block=True,
        ),
        BlockDescriptor(
            name=COMPARISON_SYNTHESIS_BLOCK,
            block_type="synthesis",
            description="Compact comparison synthesis over validated reasoning output.",
            when_to_use="When reasoning_pattern is compare_and_synthesize.",
            when_not_to_use="For non-comparison tasks.",
            required_inputs=["validated_result", "dependency_outputs"],
            produced_outputs=["synthesis_result"],
            compatible_reasoning_patterns=_COMPARE_PATTERNS,
            read_only=True,
            side_effect_level="none",
            can_synthesize=True,
        ),
        BlockDescriptor(
            name=COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
            block_type="summarization",
            description="Produce the final DynamicAgentRunOutput fields from safe validated output.",
            when_to_use="Final block in every supported pattern.",
            when_not_to_use="Before safety validation completes.",
            required_inputs=["safe_result"],
            produced_outputs=["run_output"],
            compatible_reasoning_patterns=list(_ALL_PATTERNS),
            read_only=True,
            side_effect_level="none",
        ),
        BlockDescriptor(
            name=CLARIFICATION_NEED_CHECK_BLOCK,
            block_type="clarification_check",
            description="Assess whether clarification is needed before reasoning.",
            when_to_use="When reasoning_pattern is clarification_assessment.",
            when_not_to_use="When the task brief already has sufficient context.",
            required_inputs=["task_brief", "filtered_context"],
            produced_outputs=["clarification_assessment"],
            compatible_reasoning_patterns=_CLARIFICATION_PATTERNS,
            read_only=True,
            side_effect_level="none",
        ),
    )
    for descriptor in descriptors:
        library.register(descriptor)
    return library
