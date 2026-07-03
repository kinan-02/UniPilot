"""Map classified intent to workflow execution plan (spec §9)."""

from __future__ import annotations

from app.agent.schemas import AgentIntent, IntentClassification, TaskPlan

_WORKFLOW_BY_INTENT: dict[AgentIntent, str] = {
    "graduation_progress_check": "graduation_progress_workflow",
    "transcript_import": "transcript_import_workflow",
    "semester_plan_generation": "semester_planning_workflow",
    "semester_plan_modification": "semester_planning_workflow",
    "course_question": "course_question_workflow",
    "requirement_explanation": "requirement_explanation_workflow",
    "prerequisite_check": "course_question_workflow",
    "catalog_search": "general_academic_workflow",
    "completed_courses_update": "transcript_import_workflow",
    "profile_update": "general_academic_workflow",
    "general_academic_question": "general_academic_workflow",
    "unknown_or_unsupported": "general_academic_workflow",
}

_WRITE_INTENTS: frozenset[AgentIntent] = frozenset(
    {
        "transcript_import",
        "semester_plan_generation",
        "semester_plan_modification",
        "completed_courses_update",
        "profile_update",
    }
)


def build_task_plan(classification: IntentClassification) -> TaskPlan:
    workflow = _WORKFLOW_BY_INTENT.get(classification.intent, "general_academic_workflow")
    read_only = classification.intent not in _WRITE_INTENTS
    return TaskPlan(
        workflow=workflow,
        read_only=read_only,
        requires_confirmation=classification.requires_confirmation or not read_only,
        data_needs={"mongo": list(classification.required_context)},
        services=_services_for_intent(classification.intent),
    )


def _services_for_intent(intent: AgentIntent) -> list[str]:
    mapping: dict[AgentIntent, list[str]] = {
        "graduation_progress_check": [
            "GraduationAuditService",
            "RequirementMatchingService",
        ],
        "course_question": [
            "CourseCatalogService",
            "CourseOfferingService",
            "PrerequisiteValidationService",
        ],
        "semester_plan_generation": [
            "SemesterPlanService",
            "ScheduleConflictService",
        ],
        "semester_plan_modification": [
            "SemesterPlanService",
            "ScheduleConflictService",
        ],
        "requirement_explanation": [
            "GraduationAuditService",
            "RequirementMatchingService",
        ],
        "transcript_import": ["TranscriptParserService"],
    }
    return list(mapping.get(intent, []))
