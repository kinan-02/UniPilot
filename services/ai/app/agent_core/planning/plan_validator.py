"""Deterministic validator gate (docs/planning/ADAPTIVE_PLANNING_EXTRACTION_PLAN.md
§2).

A pure, read-only reporter run on a DRAFT batch (`PlanStepDraft`s with local
labels) BEFORE the critics. It never mutates and never blocks: `rewrite.py`
remains the authoritative repairer (it silently strips dangling edges and
breaks cycles when the council's output is finalized). This module's job is
to surface those same structural facts -- plus a few cheap lexical heuristics
-- EARLY, as structured findings, so the council can pick WHICH critics to run
(W2) instead of always running all of them.

Scope note: our `PlanStep` is deliberately schema-light (objective +
depends_on + success_criteria, no typed I/O schemas or capability/tool
binding). So the reference architecture's schema-compatibility and
capability-existence checks do not apply here -- reintroducing them would
reverse the specialist-router decision. Every check below operates only on
what our model actually carries: graph structure and objective/criteria text.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStepDraft

Severity = Literal["structural", "efficiency", "quality", "coverage"]

# Finding codes -- kept as plain string constants (mirrored in the W2 selector).
F_DANGLING = "F_DANGLING"
F_CYCLE = "F_CYCLE"
F_DUP_OBJECTIVE = "F_DUP_OBJECTIVE"
F_EMPTY_CRITERIA = "F_EMPTY_CRITERIA"
F_UNADDRESSED_SUBASK = "F_UNADDRESSED_SUBASK"

# Two objectives this lexically similar are treated as the same fact.
_DUP_OBJECTIVE_JACCARD = 0.8
# Tokens shorter than this are dropped as non-content (articles, "of", "to").
_MIN_CONTENT_TOKEN_LEN = 3


class ValidatorFinding(BaseModel):
    """One advisory finding. `step_ids` are the LOCAL draft labels involved
    (empty for a plan-wide finding like an unaddressed sub_ask)."""

    code: str
    severity: Severity
    step_ids: list[str] = Field(default_factory=list)
    detail: str


class ValidatorReport(BaseModel):
    """Bundle of findings for one draft batch. Advisory only -- callers route
    critics off `codes()`, never treat a finding as a hard failure."""

    findings: list[ValidatorFinding] = Field(default_factory=list)

    def codes(self) -> set[str]:
        return {finding.code for finding in self.findings}


def _tokenize(text: str) -> set[str]:
    """Content tokens: lowercased alphanumeric runs of at least
    `_MIN_CONTENT_TOKEN_LEN` chars. Cheap and deterministic -- no stemming."""
    return {tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if len(tok) >= _MIN_CONTENT_TOKEN_LEN}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _find_dangling(drafts: list[PlanStepDraft], *, local_ids: set[str], known_global_ids: set[str]) -> list[ValidatorFinding]:
    """A depends_on entry that names neither a batch sibling (local label) nor
    an already-completed prior-invocation step (known global id). Faithful,
    local-level mirror of what `rewrite.rewrite_step_ids` would silently drop."""
    findings: list[ValidatorFinding] = []
    for draft in drafts:
        for dep in draft.depends_on:
            if dep not in local_ids and dep not in known_global_ids:
                findings.append(
                    ValidatorFinding(
                        code=F_DANGLING,
                        severity="structural",
                        step_ids=[draft.step_id],
                        detail=f"step {draft.step_id} depends on {dep!r}, which is not a sibling or a known prior step",
                    )
                )
    return findings


def _find_cycles(drafts: list[PlanStepDraft], *, local_ids: set[str]) -> list[ValidatorFinding]:
    """DFS over sibling-only edges; a back-edge to a gray node closes a cycle.
    Read-only mirror of `rewrite._break_cycles` (which strips the back-edge)."""
    adjacency = {draft.step_id: [dep for dep in draft.depends_on if dep in local_ids] for draft in drafts}
    white, gray, black = 0, 1, 2
    color = {step_id: white for step_id in adjacency}
    findings: list[ValidatorFinding] = []

    def visit(step_id: str) -> None:
        color[step_id] = gray
        for dep in adjacency[step_id]:
            if color[dep] == gray:
                findings.append(
                    ValidatorFinding(
                        code=F_CYCLE,
                        severity="structural",
                        step_ids=[step_id, dep],
                        detail=f"dependency {step_id} -> {dep} closes a cycle",
                    )
                )
            elif color[dep] == white:
                visit(dep)
        color[step_id] = black

    for step_id in adjacency:
        if color[step_id] == white:
            visit(step_id)
    return findings


def _find_duplicate_objectives(drafts: list[PlanStepDraft]) -> list[ValidatorFinding]:
    findings: list[ValidatorFinding] = []
    tokenized = [(draft.step_id, _tokenize(draft.objective)) for draft in drafts]
    for i in range(len(tokenized)):
        for j in range(i + 1, len(tokenized)):
            (id_a, toks_a), (id_b, toks_b) = tokenized[i], tokenized[j]
            if toks_a and _jaccard(toks_a, toks_b) >= _DUP_OBJECTIVE_JACCARD:
                findings.append(
                    ValidatorFinding(
                        code=F_DUP_OBJECTIVE,
                        severity="efficiency",
                        step_ids=[id_a, id_b],
                        detail=f"steps {id_a} and {id_b} have near-identical objectives; one should depend on the other",
                    )
                )
    return findings


def _find_empty_criteria(drafts: list[PlanStepDraft]) -> list[ValidatorFinding]:
    return [
        ValidatorFinding(
            code=F_EMPTY_CRITERIA,
            severity="quality",
            step_ids=[draft.step_id],
            detail=f"step {draft.step_id} has no success_criteria; the Monitor cannot verify it",
        )
        for draft in drafts
        if not draft.success_criteria
    ]


def _find_unaddressed_subasks(drafts: list[PlanStepDraft], planner_input: PlannerInvocationInput) -> list[ValidatorFinding]:
    """A sub_ask that shares ZERO content tokens with any step objective --
    deliberately a strict, zero-overlap signal (a weak coverage smell), so it
    fires only when a sub_ask is wholly disjoint from the whole plan."""
    if not planner_input.sub_asks:
        return []
    objective_tokens: set[str] = set()
    for draft in drafts:
        objective_tokens |= _tokenize(draft.objective)
    findings: list[ValidatorFinding] = []
    for sub_ask in planner_input.sub_asks:
        sub_tokens = _tokenize(sub_ask)
        if sub_tokens and not (sub_tokens & objective_tokens):
            findings.append(
                ValidatorFinding(
                    code=F_UNADDRESSED_SUBASK,
                    severity="coverage",
                    step_ids=[],
                    detail=f"sub_ask {sub_ask!r} shares no content with any step objective",
                )
            )
    return findings


def validate_plan_draft(
    drafts: list[PlanStepDraft],
    *,
    known_global_ids: set[str],
    planner_input: PlannerInvocationInput,
) -> ValidatorReport:
    """Run every deterministic check over one draft batch and bundle the
    advisory findings. Never mutates the drafts; never raises on empty input."""
    local_ids = {draft.step_id for draft in drafts}
    findings: list[ValidatorFinding] = []
    findings.extend(_find_dangling(drafts, local_ids=local_ids, known_global_ids=known_global_ids))
    findings.extend(_find_cycles(drafts, local_ids=local_ids))
    findings.extend(_find_duplicate_objectives(drafts))
    findings.extend(_find_empty_criteria(drafts))
    findings.extend(_find_unaddressed_subasks(drafts, planner_input))
    return ValidatorReport(findings=findings)


__all__ = [
    "F_DANGLING",
    "F_CYCLE",
    "F_DUP_OBJECTIVE",
    "F_EMPTY_CRITERIA",
    "F_UNADDRESSED_SUBASK",
    "Severity",
    "ValidatorFinding",
    "ValidatorReport",
    "validate_plan_draft",
]
