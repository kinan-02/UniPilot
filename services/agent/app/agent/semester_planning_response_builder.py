"""Structured blocks for semester planning responses (Agent_UI_UX.md §21)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentContextPack, ProposedAction, StructuredBlock
from app.services.semester_planning_client import SemesterPlanningResult, SemesterPlanOption


def build_semester_planning_blocks(
    *,
    context: AgentContextPack,
    result: SemesterPlanningResult,
    proposed_actions: list[ProposedAction],
) -> list[StructuredBlock]:
    blocks: list[StructuredBlock] = [
        StructuredBlock(
            type="SemesterPlanOptionsBlock",
            data={
                "semesterCode": result.semesterCode,
                "options": [_option_payload(option, actions=proposed_actions) for option in result.options],
                "assumptions": result.assumptions,
                "warnings": result.warnings,
            },
        ),
        StructuredBlock(
            type="SchedulePreviewBlock",
            data={
                "semesterCode": result.semesterCode,
                "previews": [
                    {
                        "optionId": option.optionId,
                        "label": option.label,
                        "selections": option.scheduleSelections,
                        "examSummary": option.examSummary,
                        "skippedCourses": option.skippedCourses,
                    }
                    for option in result.options
                ],
            },
        ),
        _source_summary_block(context=context, result=result),
    ]

    if proposed_actions:
        primary = proposed_actions[0]
        blocks.insert(
            1,
            StructuredBlock(
                type="ConfirmationBlock",
                data={
                    "title": "Save a semester plan",
                    "description": (
                        "Review the options below, then confirm to save your chosen plan as a draft. "
                        "Nothing is saved until you confirm."
                    ),
                    "actionType": "save_semester_plan",
                    "requiresConfirmation": True,
                    "availableActions": [
                        {
                            "optionId": action.payload.get("optionId"),
                            "actionId": action.id,
                            "label": action.label,
                        }
                        for action in proposed_actions
                    ],
                    "confirmLabel": "Save selected plan",
                    "cancelLabel": "Keep browsing",
                },
            ),
        )

    for warning in result.warnings[:4]:
        blocks.append(StructuredBlock(type="WarningBlock", data={"message": warning}))

    return blocks


def build_semester_planning_text(*, result: SemesterPlanningResult) -> str:
    if result.status != "ok" or not result.options:
        if result.errors:
            return result.errors[0]
        return "I could not generate semester plan options right now."

    count = len(result.options)
    semester = result.semesterCode or "the target semester"
    parts = [
        f"I generated {count} semester plan option(s) for {semester}.",
        "Each option respects your profile, completed courses, offerings, and credit limits.",
        "Choose an option and confirm to save it as a draft plan.",
    ]
    if result.assumptions:
        parts.append(f"Assumptions: {'; '.join(result.assumptions[:2])}.")
    return " ".join(parts)


def build_semester_planning_followups(*, result: SemesterPlanningResult) -> list[str]:
    semester = result.semesterCode or "next semester"
    return [
        f"Make the {semester} plan lighter",
        "What am I missing to graduate?",
        f"Remove Friday classes from option A",
    ]


def build_plan_saved_text(*, plan_name: str | None, semester_code: str | None) -> str:
    label = plan_name or "Semester plan"
    semester = semester_code or "your semester"
    return f'Saved "{label}" as a draft plan for {semester}. You can refine groups and schedule in the planner.'


def _option_payload(
    option: SemesterPlanOption,
    *,
    actions: list[ProposedAction],
) -> dict[str, Any]:
    action_id = next(
        (action.id for action in actions if action.payload.get("optionId") == option.optionId),
        None,
    )
    return {
        **option.model_dump(),
        "actionId": action_id,
    }


def _source_summary_block(
    *,
    context: AgentContextPack,
    result: SemesterPlanningResult,
) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "provenance": context.provenance,
            "validationStatus": context.validation.status,
            "semesterCode": result.semesterCode,
            "optionCount": len(result.options),
            "usedSources": list(context.provenance) if context.provenance else [
                "mongodb:student_profile",
                "mongodb:completed_courses",
                "catalog:degree_requirements",
                "catalog:course_offerings",
                "planner:semester_suggestions",
            ],
        },
    )
