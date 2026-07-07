"""JSON Schemas for `ReasoningBlockOutput.result` on each migrated agent call site.

Each schema intentionally matches the shape the existing (pre-`ReasoningBlock`)
implementation already produced and the shape downstream code already
consumes — Phase 2 is a compatibility migration, not a behavior change. Do
not widen these schemas without also updating the call site that maps
`result` back into the existing return type.
"""

from __future__ import annotations

from typing import Any, get_args

from app.agent.schemas import AgentIntent

_VALID_AGENT_INTENTS: tuple[str, ...] = get_args(AgentIntent)

# ---------------------------------------------------------------------------
# Intent classifier — matches `IntentClassification` / the legacy LLM payload
# consumed by `llm_intent_classifier._classify_with_llm`.
# ---------------------------------------------------------------------------
INTENT_CLASSIFIER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(_VALID_AGENT_INTENTS)},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "requiresFile": {"type": "boolean"},
        "requiresConfirmation": {"type": "boolean"},
        "requiredContext": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent", "confidence"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Preference extractor — matches the entity keys merged in
# `llm_preference_extractor.extract_planning_preferences` (kept camelCase to
# stay compatible with `entity_resolver` / `conversation_memory` keys).
# ---------------------------------------------------------------------------
PREFERENCE_EXTRACTOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "maxCredits": {"type": ["number", "null"]},
        "avoidDays": {"type": "array", "items": {"type": "string"}},
        "planningObjective": {
            "type": ["string", "null"],
            "enum": ["lighter_workload", "heavier_workload", None],
        },
        "targetSemester": {"type": ["string", "null"]},
        "targetSemesterCode": {"type": ["string", "null"]},
        "modificationType": {
            "type": ["string", "null"],
            "enum": [
                "lighter",
                "replace_course",
                "add_course",
                "avoid_days",
                "avoid_morning",
                None,
            ],
        },
        "replaceCourseNumber": {"type": ["string", "null"]},
        "addCourseNumber": {"type": ["string", "null"]},
    },
    "required": [],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Entity extraction fallback — matches the fields merged in
# `llm_entity_extractor.resolve_entities_with_llm_fallback`. At most one of
# these is ever expected to be non-null (the message is about one entity).
# ---------------------------------------------------------------------------
ENTITY_EXTRACTOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "courseNumber": {"type": ["string", "null"]},
        "trackSlug": {"type": ["string", "null"]},
        "programSlug": {"type": ["string", "null"]},
        "wikiSlug": {"type": ["string", "null"]},
    },
    "required": [],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Answer / retrieval validator — matches the dict returned by
# `llm_answer_validator.validate_retrieval_with_llm`.
# ---------------------------------------------------------------------------
ANSWER_VALIDATOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sufficient": {"type": "boolean"},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["sufficient"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Response composer — the LLM may only rewrite explanation *text*. Extra
# fields are accepted (for future surfacing / tracing) but the mapping code
# only ever reads `text`; structured blocks, actions, sources, and warnings
# stay under deterministic control.
# ---------------------------------------------------------------------------
RESPONSE_COMPOSER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "assumptions_to_surface": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["text"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Task Understanding Agent (Phase 3) — matches
# `app.agent.task_understanding.schemas.TaskUnderstandingOutput`, minus the
# `source` field (set by Python, never by the LLM). `primary_intent` and
# `secondary_intents` are intentionally free-form strings rather than an
# enum: the reconciler in `app.agent.task_understanding.normalizer` is
# responsible for rejecting unsupported values and falling back to the
# deterministic intent, per the Phase 3 spec's explicit 3-step rule — a
# generic schema-repair retry is not the right tool for that decision.
# ---------------------------------------------------------------------------
TASK_UNDERSTANDING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "needs_more_context", "failed"]},
        "user_goal": {"type": "string"},
        "normalized_request": {"type": "string"},
        "primary_intent": {"type": "string"},
        "secondary_intents": {"type": "array", "items": {"type": "string"}},
        "task_category": {
            "type": "string",
            "enum": [
                "simple_question",
                "academic_analysis",
                "planning",
                "transcript_processing",
                "requirement_explanation",
                "write_or_update_request",
                "multi_step_task",
                "unsupported",
            ],
        },
        "task_complexity": {"type": "string", "enum": ["low", "medium", "high"]},
        "recommended_autonomy_level": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
        "suggested_next_layer": {
            "type": "string",
            "enum": ["deterministic_workflow", "planner", "clarification", "unsupported"],
        },
        "required_context": {"type": "array", "items": {"type": "string"}},
        "missing_context": {"type": "array", "items": {"type": "string"}},
        "extracted_entities": {"type": "object"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "requires_user_confirmation": {"type": "boolean"},
        "write_risk": {"type": "string", "enum": ["none", "possible", "explicit"]},
        "clarifying_questions": {"type": "array", "items": {"type": "string"}},
        "intent_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "overall_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "decision_summary": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status",
        "user_goal",
        "normalized_request",
        "primary_intent",
        "task_category",
        "task_complexity",
        "recommended_autonomy_level",
        "suggested_next_layer",
        "intent_confidence",
        "overall_confidence",
        "decision_summary",
    ],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Planner Agent (Phase 5) — matches `app.agent.planner.schemas.PlannerOutput`
# / `PlannerSubtask`, minus the `source` field (set by Python, never by the
# LLM). `primary_intent` and `subtask.capability_name` are intentionally
# free-form strings rather than an enum: `app.agent.planner.normalizer` is
# responsible for rejecting an unsupported intent or a hallucinated/disabled
# capability name and falling back, per the same pattern already used for
# `TASK_UNDERSTANDING_OUTPUT_SCHEMA`'s `primary_intent` — a generic
# schema-repair retry is not the right tool for that decision, since it
# requires knowledge (the `AgentIntent` enum, the live `CapabilityRegistry`)
# that isn't expressible in a static JSON schema.
# ---------------------------------------------------------------------------
PLANNER_DYNAMIC_AGENT_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spec_id": {"type": "string"},
        "agent_name": {"type": "string"},
        "role": {"type": "string"},
        "objective": {"type": "string"},
        "reasoning_pattern": {
            "type": "string",
            "enum": [
                "single_pass",
                "tool_observation_loop",
                "compare_and_synthesize",
            ],
        },
        "allowed_blocks": {"type": "array", "items": {"type": "string"}},
        "allowed_observations": {"type": "array", "items": {"type": "string"}},
        "allowed_capabilities": {"type": "array", "items": {"type": "string"}},
        "context_contract": {
            "type": "object",
            "properties": {
                "allowed_context_sections": {"type": "array", "items": {"type": "string"}},
                "required_context_sections": {"type": "array", "items": {"type": "string"}},
                "forbidden_context_keys": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "expected_output_schema_name": {"type": "string"},
        "validation_policy": {
            "type": "object",
            "properties": {
                "require_sources": {"type": "boolean"},
                "require_confidence": {"type": "boolean"},
                "allow_missing_context": {"type": "boolean"},
                "allow_proposed_actions": {"type": "boolean"},
                "allow_writes": {"type": "boolean"},
                "require_output_schema": {"type": "boolean"},
                "max_output_chars": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "budget": {
            "type": "object",
            "properties": {
                "max_reasoning_calls": {"type": "integer"},
                "max_tool_rounds": {"type": "integer"},
                "max_observations": {"type": "integer"},
                "max_validation_passes": {"type": "integer"},
                "max_runtime_ms": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "boundaries": {"type": "array", "items": {"type": "string"}},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "shadow_only": {"type": "boolean"},
    },
    "required": [
        "spec_id",
        "agent_name",
        "role",
        "objective",
        "reasoning_pattern",
        "expected_output_schema_name",
        "shadow_only",
    ],
    "additionalProperties": False,
}

PLANNER_SUBTASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": [
                "understand",
                "retrieve_context",
                "analyze",
                "simulate",
                "validate",
                "compose",
                "propose_action",
                "clarify",
            ],
        },
        "capability_name": {"type": "string"},
        "objective": {"type": "string"},
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "required_context_sections": {"type": "array", "items": {"type": "string"}},
        "expected_output_schema_name": {"type": ["string", "null"]},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "validation_requirements": {"type": "array", "items": {"type": "string"}},
        "can_run_in_parallel_group": {"type": ["string", "null"]},
        "requires_user_confirmation": {"type": "boolean"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "dynamic_agent_spec": PLANNER_DYNAMIC_AGENT_SPEC_SCHEMA,
    },
    "required": ["id", "title", "kind", "capability_name", "objective"],
    "additionalProperties": False,
}

PLANNER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "needs_more_context", "unsupported", "failed"],
        },
        "plan_id": {"type": "string"},
        "user_goal": {"type": "string"},
        "execution_mode": {
            "type": "string",
            "enum": [
                "deterministic_workflow",
                "single_capability",
                "multi_capability_graph",
                "clarification",
                "unsupported",
            ],
        },
        "recommended_autonomy_level": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
        "primary_intent": {"type": "string"},
        "subtasks": {"type": "array", "items": PLANNER_SUBTASK_SCHEMA},
        "required_context": {"type": "array", "items": {"type": "string"}},
        "missing_context": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "requires_user_confirmation": {"type": "boolean"},
        "write_risk": {"type": "string", "enum": ["none", "possible", "explicit"]},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "validation_strategy": {"type": "array", "items": {"type": "string"}},
        "fallback_workflow_name": {"type": ["string", "null"]},
        "decision_summary": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": [
        "status",
        "plan_id",
        "user_goal",
        "execution_mode",
        "recommended_autonomy_level",
        "primary_intent",
        "decision_summary",
        "confidence",
    ],
    "additionalProperties": False,
}

PLANNER_REPAIR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": [
                "repaired",
                "regenerated",
                "continued",
                "clarification_needed",
                "aborted_safely",
                "failed",
                "skipped",
            ],
        },
        "mode_used": {
            "type": "string",
            "enum": ["repair", "regenerate", "continue", "clarify_first", "abort_safely"],
        },
        "plan_id": {"type": ["string", "null"]},
        "repaired_plan": {"type": ["object", "null"]},
        "preserved_subtask_ids": {"type": "array", "items": {"type": "string"}},
        "revised_subtask_ids": {"type": "array", "items": {"type": "string"}},
        "removed_subtask_ids": {"type": "array", "items": {"type": "string"}},
        "added_subtask_ids": {"type": "array", "items": {"type": "string"}},
        "decision_summary": {"type": "string"},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "safe_to_use": {"type": "boolean"},
    },
    "required": ["status", "mode_used", "decision_summary", "confidence", "safe_to_use"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Phase 10 — read-only specialist agents. All three share the exact same
# shape (matching `app.agent.specialists.schemas.SpecialistAgentOutput` minus
# `agent_name`/`subtask_id`, set by Python, and minus `proposed_actions`,
# which the LLM is never asked to populate at all — the model's own field
# validator forces it to `[]` unconditionally regardless).
# ---------------------------------------------------------------------------


def _specialist_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["completed", "needs_more_context", "unsupported", "failed"],
            },
            "result": {"type": "object"},
            "decision_summary": {"type": "string"},
            "key_findings": {"type": "array", "items": {"type": "string"}},
            "missing_context": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "validation_notes": {"type": "array", "items": {"type": "string"}},
            "sources": {"type": "array", "items": {"type": "object"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["status", "decision_summary", "confidence"],
        "additionalProperties": False,
    }


SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA: dict[str, Any] = _specialist_output_schema()
SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA: dict[str, Any] = _specialist_output_schema()
SPECIALIST_REQUIREMENT_EXPLANATION_OUTPUT_SCHEMA: dict[str, Any] = _specialist_output_schema()

SYNTHESIS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": [
                "candidate_ready",
                "candidate_ready_with_warnings",
                "needs_clarification",
                "insufficient_evidence",
                "unsafe",
                "failed",
                "skipped",
            ],
        },
        "candidate_answer_text": {"type": ["string", "null"]},
        "decision_summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
        "evidence_used_ids": {"type": "array", "items": {"type": "string"}},
        "evidence_excluded_ids": {"type": "array", "items": {"type": "string"}},
        "safe_to_show": {"type": "boolean"},
        "safe_to_promote": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "decision_summary", "confidence", "safe_to_show", "safe_to_promote"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Dynamic Agent (Phase 15) — matches `app.agent.dynamic_agents.schemas.DynamicAgentRunOutput`
# minus `spec_id`/`agent_name` (set by Python) and minus `proposed_actions`
# (forced to `[]` by the model validator, never populated by the LLM schema).
# ---------------------------------------------------------------------------
DYNAMIC_AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "needs_more_context", "unsupported", "failed"],
        },
        "result": {"type": "object"},
        "decision_summary": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "missing_context": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "validation_notes": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "object"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["status", "decision_summary", "confidence"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Final answer judge (eval-only) — compares agent final answer to golden facts.
# ---------------------------------------------------------------------------
FINAL_ANSWER_JUDGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "fact_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["present", "partial", "missing", "contradicted"],
                    },
                    "evidence_excerpt": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["fact", "status"],
                "additionalProperties": False,
            },
        },
        "hallucination_warnings": {"type": "array", "items": {"type": "string"}},
        "source_warnings": {"type": "array", "items": {"type": "string"}},
        "overall_verdict": {
            "type": "string",
            "enum": ["passed", "partial", "failed"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["status", "fact_results", "overall_verdict", "confidence"],
    "additionalProperties": False,
}
