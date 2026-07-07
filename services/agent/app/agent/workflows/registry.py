"""Workflow registry for the agent orchestrator."""

from __future__ import annotations

from app.agent.workflows.base import AgentWorkflow
from app.agent.workflows.semester_planning_workflow import SemesterPlanningWorkflow
from app.agent.workflows.transcript_import_workflow import TranscriptImportWorkflow
from app.agent.workflows.course_question_workflow import CourseQuestionWorkflow
from app.agent.workflows.general_academic_workflow import GeneralAcademicWorkflow
from app.agent.workflows.requirement_explanation_workflow import RequirementExplanationWorkflow
from app.agent.workflows.graduation_progress_workflow import GraduationProgressWorkflow

_GENERAL = GeneralAcademicWorkflow()
_GRADUATION = GraduationProgressWorkflow()
_COURSE_QUESTION = CourseQuestionWorkflow()
_TRANSCRIPT = TranscriptImportWorkflow()
_PLANNING = SemesterPlanningWorkflow()
_REQUIREMENT = RequirementExplanationWorkflow()

_REGISTRY: dict[str, AgentWorkflow] = {
    _GENERAL.name: _GENERAL,
    _GRADUATION.name: _GRADUATION,
    _COURSE_QUESTION.name: _COURSE_QUESTION,
    _TRANSCRIPT.name: _TRANSCRIPT,
    _PLANNING.name: _PLANNING,
    _REQUIREMENT.name: _REQUIREMENT,
    "course_question_workflow": _COURSE_QUESTION,
    "transcript_import_workflow": _TRANSCRIPT,
    "semester_planning_workflow": _PLANNING,
    "requirement_explanation_workflow": _REQUIREMENT,
}


def get_workflow(name: str) -> AgentWorkflow:
    return _REGISTRY.get(name, _GENERAL)
