"""Non-generative AgentBuilder (Phase 15).

Reads a validated `AgentSpec` and assembles a `DynamicAgentInstance` from
the fixed `BlockLibrary`. Never generates code, never calls an LLM, and never
executes the agent during build.
"""

from __future__ import annotations

from app.agent.dynamic_agents.block_library import (
    DEFAULT_BLOCKS_BY_PATTERN,
    BlockLibrary,
    build_default_block_library,
)
from app.agent.dynamic_agents.runtime import DynamicAgentInstance
from app.agent.dynamic_agents.schemas import AgentBuildResult, AgentSpec, BlockDescriptor
from app.agent.dynamic_agents.spec_validation import AgentSpecValidationError, require_valid_agent_spec


class AgentBuilder:
    """Deterministic assembler for shadow-only dynamic agents."""

    def __init__(self, *, block_library: BlockLibrary | None = None) -> None:
        self._library = block_library or build_default_block_library()

    def resolve_block_names(self, spec: AgentSpec) -> list[str]:
        if spec.allowed_blocks:
            return list(spec.allowed_blocks)
        return list(DEFAULT_BLOCKS_BY_PATTERN.get(spec.reasoning_pattern, ()))

    def resolve_blocks(self, spec: AgentSpec) -> list[BlockDescriptor]:
        return [self._library.require(name) for name in self.resolve_block_names(spec)]

    def build(self, spec: AgentSpec | dict) -> DynamicAgentInstance:
        validated = require_valid_agent_spec(spec, block_library=self._library)
        blocks = self.resolve_blocks(validated)
        if not blocks:
            raise AgentSpecValidationError("no_blocks_resolved_for_spec")
        return DynamicAgentInstance(spec=validated, blocks=blocks, block_library=self._library)

    def build_result(self, spec: AgentSpec | dict) -> AgentBuildResult:
        try:
            instance = self.build(spec)
            return AgentBuildResult(success=True, instance=instance, errors=[])
        except AgentSpecValidationError as exc:
            return AgentBuildResult(success=False, instance=None, errors=[str(exc)])
