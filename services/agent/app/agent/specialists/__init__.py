"""Read-only specialist-agent wrappers (Phase 10) — shadow-only.

Structured, `ReasoningBlock`-powered workers for a small, explicitly
reviewed set of read-only academic subtasks
(`graduation_progress_agent`, `course_catalog_agent`,
`requirement_explanation_agent`). Every specialist:

- only ever calls the LLM through the shared `ReasoningBlock` runtime,
- receives a compiled, minimal context pack plus dependency outputs,
- returns a schema-validated `SpecialistAgentOutput` whose `proposed_actions`
  is always `[]` (enforced at the model level, not just by convention),
- falls back safely (never raises) when the LLM is unavailable or reasoning
  fails.

Write/proposal-capable specialists (`transcript_import_agent`,
`semester_planning_agent`, `action_proposal_agent`, `profile_update_agent`)
are deliberately out of scope for this phase — see
`app.agent.capabilities.default_registry` and `specialists.registry`.

Importing this package has no side effects. Specialist output is diagnostic/
shadow-only in Phase 10 — nothing here affects the live orchestrator's final
response, workflow selection, or the Phase 9 promotion gate.
"""

from __future__ import annotations

from app.agent.specialists.base import (
    build_output_from_result,
    build_task_context,
    fallback_output,
    run_specialist_reasoning,
)
from app.agent.specialists.compare import compare_workflow_and_specialist, specialist_agent_for_workflow
from app.agent.specialists.context import build_agent_context_pack_summary
from app.agent.specialists.course_catalog_agent import run_course_catalog_agent
from app.agent.specialists.diagnostics import (
    build_specialist_compare_diagnostics,
    build_specialist_validation_metadata,
)
from app.agent.specialists.graduation_progress_agent import run_graduation_progress_agent
from app.agent.specialists.output_summarizer import summarize_specialist_output
from app.agent.specialists.registry import (
    SpecialistAgentFn,
    SpecialistAgentNotFoundError,
    SpecialistAgentRegistry,
    build_default_specialist_agent_registry,
)
from app.agent.specialists.requirement_explanation_agent import run_requirement_explanation_agent
from app.agent.specialists.safety import is_specialist_agent_safe, specialist_agent_unsafe_warning
from app.agent.specialists.schemas import (
    SpecialistAgentInput,
    SpecialistAgentKind,
    SpecialistAgentOutput,
    SpecialistAgentStatus,
    SpecialistToolObservation,
)
from app.agent.specialists.supervisor_handler import SpecialistAgentHandler
from app.agent.specialists.tools.observation_builder import build_specialist_observations
from app.agent.specialists.tools.registry import (
    ObservationDescriptor,
    SpecialistObservationNotFoundError,
    SpecialistObservationRegistry,
    build_default_observation_registry,
)
from app.agent.specialists.tools.schemas import (
    SpecialistObservation,
    SpecialistObservationBundle,
    SpecialistObservationRequest,
)
from app.agent.specialists.validation import validate_specialist_output
from app.agent.specialists.validation_schemas import (
    WORKFLOW_TO_SPECIALIST_AGENT,
    SpecialistCompareDiagnostics,
    SpecialistOutputValidationResult,
    SpecialistValidationIssue,
    SpecialistValidationSeverity,
    SpecialistValidationStatus,
    WorkflowSpecialistComparison,
)

__all__ = [
    "build_output_from_result",
    "build_task_context",
    "fallback_output",
    "run_specialist_reasoning",
    "build_agent_context_pack_summary",
    "run_course_catalog_agent",
    "run_graduation_progress_agent",
    "run_requirement_explanation_agent",
    "summarize_specialist_output",
    "SpecialistAgentFn",
    "SpecialistAgentNotFoundError",
    "SpecialistAgentRegistry",
    "build_default_specialist_agent_registry",
    "is_specialist_agent_safe",
    "specialist_agent_unsafe_warning",
    "SpecialistAgentInput",
    "SpecialistAgentKind",
    "SpecialistAgentOutput",
    "SpecialistAgentStatus",
    "SpecialistToolObservation",
    "SpecialistAgentHandler",
    "compare_workflow_and_specialist",
    "specialist_agent_for_workflow",
    "build_specialist_compare_diagnostics",
    "build_specialist_validation_metadata",
    "validate_specialist_output",
    "WORKFLOW_TO_SPECIALIST_AGENT",
    "SpecialistCompareDiagnostics",
    "SpecialistOutputValidationResult",
    "SpecialistValidationIssue",
    "SpecialistValidationSeverity",
    "SpecialistValidationStatus",
    "WorkflowSpecialistComparison",
    "build_specialist_observations",
    "ObservationDescriptor",
    "SpecialistObservationNotFoundError",
    "SpecialistObservationRegistry",
    "build_default_observation_registry",
    "SpecialistObservation",
    "SpecialistObservationBundle",
    "SpecialistObservationRequest",
]
