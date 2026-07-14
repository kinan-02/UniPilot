"""Conditional critic selection (docs/planning/ADAPTIVE_PLANNING_EXTRACTION_PLAN.md
§3.2).

Owns the critic *vocabulary* (the six names + the palette) and the
deterministic policy that activates a SUBSET of it per invocation. The whole
point: the palette grew 4 -> 6, but per-turn critic cost drops because we run
the one or two critics the signals point at instead of all of them.

Deterministic on purpose (reference doc §5/§11): no LLM call is spent deciding
which LLM critics to run. Selection is driven by the validator's findings plus
signals already on the invocation input (replan state, understanding
confidence, and cheap keyword scans of the goal/sub_asks/draft objectives).

`planner_council` imports the name constants from here (one-directional -- this
module imports nothing from the council), so there is a single owner of "what
critics exist."
"""

from __future__ import annotations

import re

from app.agent_core.planning.plan_validator import (
    F_CYCLE,
    F_DANGLING,
    F_DUP_OBJECTIVE,
    F_EMPTY_CRITERIA,
    F_OVER_DECOMPOSED,
    F_UNADDRESSED_SUBASK,
    ValidatorReport,
)
from app.agent_core.planning.schemas import PlannerInvocationInput

COVERAGE_CRITIC_V1 = "planner_coverage_critic_v1"
GROUNDING_CRITIC_V1 = "planner_grounding_critic_v1"
CRITERIA_CRITIC_V1 = "planner_criteria_critic_v1"
PARSIMONY_CRITIC_V1 = "planner_parsimony_critic_v1"
STRATEGY_CRITIC_V1 = "planner_strategy_critic_v1"
DOMAIN_CRITIC_V1 = "planner_domain_critic_v1"

# Canonical order -- also the tie-break order when two critics share a priority.
CRITIC_PALETTE: tuple[str, ...] = (
    COVERAGE_CRITIC_V1,
    CRITERIA_CRITIC_V1,
    DOMAIN_CRITIC_V1,
    GROUNDING_CRITIC_V1,
    PARSIMONY_CRITIC_V1,
    STRATEGY_CRITIC_V1,
)

_DEFAULT_MAX_ACTIVE = 2
# A plan this long is a strategy smell even absent other signals.
_HIGH_STEP_COUNT = 5
# Below this understanding confidence, challenge the whole approach.
_LOW_CONFIDENCE = 0.8

_GROUNDING_KEYWORDS = frozenset(
    {"profile", "gpa", "transcript", "completed", "credit", "credits", "semester", "enrolled", "grade", "standing"}
)
_DOMAIN_KEYWORDS = frozenset(
    {"prerequisite", "prereq", "prerequisites", "eligib", "degree", "graduat", "track", "requirement",
     "requirements", "catalog", "bucket", "mandatory", "elective"}
)
_COURSE_CODE = re.compile(r"\b\d{5,8}\b")
_CRITERIA_REASON_MARKERS = ("criteri", "unmet", "success")


def _corpus(planner_input: PlannerInvocationInput, draft_objectives: list[str]) -> str:
    parts = [planner_input.user_goal, *planner_input.sub_asks, *planner_input.constraints, *draft_objectives]
    return " ".join(parts).lower()


def _has_keyword(corpus: str, keywords: frozenset[str]) -> bool:
    return any(word in corpus for word in keywords)


def select_critics(
    *,
    invocation: int,
    planner_input: PlannerInvocationInput,
    report: ValidatorReport,
    draft_objectives: list[str],
    palette: tuple[str, ...] = CRITIC_PALETTE,
    max_active: int = _DEFAULT_MAX_ACTIVE,
) -> tuple[str, ...]:
    """Pick the critics to run this invocation. Returns an ordered, deduped,
    capped subset of `palette`. Only ever called on the first invocation or a
    replan (the council's outer gate handles routine continuations), so the
    two special cases below -- the first-invocation floor and the replan cap
    bump -- are disjoint and cover both entry paths."""
    codes = report.codes()
    corpus = _corpus(planner_input, draft_objectives)
    replan = bool(planner_input.monitor_flags or planner_input.replan_reason)
    reason = (planner_input.replan_reason or "").lower()

    # (critic, priority) candidates; higher priority wins a tie for a cap slot.
    candidates: list[tuple[str, int]] = []
    if {F_DANGLING, F_CYCLE, F_UNADDRESSED_SUBASK} & codes:
        candidates.append((COVERAGE_CRITIC_V1, 5))
    if any(marker in reason for marker in _CRITERIA_REASON_MARKERS):
        candidates.append((CRITERIA_CRITIC_V1, 5))
    elif F_EMPTY_CRITERIA in codes:
        candidates.append((CRITERIA_CRITIC_V1, 4))
    if {F_DUP_OBJECTIVE, F_OVER_DECOMPOSED} & codes:
        candidates.append((PARSIMONY_CRITIC_V1, 3))
    if _has_keyword(corpus, _DOMAIN_KEYWORDS):
        candidates.append((DOMAIN_CRITIC_V1, 4))
    if _has_keyword(corpus, _GROUNDING_KEYWORDS) or _COURSE_CODE.search(corpus):
        candidates.append((GROUNDING_CRITIC_V1, 3))
    if replan:
        candidates.append((STRATEGY_CRITIC_V1, 4))
    elif planner_input.confidence < _LOW_CONFIDENCE:
        candidates.append((STRATEGY_CRITIC_V1, 3))
    elif len(draft_objectives) >= _HIGH_STEP_COUNT:
        candidates.append((STRATEGY_CRITIC_V1, 2))

    # Keep the highest priority seen per critic, restricted to the palette.
    best: dict[str, int] = {}
    for critic, priority in candidates:
        if critic in palette and priority > best.get(critic, -1):
            best[critic] = priority

    cap = max_active + (1 if replan else 0)
    palette_index = {name: idx for idx, name in enumerate(palette)}
    ranked = sorted(best, key=lambda critic: (-best[critic], palette_index[critic]))
    selected = tuple(ranked[:cap])

    # Floor: the first invocation sets the plan's whole shape, so never leave
    # it unreviewed -- fall back to the two most universally useful checks.
    if invocation <= 1 and not selected:
        selected = tuple(c for c in (COVERAGE_CRITIC_V1, PARSIMONY_CRITIC_V1) if c in palette)
    return selected


__all__ = [
    "COVERAGE_CRITIC_V1",
    "GROUNDING_CRITIC_V1",
    "CRITERIA_CRITIC_V1",
    "PARSIMONY_CRITIC_V1",
    "STRATEGY_CRITIC_V1",
    "DOMAIN_CRITIC_V1",
    "CRITIC_PALETTE",
    "select_critics",
]
