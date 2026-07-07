"""Dynamic AgentSpec + Block Library + Agent Builder (Phase 15)."""

from app.agent.dynamic_agents.block_library import BlockLibrary, build_default_block_library
from app.agent.dynamic_agents.builder import AgentBuilder
from app.agent.dynamic_agents.diagnostics import (
    build_dynamic_agent_run_summary,
    build_dynamic_agents_diagnostics,
    build_dynamic_agents_metadata_from_subtask_summaries,
)
from app.agent.dynamic_agents.output_summarizer import summarize_dynamic_agent_output
from app.agent.dynamic_agents.prompt_contracts import DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME, DYNAMIC_AGENT_V1
from app.agent.dynamic_agents.runtime import DynamicAgentInstance, build_reasoning_input, fallback_output
from app.agent.dynamic_agents.schemas import (
    AgentBuildResult,
    AgentReasoningPattern,
    AgentSpec,
    BlockDescriptor,
    DynamicAgentRunInput,
    DynamicAgentRunOutput,
    TaskBrief,
)
from app.agent.dynamic_agents.spec_validation import AgentSpecValidationError, require_valid_agent_spec, validate_agent_spec
from app.agent.dynamic_agents.supervisor_handler import DynamicAgentHandler

__all__ = [
    "AgentBuildResult",
    "AgentBuilder",
    "AgentReasoningPattern",
    "AgentSpec",
    "AgentSpecValidationError",
    "BlockDescriptor",
    "BlockLibrary",
    "DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME",
    "DYNAMIC_AGENT_V1",
    "DynamicAgentHandler",
    "DynamicAgentInstance",
    "DynamicAgentRunInput",
    "DynamicAgentRunOutput",
    "TaskBrief",
    "build_default_block_library",
    "build_dynamic_agent_run_summary",
    "build_dynamic_agents_diagnostics",
    "build_dynamic_agents_metadata_from_subtask_summaries",
    "build_reasoning_input",
    "build_default_block_library",
    "fallback_output",
    "require_valid_agent_spec",
    "summarize_dynamic_agent_output",
    "validate_agent_spec",
]
