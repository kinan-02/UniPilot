"""Post-processing pipeline that turns raw LLM output into the Planner's
final output (docs/agent/PLANNER_OUTPUT_DESIGN.md §4, §5).

Kept separate from `planner.py` because this is the mechanical, code-owned
half of the Planner's work -- id rewriting, referential-integrity and
acyclicity validation, hollow-result detection, and graph derivation --
distinct from the LLM-reasoning half `planner.py` orchestrates.
"""

from __future__ import annotations

import logging

from app.agent_core.planning.schemas import PlanGraph, PlanStatus, PlanStep, PlanStepDraft

logger = logging.getLogger(__name__)


def rewrite_step_ids(
    drafts: list[PlanStepDraft],
    *,
    invocation: int,
    known_global_ids: set[str],
) -> list[PlanStep]:
    """Turn one invocation's raw `PlanStepDraft` batch into final `PlanStep`s
    (PLANNER_OUTPUT_DESIGN.md §4, points 1-3, 5).

    `step_id` is never trusted from the LLM directly: local labels ("A",
    "B", ...) are rewritten into ids unique across the plan's whole
    lifetime (`f"{invocation}{label}"`). `depends_on` entries are resolved
    the same pass -- a local label is translated, anything else is assumed
    to already be a real global id the model copied from what it was shown
    of `plan_graph_so_far` and is left as-is.

    A `depends_on` entry that resolves to neither a step in this batch nor
    `known_global_ids` is a hallucinated dependency -- dropped with a
    warning, not treated as fatal. Under-declaring a real dependency is
    unrecoverable downstream (§6); over-declaring a fake one is safely
    recoverable by stripping it, so nothing here ever *adds* an edge.

    Global id uniqueness is a hard invariant enforced here, not trusted to
    the model's own labeling discipline: two distinct local labels that
    collide after lowercasing (e.g. "A" and "a"), or the model reusing the
    same local label for two different drafts, would otherwise silently
    collapse two steps into one identical `step_id` -- corrupting every
    dict downstream that's keyed by step_id (`compute_plan_graph`'s
    `forward`/`dependents`, cross-invocation `plan_graph_so_far` lookups).
    A collision is disambiguated with a numeric suffix and logged, never
    silently merged or dropped.
    """
    local_to_global: dict[str, str] = {}
    seen_global_ids: set[str] = set()
    draft_global_ids: list[str] = []
    for draft in drafts:
        candidate = f"{invocation}{draft.step_id.lower()}"
        global_id = candidate
        suffix = 2
        while global_id in seen_global_ids:
            logger.warning(
                "planner_step_id_collision: local label %r produced a duplicate global id %r "
                "-- disambiguated to %r",
                draft.step_id,
                candidate,
                f"{candidate}-{suffix}",
            )
            global_id = f"{candidate}-{suffix}"
            suffix += 1
        seen_global_ids.add(global_id)
        local_to_global[draft.step_id] = global_id  # last-seen wins if a label is reused
        draft_global_ids.append(global_id)

    batch_global_ids = seen_global_ids

    steps: list[PlanStep] = []
    for draft, global_id in zip(drafts, draft_global_ids):
        resolved_depends_on: list[str] = []
        for dep in draft.depends_on:
            resolved = local_to_global.get(dep, dep)
            if resolved not in batch_global_ids and resolved not in known_global_ids:
                logger.warning(
                    "planner_dangling_dependency: step %s declared dependency %s, not found "
                    "in this batch or accumulated state -- dropped",
                    global_id,
                    dep,
                )
                continue
            if resolved not in resolved_depends_on:
                resolved_depends_on.append(resolved)
        steps.append(
            PlanStep(
                step_id=global_id,
                objective=draft.objective,
                depends_on=resolved_depends_on,
                success_criteria=draft.success_criteria,
                assumptions_to_verify=draft.assumptions_to_verify,
            )
        )

    return _break_cycles(steps, batch_global_ids=batch_global_ids)


def _break_cycles(steps: list[PlanStep], *, batch_global_ids: set[str]) -> list[PlanStep]:
    """DFS cycle check over just this batch's local edges -- a dependency
    pointing outside the batch can never participate in a same-batch cycle
    by construction (it already existed before this batch was produced).
    A cycle is broken by dropping the back-edge that closes it, not by
    rejecting the whole invocation -- the same "strip, don't reject"
    judgment as the dangling-reference case above."""
    by_id = {step.step_id: step for step in steps}
    depends_on_by_id = {step.step_id: list(step.depends_on) for step in steps}

    white, gray, black = 0, 1, 2
    color = {step_id: white for step_id in by_id}

    def visit(step_id: str) -> None:
        color[step_id] = gray
        for dep in list(depends_on_by_id[step_id]):
            if dep not in batch_global_ids:
                continue
            if color[dep] == gray:
                logger.warning(
                    "planner_cycle_broken: dropped dependency %s from step %s to break a cycle",
                    dep,
                    step_id,
                )
                depends_on_by_id[step_id].remove(dep)
            elif color[dep] == white:
                visit(dep)
        color[step_id] = black

    for step_id in by_id:
        if color[step_id] == white:
            visit(step_id)

    return [by_id[step_id].model_copy(update={"depends_on": depends_on_by_id[step_id]}) for step_id in by_id]


def check_hollow_result(
    plan_status: PlanStatus,
    next_steps: list[PlanStep],
    clarification_question: str | None,
) -> bool:
    """A schema-valid but semantically empty result (PLANNER_OUTPUT_DESIGN.md
    §4 point 4): `in_progress` with no steps, or `blocked_needs_clarification`
    with no question to ask. Callers should treat a `True` result as a
    reasoning failure, not a valid output -- the same discipline already
    applied to Request Understanding's hollow-result checks."""
    if plan_status == "in_progress" and not next_steps:
        return True
    if plan_status == "blocked_needs_clarification" and not clarification_question:
        return True
    return False


def compute_plan_graph(steps: list[PlanStep]) -> PlanGraph:
    """Derive this invocation's own delta graph from validated `PlanStep`s
    (PLANNER_OUTPUT_DESIGN.md §5). Scoped to `steps` only -- never the whole
    plan; `PlanExecutionState.merge_plan_graph` accumulates deltas across
    invocations."""
    forward: dict[str, list[str]] = {}
    dependents: dict[str, list[str]] = {}
    batch_ids = {step.step_id for step in steps}

    for step in steps:
        forward[step.step_id] = list(step.depends_on)
        dependents.setdefault(step.step_id, [])
        for dep in step.depends_on:
            dependents.setdefault(dep, []).append(step.step_id)

    return PlanGraph(
        forward=forward,
        dependents=dependents,
        execution_layers=_compute_execution_layers(steps, batch_ids=batch_ids),
    )


def _compute_execution_layers(steps: list[PlanStep], *, batch_ids: set[str]) -> list[list[str]]:
    """Topological layering over just this batch. Any `depends_on` target
    outside the batch is treated as already-satisfied -- it must be a
    completed prior-invocation step by construction, so it can't constrain
    layering within this delta."""
    remaining = {step.step_id: {dep for dep in step.depends_on if dep in batch_ids} for step in steps}
    layers: list[list[str]] = []

    while remaining:
        ready = sorted(step_id for step_id, deps in remaining.items() if not deps)
        if not ready:
            # Shouldn't happen once `_break_cycles` has run, but never hang.
            logger.warning("planner_layering_stuck: forcing remaining steps %s into one layer", sorted(remaining))
            ready = sorted(remaining)
        layers.append(ready)
        for step_id in ready:
            del remaining[step_id]
        for deps in remaining.values():
            deps.difference_update(ready)

    return layers


__all__ = ["rewrite_step_ids", "check_hollow_result", "compute_plan_graph"]
