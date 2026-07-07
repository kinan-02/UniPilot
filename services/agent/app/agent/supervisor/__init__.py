"""Supervisor Orchestrator Runtime (Phase 6/7) — shadow-only.

Consumes a normalized `PlannerOutput` (Phase 5) and executes its subtask
graph mechanics — dependency ordering, context compilation, handler
dispatch, blackboard updates, retries/budgets — through safe dry-run
handlers by default, or through a small, explicitly reviewed set of real
read-only workflow adapters (Phase 7) when safe and enabled. Never creates
an action proposal or performs a write, and never controls live routing.
Importing this package has no side effects.
"""

from __future__ import annotations

from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.budgets import BudgetTracker
from app.agent.supervisor.controller import ControllerDecision, decide_next_action
from app.agent.supervisor.errors import (
    DependencyCycleError,
    DuplicateSubtaskIdError,
    InvalidPlannerOutputError,
    SupervisorError,
    UnknownDependencyError,
)
from app.agent.supervisor.graph import ExecutionGraph
from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry, build_default_handler_registry
from app.agent.supervisor.handlers import (
    ContextPreviewHandler,
    DryRunCapabilityHandler,
    SubtaskHandler,
    UnsupportedCapabilityHandler,
)
from app.agent.supervisor.compare_diagnostics import build_supervisor_validation_metadata
from app.agent.supervisor.output_summarizer import summarize_agent_response, unsafe_output_summary
from app.agent.supervisor.post_context_runner import PostContextShadowCompareOutcome, run_post_context_shadow_compare
from app.agent.supervisor.promotion import (
    check_candidate_response_safety,
    eligible_promotion_workflows,
    evaluate_promotion_decision,
)
from app.agent.supervisor.promotion_diagnostics import build_supervisor_promotion_metadata
from app.agent.supervisor.promotion_schemas import (
    PromotionBlockReason,
    PromotionDecision,
    PromotionDecisionStatus,
    PromotionMode,
    ShadowCandidateBundle,
)
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.safety import can_shadow_execute_capability, shadow_execution_blocked_warning
from app.agent.supervisor.schemas import (
    ExecutionBudget,
    SubtaskExecutionRecord,
    SubtaskExecutionStatus,
    SubtaskHandlerKind,
    SubtaskResult,
    SupervisorRunInput,
    SupervisorRunOutput,
    SupervisorRunStatus,
    SupervisorRuntimeContext,
)
from app.agent.supervisor.shadow_compare import build_comparison_summary, compare_live_and_shadow_result
from app.agent.supervisor.validation import validate_shadow_run
from app.agent.supervisor.validation_schemas import (
    ShadowComparisonSummary,
    SupervisorValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatus,
)
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler

__all__ = [
    "SupervisorBlackboard",
    "BudgetTracker",
    "ControllerDecision",
    "decide_next_action",
    "DependencyCycleError",
    "DuplicateSubtaskIdError",
    "InvalidPlannerOutputError",
    "SupervisorError",
    "UnknownDependencyError",
    "ExecutionGraph",
    "SubtaskHandlerRegistry",
    "build_default_handler_registry",
    "ContextPreviewHandler",
    "DryRunCapabilityHandler",
    "SubtaskHandler",
    "UnsupportedCapabilityHandler",
    "summarize_agent_response",
    "unsafe_output_summary",
    "run_supervisor_shadow",
    "can_shadow_execute_capability",
    "shadow_execution_blocked_warning",
    "ExecutionBudget",
    "SubtaskExecutionRecord",
    "SubtaskExecutionStatus",
    "SubtaskHandlerKind",
    "SubtaskResult",
    "SupervisorRunInput",
    "SupervisorRunOutput",
    "SupervisorRunStatus",
    "SupervisorRuntimeContext",
    "compare_live_and_shadow_result",
    "ReadOnlyWorkflowAdapterHandler",
    "build_comparison_summary",
    "build_supervisor_validation_metadata",
    "run_post_context_shadow_compare",
    "validate_shadow_run",
    "ShadowComparisonSummary",
    "SupervisorValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationStatus",
    "PostContextShadowCompareOutcome",
    "check_candidate_response_safety",
    "eligible_promotion_workflows",
    "evaluate_promotion_decision",
    "build_supervisor_promotion_metadata",
    "PromotionBlockReason",
    "PromotionDecision",
    "PromotionDecisionStatus",
    "PromotionMode",
    "ShadowCandidateBundle",
]
