"""Goal Analyst LLM layer — natural language to GoalSpec."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.llm.structured_output import invoke_structured_model
from app.orchestrator.artifacts import GoalIntent, GoalSpec
from app.services.planner_support import extract_course_codes


class _GoalSpecPayload(BaseModel):
    intent: str
    explicit_course_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ambiguity_note: str | None = None
    clarification_question: str | None = None


def analyze_goal_deterministic(goal: str, user_context: dict[str, Any]) -> GoalSpec:
    """Layer 0 — rule-based goal interpretation."""
    codes = extract_course_codes(goal)
    constraints = dict(user_context.get("constraints") or {})
    lowered = goal.lower()

    from app.services.what_if_scenario import WhatIfScenario, parse_what_if_scenario

    what_if = parse_what_if_scenario(goal)
    if what_if:
        intent = (
            GoalIntent.WHAT_IF_FAIL
            if what_if.scenario == WhatIfScenario.COURSE_FAILURE
            else GoalIntent.WHAT_IF
        )
        return GoalSpec(
            intent=intent,
            explicit_course_ids=list(what_if.failed_courses),
            constraints=constraints,
            confidence=0.9,
            what_if_scenario=what_if.scenario.value,
            raw_goal=goal,
            analysis_source="deterministic",
        )

    policy_tokens_en = (
        "regulation",
        "policy",
        "student rights",
        "appeal",
        "retake rule",
        "bureaucracy",
        "academic committee",
    )
    policy_tokens_he = ("תקנון", "נוהל", "זכויות", "ערעור", "מילואים", "פטור", "ועדה")
    if any(token in lowered for token in policy_tokens_en) or any(
        token in goal for token in policy_tokens_he
    ):
        return GoalSpec(
            intent=GoalIntent.POLICY_QA,
            constraints=constraints,
            confidence=0.9,
            raw_goal=goal,
            analysis_source="deterministic",
        )

    if codes:
        return GoalSpec(
            intent=GoalIntent.EXPLICIT_COURSES,
            explicit_course_ids=codes,
            constraints=constraints,
            confidence=0.95,
            raw_goal=goal,
            analysis_source="deterministic",
        )

    if any(token in lowered for token in ("balanced", "light load", "workload")) or any(
        token in goal for token in ("מאוזן", "עומס")
    ):
        return GoalSpec(
            intent=GoalIntent.BALANCED_LOAD,
            constraints=constraints,
            confidence=0.8,
            raw_goal=goal,
            analysis_source="deterministic",
        )

    if user_context.get("track_slug") and any(
        token in lowered for token in ("track", "specialization", "מסלול")
    ):
        return GoalSpec(
            intent=GoalIntent.TRACK_ALIGNED,
            constraints=constraints,
            confidence=0.75,
            raw_goal=goal,
            analysis_source="deterministic",
        )

    if len(goal.strip()) < 8:
        return GoalSpec(
            intent=GoalIntent.UNCLEAR,
            constraints=constraints,
            confidence=0.3,
            ambiguity_note="Goal is too short to interpret reliably.",
            clarification_question=(
                "Which semester are you planning for, and do you want specific courses "
                "or a balanced workload?"
            ),
            raw_goal=goal,
            analysis_source="deterministic",
        )

    return GoalSpec(
        intent=GoalIntent.OPEN_EXPLORATION,
        constraints=constraints,
        confidence=0.6,
        raw_goal=goal,
        analysis_source="deterministic",
    )


def _map_intent(raw: str) -> GoalIntent:
    normalized = raw.strip().lower()
    mapping = {
        "explicit_courses": GoalIntent.EXPLICIT_COURSES,
        "balanced_load": GoalIntent.BALANCED_LOAD,
        "track_aligned": GoalIntent.TRACK_ALIGNED,
        "open_exploration": GoalIntent.OPEN_EXPLORATION,
        "what_if_fail": GoalIntent.WHAT_IF_FAIL,
        "what_if": GoalIntent.WHAT_IF,
        "policy_qa": GoalIntent.POLICY_QA,
        "unclear": GoalIntent.UNCLEAR,
    }
    return mapping.get(normalized, GoalIntent.OPEN_EXPLORATION)


async def analyze_goal_with_llm(
    goal: str,
    user_context: dict[str, Any],
    settings: Settings | None = None,
) -> GoalSpec:
    """Layer 1 — LLM goal classification (deepseek-v4-pro via shared MAS client)."""
    cfg = settings or get_settings()
    deterministic = analyze_goal_deterministic(goal, user_context)

    if not cfg.llm_configured():
        return deterministic

    try:
        payload = await invoke_structured_model(
            system_prompt=(
                "You are the UniPilot Goal Analyst. Classify the student's semester planning "
                "goal into one intent: explicit_courses, balanced_load, track_aligned, "
                "open_exploration, or unclear. Extract any 8-digit Technion course codes "
                "mentioned. Never invent course codes."
            ),
            user_prompt=(
                f"Goal: {goal}\n"
                f"Track slug: {user_context.get('track_slug') or 'unknown'}\n"
                f"Constraints: {user_context.get('constraints') or {}}\n"
                "Return JSON: "
                '{"intent":"...", "explicit_course_ids":["..."], "confidence":0.0, '
                '"ambiguity_note":"...", "clarification_question":"..."}'
            ),
            model_type=_GoalSpecPayload,
            settings=cfg,
        )
        codes = extract_course_codes(goal) or payload.explicit_course_ids
        intent = _map_intent(payload.intent)
        if codes:
            intent = GoalIntent.EXPLICIT_COURSES

        return GoalSpec(
            intent=intent,
            explicit_course_ids=list(dict.fromkeys(codes)),
            constraints=dict(user_context.get("constraints") or {}),
            confidence=max(deterministic.confidence, float(payload.confidence)),
            ambiguity_note=payload.ambiguity_note or deterministic.ambiguity_note,
            clarification_question=(
                payload.clarification_question or deterministic.clarification_question
            ),
            raw_goal=goal,
            analysis_source="llm",
        )
    except Exception:  # noqa: BLE001 — fall back to deterministic layer
        return deterministic
