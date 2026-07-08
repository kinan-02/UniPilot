"""Task Understanding Agent.

Produces a richer, structured understanding of a student's request via the
shared `ReasoningBlock` runtime. Live and authoritative: `run_task_understanding`
(integration.py) feeds workflow dispatch. Importing this package has no side
effects.
"""

from __future__ import annotations

from app.agent.task_understanding.agent import (
    build_deterministic_task_understanding_fallback,
    understand_user_task,
)
from app.agent.task_understanding.integration import (
    build_task_understanding_diagnostic_summary,
    run_task_understanding,
    to_intent_classification,
)
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
    "build_deterministic_task_understanding_fallback",
    "run_task_understanding",
    "build_task_understanding_diagnostic_summary",
    "to_intent_classification",
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
