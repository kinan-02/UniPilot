"""Next-semester planning workflow — composable phase runner."""

from __future__ import annotations

from typing import Any

from app.agents.registry import AgentRegistry, get_default_registry
from app.config import Settings, get_settings
from app.effectors.gateway import get_effector_gateway
from app.orchestrator.artifacts import GoalIntent
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import NegotiationResult
from app.orchestrator.workflow.finalize import (
    finalize_success,
    record_best_candidate,
    relax_soft_constraints,
)
from app.orchestrator.workflow.hard_gate import run_hard_constraint_gate
from app.orchestrator.workflow.snapshot import workflow_snapshot
from app.services.graph_registry import graph_registry
from app.services.what_if_scenario import apply_what_if_scenario, parse_what_if_scenario


def needs_goal_clarification(blackboard: Blackboard) -> bool:
    goal_spec = blackboard.goal_spec
    if goal_spec is None:
        return False
    return goal_spec.confidence < 0.5 and goal_spec.intent == GoalIntent.UNCLEAR


def clarification_question(blackboard: Blackboard) -> str:
    goal_spec = blackboard.goal_spec
    if goal_spec and goal_spec.clarification_question:
        return goal_spec.clarification_question
    if goal_spec and goal_spec.ambiguity_note:
        return goal_spec.ambiguity_note
    return (
        "Could you clarify which courses or workload you want for next semester? "
        "For example: specific course numbers or a light/balanced load."
    )


async def run_planning_negotiation(
    *,
    goal: str,
    user_context: dict[str, Any],
    settings: Settings | None = None,
    registry: AgentRegistry | None = None,
    session_id: str | None = None,
    initial_transcript: list[dict[str, Any]] | None = None,
) -> NegotiationResult:
    """Run bounded Goal Analyst → Planner → critics → Arbiter → Explainer pipeline."""
    cfg = settings or get_settings()

    what_if = parse_what_if_scenario(goal)
    if what_if:
        baseline_snapshot = {
            "completed_courses": list(user_context.get("completed_courses") or []),
            "track_slug": user_context.get("track_slug"),
            "constraints": dict(user_context.get("constraints") or {}),
        }
        user_context = apply_what_if_scenario(user_context, what_if)
        user_context["what_if_baseline"] = baseline_snapshot

    engine = graph_registry.get_engine_for_user_context(user_context, cfg)
    agents = registry or get_default_registry()
    max_rounds = max(1, int(cfg.mas_max_negotiation_rounds))

    blackboard = Blackboard(
        goal=goal,
        user_context=user_context,
        settings=cfg,
        engine=engine,
        max_rounds=max_rounds,
        transcript=list(initial_transcript or []),
        session_id=session_id,
    )

    analyst_turn = await agents.goal_analyst.run(blackboard)
    blackboard.record_turn(analyst_turn)
    await workflow_snapshot(blackboard, "goal_analyst")

    if needs_goal_clarification(blackboard):
        question = clarification_question(blackboard)
        return NegotiationResult(
            status="awaiting_clarification",
            final_decision={
                "clarificationQuestion": question,
                "goalSpec": blackboard.goal_spec.model_dump() if blackboard.goal_spec else None,
            },
            transcript=blackboard.transcript,
            rounds=0,
        )

    for round_num in range(1, max_rounds + 1):
        blackboard.round = round_num
        blackboard.clear_vetoes()

        planner_turn = await agents.planner.run(blackboard)
        blackboard.record_turn(planner_turn)
        await workflow_snapshot(blackboard, f"planner_round_{round_num}")
        await get_effector_gateway().preload_academic_risk_cache(
            blackboard,
            blackboard.candidate_plans,
        )

        veto_turn = await run_hard_constraint_gate(blackboard)
        if veto_turn and veto_turn.action == "veto":
            revise_turn = await agents.planner.revise(blackboard)
            blackboard.record_turn(revise_turn)
            veto_turn = await run_hard_constraint_gate(blackboard)

        if veto_turn and veto_turn.action == "veto":
            if round_num < max_rounds:
                relax_soft_constraints(blackboard)
                continue
            break

        if not blackboard.candidate_plan or not blackboard.candidate_plan.course_ids:
            if round_num < max_rounds:
                blackboard.open_vetoes = [{"violations": ["No feasible courses in plan."]}]
                blackboard.last_veto_agent = "catalog_scout"
                continue
            return NegotiationResult(
                status="failed",
                transcript=blackboard.transcript,
                rounds=blackboard.round,
                error="No feasible courses in plan.",
            )

        record_best_candidate(blackboard)
        return await finalize_success(blackboard, agents)

    if blackboard.best_seen_plan and blackboard.best_seen_plan.course_ids and blackboard.engine is not None:
        blackboard.record_relaxation(
            "Committed best feasible plan after negotiation deadlock."
        )
        blackboard.set_candidate(blackboard.best_seen_plan)
        return await finalize_success(blackboard, agents)

    return NegotiationResult(
        status="failed",
        transcript=blackboard.transcript,
        rounds=blackboard.round,
        error="Max negotiation rounds exceeded without a feasible plan.",
    )
