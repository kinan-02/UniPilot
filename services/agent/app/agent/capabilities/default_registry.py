"""Default `CapabilityRegistry` construction (Phase 4).

Registers metadata for:
- the 6 workflows that exist and run today,
- 10 future specialist-agent descriptors (Phase 5+ placeholders — not
  executable yet),
- the concrete deterministic validator/composer pieces that exist today,
- tools, retrieval, and internal-API capabilities the workflows already use.

Deterministic and side-effect free: call `build_default_capability_registry()`
to get a fresh, fully-populated registry. No database or LLM access.
"""

from __future__ import annotations

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import (
    CapabilityContextContract,
    CapabilityDescriptor,
    CapabilityExecutionMetadata,
    CapabilityIOContract,
    CapabilityPermissionScope,
)
from app.agent.context_compiler import context_sections as sections

# ---------------------------------------------------------------------------
# Phase 7 execution metadata — set only after reading each workflow's source
# and confirming it never writes to Mongo and never creates an
# `agent_action_proposals` document. `_READ_ONLY_WORKFLOW_EXECUTION`
# documents that review inline; `_NOT_SHADOW_EXECUTABLE` is the explicit,
# reviewed opposite for the two proposal-creating workflows — see
# `app.agent.supervisor.workflow_adapters` for the handler that consumes
# `handler_name="read_only_workflow_adapter"`.
# ---------------------------------------------------------------------------

_READ_ONLY_WORKFLOW_EXECUTION = CapabilityExecutionMetadata(
    execution_supported=True,
    shadow_execution_supported=True,
    handler_name="read_only_workflow_adapter",
    side_effect_level="none",
    safe_for_shadow_execution=True,
)

# Reviewed: both `transcript_import_workflow` and `semester_planning_workflow`
# call `create_agent_action_proposal(...)` (writes an `agent_action_proposals`
# document) on every successful run — never safe to shadow-execute, Phase 7
# or later, unless a dedicated no-side-effect preview mode is built and
# reviewed separately.
# Phase 8: `general_academic_workflow` is read-only and passes every
# `safety.can_shadow_execute_capability` check, but it may unconditionally
# call an LLM (via the existing, already-approved `ReasoningBlock` path —
# see the workflow's own notes below) — real-executing it on every turn
# purely for shadow comparison would add real LLM cost/latency/noise with
# no safety benefit. `operationally_expensive_for_shadow_execution=True`
# keeps it eligible for dry-run/graph-mechanics shadow execution while
# `app.agent.supervisor.runtime._select_handler` skips real execution for it
# by default (see Phase 8 notes there).
_READ_ONLY_BUT_LLM_EXPENSIVE_WORKFLOW_EXECUTION = CapabilityExecutionMetadata(
    execution_supported=True,
    shadow_execution_supported=True,
    handler_name="read_only_workflow_adapter",
    side_effect_level="none",
    safe_for_shadow_execution=True,
    operationally_expensive_for_shadow_execution=True,
)

# Phase 10: the three read-only specialist agents — reviewed to confirm each
# only ever calls the LLM through `ReasoningBlock`, never writes to Mongo,
# and never creates an `agent_action_proposals` document (its output's
# `proposed_actions` field is forced to `[]` at the model level regardless).
# See `app.agent.specialists.supervisor_handler` for the handler that
# consumes `handler_name="specialist_agent_handler"`.
_READ_ONLY_SPECIALIST_AGENT_EXECUTION = CapabilityExecutionMetadata(
    execution_supported=True,
    shadow_execution_supported=True,
    handler_name="specialist_agent_handler",
    side_effect_level="none",
    safe_for_shadow_execution=True,
)

# post-Phase-9: real, proposal-creating execution only, never shadow/dry-run
# comparison. Reviewed to confirm both `transcript_import_workflow` and
# `semester_planning_workflow` only ever call `create_agent_action_proposal`
# (never a direct mutation) -- see `app.agent.planner_first_live` for the
# separately, explicitly gated caller this enables, and
# `app.agent.supervisor.safety.can_execute_capability_for_real_with_proposals`
# for the dispatch-time safety predicate. `shadow_execution_supported` and
# `safe_for_shadow_execution` stay permanently `False` for these two --
# shadow/diagnostic/promotion dispatch must never create a real proposal.
_PROPOSAL_CAPABLE_REAL_EXECUTION = CapabilityExecutionMetadata(
    execution_supported=True,
    shadow_execution_supported=False,
    handler_name="proposal_capable_workflow_adapter",
    side_effect_level="proposal",
    safe_for_shadow_execution=False,
    real_execution_supported_with_proposals=True,
)

# ---------------------------------------------------------------------------
# Workflows — mirrors `app.agent.task_planner._WORKFLOW_BY_INTENT` /
# `app.agent.workflows.registry`. Duplicated here deliberately (small, stable
# metadata) rather than imported, to keep this module free of any import-time
# coupling to the live routing table.
# ---------------------------------------------------------------------------

_ACADEMIC_WORKFLOW_CONTEXT = CapabilityContextContract(
    allowed_context_sections=[
        sections.USER_MESSAGE,
        sections.DETERMINISTIC_INTENT,
        sections.DETERMINISTIC_ENTITIES,
        sections.CONVERSATION_ENTITIES,
        sections.CONVERSATION_ASSUMPTIONS,
        sections.PROFILE_SUMMARY,
        sections.AGENT_CONTEXT_PACK_SUMMARY,
    ],
    forbidden_context_sections=[],
    max_recent_messages=6,
    max_wiki_snippets=8,
)


def _workflow_capabilities() -> list[CapabilityDescriptor]:
    return [
        CapabilityDescriptor(
            name="graduation_progress_workflow",
            type="workflow",
            description="Compute graduation/degree progress from completed courses and requirements.",
            owner="services/agent/app/agent/workflows/graduation_progress_workflow.py",
            supported_intents=["graduation_progress_check"],
            supported_task_categories=["academic_analysis"],
            risk_level="low",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                allowed_internal_endpoints=["/internal/agent/graduation-audit/users/{id}"],
            ),
            context=_ACADEMIC_WORKFLOW_CONTEXT,
            execution=_READ_ONLY_WORKFLOW_EXECUTION,
        ),
        CapabilityDescriptor(
            name="course_question_workflow",
            type="workflow",
            description="Answer eligibility, prerequisite, or offering questions about a specific course.",
            owner="services/agent/app/agent/workflows/course_question_workflow.py",
            supported_intents=["course_question", "prerequisite_check"],
            supported_task_categories=["simple_question"],
            risk_level="low",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_read_offerings=True,
                allowed_internal_endpoints=["/internal/agent/course-requirement-contribution"],
            ),
            context=_ACADEMIC_WORKFLOW_CONTEXT,
            execution=_READ_ONLY_WORKFLOW_EXECUTION,
        ),
        CapabilityDescriptor(
            name="transcript_import_workflow",
            type="workflow",
            description="Parse an uploaded transcript and let the student review/confirm before saving.",
            owner="services/agent/app/agent/workflows/transcript_import_workflow.py",
            supported_intents=["transcript_import", "completed_courses_update"],
            supported_task_categories=["transcript_processing"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_create_action_proposals=True,
                write_scope="proposal_only",
                allowed_collections=["agent_action_proposals"],
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.DETERMINISTIC_ENTITIES,
                    sections.PROFILE_SUMMARY,
                    sections.ATTACHMENT_METADATA,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                ],
                include_attachment_metadata=True,
                include_attachment_contents=False,
                include_full_transcript_rows=False,
            ),
            notes=["Only ever creates an action proposal; api's confirm route performs the write."],
            execution=_PROPOSAL_CAPABLE_REAL_EXECUTION,
        ),
        CapabilityDescriptor(
            name="semester_planning_workflow",
            type="workflow",
            description="Generate or modify a semester schedule/plan.",
            owner="services/agent/app/agent/workflows/semester_planning_workflow.py",
            supported_intents=["semester_plan_generation", "semester_plan_modification"],
            supported_task_categories=["planning"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_read_offerings=True,
                can_create_action_proposals=True,
                write_scope="proposal_only",
                allowed_collections=["agent_action_proposals"],
                allowed_internal_endpoints=["/internal/agent/semester-plan-options/users/{id}"],
            ),
            context=_ACADEMIC_WORKFLOW_CONTEXT,
            notes=["Only ever creates an action proposal; api's confirm route performs the write."],
            execution=_PROPOSAL_CAPABLE_REAL_EXECUTION,
        ),
        CapabilityDescriptor(
            name="requirement_explanation_workflow",
            type="workflow",
            description="Explain a degree requirement bucket and what satisfies it.",
            owner="services/agent/app/agent/workflows/requirement_explanation_workflow.py",
            supported_intents=["requirement_explanation"],
            supported_task_categories=["requirement_explanation"],
            risk_level="low",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                allowed_internal_endpoints=["/internal/agent/graduation-audit/users/{id}"],
            ),
            context=_ACADEMIC_WORKFLOW_CONTEXT,
            execution=_READ_ONLY_WORKFLOW_EXECUTION,
        ),
        CapabilityDescriptor(
            name="general_academic_workflow",
            type="workflow",
            description="General/catalog Q&A, profile-update guidance, and unsupported/unclear requests.",
            owner="services/agent/app/agent/workflows/general_academic_workflow.py",
            supported_intents=[
                "catalog_search",
                "profile_update",
                "program_minor_lookup",
                "track_structure_lookup",
                "regulation_lookup",
                "general_academic_question",
                "unknown_or_unsupported",
            ],
            supported_task_categories=["simple_question", "unsupported"],
            risk_level="low",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_read_wiki=True,
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.DETERMINISTIC_INTENT,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.WIKI_SNIPPETS,
                ],
                max_wiki_snippets=8,
            ),
            execution=_READ_ONLY_BUT_LLM_EXPENSIVE_WORKFLOW_EXECUTION,
            notes=[
                "Never writes to Mongo and never creates an action proposal — safe to "
                "shadow-execute. May call ReasoningBlock (existing Phase 2 migration, "
                "already the only approved LLM path) for catalog_search/general "
                "questions; that call is unconditional in the live path today (no "
                "dedicated AGENT_LLM_*_ENABLED flag — a pre-existing inconsistency, "
                "see Phase 2 notes) and fails safely to deterministic baseline text "
                "when no LLM is configured. No new LLM call was added for Phase 7.",
                "Phase 8: marked operationally_expensive_for_shadow_execution — real "
                "shadow execution is skipped by default (falls back to the safe "
                "dry-run handler) so post-context shadow comparison never triggers a "
                "real LLM call on every turn; still fully eligible for dry-run/graph "
                "mechanics shadow execution.",
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Future specialist agents — Phase 5+ placeholders. Metadata only: none of
# these are executable in Phase 4. Context contracts follow the Phase 4 spec
# examples for the 5 explicitly-specified agents; the remaining 5 mirror
# their corresponding workflow's needs as a reasonable starting point.
# ---------------------------------------------------------------------------


def _specialist_agent_capabilities() -> list[CapabilityDescriptor]:
    return [
        CapabilityDescriptor(
            name="task_understanding_agent",
            type="specialist_agent",
            risk_level="medium",
            description="Deeply understands the user's task before planning/workflow execution (Phase 3, live).",
            owner="services/agent/app/agent/task_understanding/",
            supported_task_categories=[
                "simple_question",
                "academic_analysis",
                "planning",
                "transcript_processing",
                "requirement_explanation",
                "write_or_update_request",
                "multi_step_task",
                "unsupported",
            ],
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.CONVERSATION_SUMMARY,
                    sections.RECENT_MESSAGES,
                    sections.CONVERSATION_ENTITIES,
                    sections.CONVERSATION_ASSUMPTIONS,
                    sections.DETERMINISTIC_INTENT,
                    sections.DETERMINISTIC_ENTITIES,
                    sections.PROFILE_SUMMARY,
                    sections.ATTACHMENT_METADATA,
                ],
                forbidden_context_sections=[
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.WIKI_SNIPPETS,
                ],
                include_attachment_metadata=True,
                include_attachment_contents=False,
                include_full_catalog=False,
                include_full_transcript_rows=False,
            ),
            notes=["Already implemented and live (diagnostic dry-run only) — not a future placeholder."],
        ),
        CapabilityDescriptor(
            name="planner_agent",
            type="specialist_agent",
            description="Phase 5 placeholder: decomposes a task into subtasks across capabilities.",
            owner="phase5",
            enabled=False,
            supported_task_categories=["planning", "multi_step_task"],
            risk_level="high",
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.DETERMINISTIC_INTENT,
                    sections.DETERMINISTIC_ENTITIES,
                    sections.CONVERSATION_SUMMARY,
                    sections.CONVERSATION_ENTITIES,
                    sections.CONVERSATION_ASSUMPTIONS,
                    sections.PROFILE_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            notes=["Not implemented. Registered so Phase 5 has a descriptor to build against."],
        ),
        CapabilityDescriptor(
            name="graduation_progress_agent",
            type="specialist_agent",
            description="Phase 10: read-only specialist wrapper around graduation-progress computation.",
            owner="services/agent/app/agent/specialists/graduation_progress_agent.py",
            enabled=True,
            supported_intents=["graduation_progress_check"],
            supported_task_categories=["academic_analysis"],
            risk_level="high",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            execution=_READ_ONLY_SPECIALIST_AGENT_EXECUTION,
            notes=[
                "Phase 10: implemented, shadow-only. Reasons via ReasoningBlock over "
                "compiled_context/dependency_outputs only -- never recalculates "
                "credits/eligibility itself. `graduation_progress_workflow` remains "
                "the live, authoritative equivalent; this agent's output never "
                "affects the final response and is never promotable (Phase 9 "
                "promotion is restricted to graduation_progress_workflow, not this "
                "agent name).",
            ],
        ),
        CapabilityDescriptor(
            name="course_catalog_agent",
            type="specialist_agent",
            description="Phase 10: read-only specialist wrapper around catalog/course-question retrieval.",
            owner="services/agent/app/agent/specialists/course_catalog_agent.py",
            enabled=True,
            supported_intents=["course_question", "prerequisite_check", "catalog_search"],
            supported_task_categories=["simple_question"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_read_offerings=True,
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.DETERMINISTIC_ENTITIES,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.WIKI_SNIPPETS,
                    sections.PREVIOUS_RESULTS,
                ],
                max_wiki_snippets=8,
            ),
            execution=_READ_ONLY_SPECIALIST_AGENT_EXECUTION,
            notes=[
                "Phase 10: implemented, shadow-only. `course_question_workflow` "
                "remains the live, authoritative equivalent.",
            ],
        ),
        CapabilityDescriptor(
            name="semester_planning_agent",
            type="specialist_agent",
            description="Phase 5+ placeholder: specialist wrapper around semester plan generation.",
            owner="phase5",
            enabled=False,
            supported_intents=["semester_plan_generation", "semester_plan_modification"],
            supported_task_categories=["planning"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_create_action_proposals=True,
                write_scope="proposal_only",
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.DETERMINISTIC_ENTITIES,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            notes=["Not implemented. `semester_planning_workflow` is the live equivalent today."],
        ),
        CapabilityDescriptor(
            name="transcript_import_agent",
            type="specialist_agent",
            description="Phase 5+ placeholder: specialist wrapper around transcript review/import proposals.",
            owner="phase5",
            enabled=False,
            supported_intents=["transcript_import", "completed_courses_update"],
            supported_task_categories=["transcript_processing"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_create_action_proposals=True,
                write_scope="proposal_only",
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.ATTACHMENT_METADATA,
                    sections.PROFILE_SUMMARY,
                ],
                include_attachment_metadata=True,
                include_attachment_contents=False,
                include_full_transcript_rows=False,
            ),
            notes=["Not implemented. `transcript_import_workflow` is the live equivalent today."],
        ),
        CapabilityDescriptor(
            name="requirement_explanation_agent",
            type="specialist_agent",
            description="Phase 10: read-only specialist wrapper around requirement-bucket explanation.",
            owner="services/agent/app/agent/specialists/requirement_explanation_agent.py",
            enabled=True,
            supported_intents=["requirement_explanation"],
            supported_task_categories=["requirement_explanation"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
            ),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            execution=_READ_ONLY_SPECIALIST_AGENT_EXECUTION,
            notes=[
                "Phase 10: implemented, shadow-only. `requirement_explanation_workflow` "
                "remains the live, authoritative equivalent.",
            ],
        ),
        CapabilityDescriptor(
            name="dynamic_agent",
            type="specialist_agent",
            description="Phase 15: shadow-only dynamically configured sub-agent assembled from BlockLibrary.",
            owner="services/agent/app/agent/dynamic_agents/",
            enabled=True,
            supported_intents=[],
            supported_task_categories=["multi_step_task"],
            risk_level="medium",
            permissions=CapabilityPermissionScope(),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PROFILE_SUMMARY,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            execution=_READ_ONLY_SPECIALIST_AGENT_EXECUTION,
            notes=[
                "Phase 15: shadow-only dynamic AgentSpec execution. Never affects final answers "
                "or replaces named specialists/workflows.",
            ],
        ),
        CapabilityDescriptor(
            name="general_academic_rag_agent",
            type="specialist_agent",
            description="Phase 5+ placeholder: specialist wrapper around general/catalog wiki RAG Q&A.",
            owner="phase5",
            enabled=False,
            supported_intents=["catalog_search", "general_academic_question", "unknown_or_unsupported"],
            supported_task_categories=["simple_question", "unsupported"],
            risk_level="low",
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PROFILE_SUMMARY,
                    sections.WIKI_SNIPPETS,
                    sections.PREVIOUS_RESULTS,
                ],
                max_wiki_snippets=8,
            ),
            notes=["Not implemented. `general_academic_workflow` is the live equivalent today."],
        ),
        CapabilityDescriptor(
            name="validator_agent",
            type="specialist_agent",
            description="Phase 5+ placeholder: specialist agent that checks a draft result against source-of-truth data.",
            owner="phase5",
            enabled=False,
            supported_task_categories=["academic_analysis", "planning"],
            risk_level="medium",
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.TASK_UNDERSTANDING,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            notes=[
                "Not implemented. Would consult app.agent.capabilities.source_of_truth "
                "to resolve conflicts between LLM output and deterministic data.",
            ],
        ),
        CapabilityDescriptor(
            name="response_composer_agent",
            type="specialist_agent",
            description="Phase 5+ placeholder: specialist agent that composes the final user-facing reply.",
            owner="phase5",
            enabled=False,
            supported_task_categories=[
                "simple_question",
                "academic_analysis",
                "planning",
                "transcript_processing",
                "requirement_explanation",
            ],
            risk_level="low",
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PREVIOUS_RESULTS,
                    sections.AGENT_CONTEXT_PACK_SUMMARY,
                    sections.CONVERSATION_ASSUMPTIONS,
                    sections.EXTRA_CONTEXT,
                ],
            ),
            notes=["Not implemented. `llm_response_composer.enhance_response_with_llm` is the live equivalent today."],
        ),
    ]


# ---------------------------------------------------------------------------
# Concrete deterministic validator/composer pieces that exist today (not
# future agents) — gives real coverage of the "validator"/"composer"
# capability types alongside the agentic placeholders above.
# ---------------------------------------------------------------------------


def _validator_and_composer_capabilities() -> list[CapabilityDescriptor]:
    return [
        CapabilityDescriptor(
            name="context_validator",
            type="validator",
            description="Validates AgentContextPack completeness/status before workflow execution.",
            owner="services/agent/app/agent/context_validator.py",
            risk_level="low",
            context=CapabilityContextContract(
                allowed_context_sections=[sections.AGENT_CONTEXT_PACK_SUMMARY],
            ),
        ),
        CapabilityDescriptor(
            name="response_composer",
            type="composer",
            description="Composes the deterministic AgentResponse (text + blocks) after a workflow completes.",
            owner="services/agent/app/agent/response_composer.py",
            risk_level="low",
            context=CapabilityContextContract(
                allowed_context_sections=[sections.PREVIOUS_RESULTS, sections.AGENT_CONTEXT_PACK_SUMMARY],
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Tools / retrieval / internal APIs already used by the live path.
# ---------------------------------------------------------------------------


def _tool_and_retrieval_capabilities() -> list[CapabilityDescriptor]:
    return [
        CapabilityDescriptor(
            name="context_builder",
            type="tool",
            description="Assembles the AgentContextPack (Mongo + academic graph retrieval) for one turn.",
            owner="services/agent/app/agent/context_builder.py",
            risk_level="low",
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_catalog=True,
                can_read_offerings=True,
                can_read_wiki=True,
            ),
        ),
        CapabilityDescriptor(
            name="clarification_capability",
            type="tool",
            description="Phase 17: deterministic clarification need detection, policy, and compact diagnostics.",
            owner="services/agent/app/agent/clarification/",
            enabled=True,
            supported_intents=[],
            supported_task_categories=["multi_step_task", "planning", "academic_analysis"],
            risk_level="low",
            permissions=CapabilityPermissionScope(),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.CONVERSATION_ASSUMPTIONS,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            execution=CapabilityExecutionMetadata(
                execution_supported=True,
                shadow_execution_supported=True,
                handler_name=None,
                side_effect_level="none",
                safe_for_shadow_execution=True,
            ),
            notes=[
                "Phase 17/18: diagnostic-only by default. Distinguishes preference vs epistemic "
                "ambiguity, applies consequence-aware ask/assume/skip policy, supports cross-turn "
                "pending state when user-facing clarification is enabled, and never writes student "
                "data or creates action proposals.",
            ],
        ),
        CapabilityDescriptor(
            name="synthesis_composer_capability",
            type="tool",
            description="Phase 21: reconciles workflow, specialist, dynamic-agent, monitor, clarification, and repair evidence into a diagnostic synthesis candidate.",
            owner="services/agent/app/agent/synthesis/",
            enabled=True,
            supported_intents=[],
            supported_task_categories=["multi_step_task", "planning", "academic_analysis"],
            risk_level="high",
            permissions=CapabilityPermissionScope(),
            context=CapabilityContextContract(
                allowed_context_sections=[
                    sections.USER_MESSAGE,
                    sections.TASK_UNDERSTANDING,
                    sections.PREVIOUS_RESULTS,
                ],
            ),
            execution=CapabilityExecutionMetadata(
                execution_supported=True,
                shadow_execution_supported=True,
                handler_name=None,
                side_effect_level="none",
                safe_for_shadow_execution=True,
            ),
            notes=[
                "Phase 21/22: diagnostic-only by default. Builds compact SynthesisInput from post-context "
                "summaries, applies deterministic trust ranking and conflict detection, optionally uses "
                "ReasoningBlock when enabled, attaches synthesisDiagnostics without changing final answers. "
                "Phase 22 adds controlled text-only promotion behind AGENT_SYNTHESIS_TEXT_PROMOTION_* flags.",
            ],
        ),
        CapabilityDescriptor(
            name="academic_graph_retrieval",
            type="retrieval",
            description=(
                "Wiki knowledge graph + semester JSON retrieval "
                "(schedule, prerequisites, eligibility, wiki search)."
            ),
            owner="services/agent/app/retrieval/graph_retriever.py",
            risk_level="low",
            permissions=CapabilityPermissionScope(can_read_wiki=True),
            notes=["Primary retrieval backend; replaces legacy hybrid RAG."],
        ),
        CapabilityDescriptor(
            name="wiki_hybrid_retrieval",
            type="retrieval",
            description="LEGACY: BM25 + embedding hybrid retrieval over the Obsidian catalog wiki.",
            owner="services/agent/app/retrieval/hybrid_wiki_retriever.py",
            risk_level="low",
            permissions=CapabilityPermissionScope(can_read_wiki=True),
            notes=["Deprecated — not wired into the live orchestrator path."],
        ),
        CapabilityDescriptor(
            name="agentic_wiki_retrieval",
            type="retrieval",
            description="Multi-step query decomposition + gap-driven wiki retrieval refinement.",
            owner="services/agent/app/agent/query_decomposer.py",
            risk_level="low",
            permissions=CapabilityPermissionScope(can_read_wiki=True),
            notes=["Enabled via AGENT_AGENTIC_RETRIEVAL_ENABLED."],
        ),
        CapabilityDescriptor(
            name="graduation_audit_internal_api",
            type="internal_api",
            description="api-side graduation audit engine (graduation_progress_calculator).",
            owner="services/api/app/routes/internal_agent.py",
            risk_level="low",
            io=CapabilityIOContract(output_schema_name="GraduationAuditResult"),
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                allowed_internal_endpoints=["/internal/agent/graduation-audit/users/{id}"],
            ),
            notes=["Stays in api to avoid duplicating the core graduation-rules engine."],
        ),
        CapabilityDescriptor(
            name="semester_plan_options_internal_api",
            type="internal_api",
            description="api-side semester plan option generation engine.",
            owner="services/api/app/routes/internal_agent.py",
            risk_level="low",
            io=CapabilityIOContract(output_schema_name="SemesterPlanningResult"),
            permissions=CapabilityPermissionScope(
                can_read_student_data=True,
                can_read_offerings=True,
                allowed_internal_endpoints=["/internal/agent/semester-plan-options/users/{id}"],
            ),
            notes=["Stays in api to avoid duplicating the shared planning/suggestion engine."],
        ),
        CapabilityDescriptor(
            name="course_requirement_contribution_internal_api",
            type="internal_api",
            description="api-side pool/matrix requirement-contribution matching engine.",
            owner="services/api/app/routes/internal_agent.py",
            risk_level="low",
            io=CapabilityIOContract(output_schema_name="dict[str, Any]"),
            permissions=CapabilityPermissionScope(
                can_read_catalog=True,
                allowed_internal_endpoints=["/internal/agent/course-requirement-contribution"],
            ),
            notes=["Stays in api to avoid duplicating the pool/matrix classification engine."],
        ),
        CapabilityDescriptor(
            name="transcript_parser",
            type="tool",
            description="Extracts course rows from an uploaded transcript PDF (separate microservice).",
            owner="services/transcript-parser/",
            risk_level="low",
            permissions=CapabilityPermissionScope(),
            notes=[
                "Invoked by api's route layer (agent_attachment_service) before the turn "
                "reaches the agent service — agent only ever receives the already-parsed "
                "attachment metadata + parsePreview, never calls transcript-parser directly.",
            ],
        ),
        CapabilityDescriptor(
            name="action_proposal_creator",
            type="tool",
            description="Creates an agent_action_proposals document for a proposed write.",
            owner="services/agent/app/repositories/agent_action_proposal_repository.py",
            risk_level="medium",
            permissions=CapabilityPermissionScope(
                can_create_action_proposals=True,
                write_scope="proposal_only",
                allowed_collections=["agent_action_proposals"],
            ),
            notes=[
                "The only capability besides api's own confirm/reject routes with any write "
                "scope — and even this only ever proposes, never executes, a write.",
            ],
        ),
    ]


def build_default_capability_registry() -> CapabilityRegistry:
    """Return a fresh `CapabilityRegistry` pre-populated with all default capabilities."""
    registry = CapabilityRegistry()
    for capability in (
        _workflow_capabilities()
        + _specialist_agent_capabilities()
        + _validator_and_composer_capabilities()
        + _tool_and_retrieval_capabilities()
    ):
        registry.register(capability)
    return registry
