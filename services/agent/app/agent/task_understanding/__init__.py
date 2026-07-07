"""Task Understanding Agent (Phase 3).

Produces a richer, structured understanding of a student's request via the
shared `ReasoningBlock` runtime. Diagnostic only: nothing in the live
orchestrator uses this output to select a workflow or alter a response.
Importing this package has no side effects.
"""

from __future__ import annotations

from app.agent.task_understanding.agent import understand_user_task
from app.agent.task_understanding.integration import run_task_understanding_dry_run
from app.agent.task_understanding.normalizer import reconcile_task_understanding_output
from app.agent.task_understanding.schemas import (
    AUTONOMY_LEVEL_DESCRIPTIONS,
    AutonomyLevel,
    SuggestedNextLayer,
    TaskCategory,
    TaskComplexity,
    TaskUnderstandingInput,
    TaskUnderstandingOutput,
    TaskUnderstandingSource,
    TaskUnderstandingStatus,
    WriteRisk,
)

__all__ = [
    "understand_user_task",
    "run_task_understanding_dry_run",
    "reconcile_task_understanding_output",
    "AUTONOMY_LEVEL_DESCRIPTIONS",
    "AutonomyLevel",
    "SuggestedNextLayer",
    "TaskCategory",
    "TaskComplexity",
    "TaskUnderstandingInput",
    "TaskUnderstandingOutput",
    "TaskUnderstandingSource",
    "TaskUnderstandingStatus",
    "WriteRisk",
]
