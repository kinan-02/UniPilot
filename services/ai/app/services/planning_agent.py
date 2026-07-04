"""Planning swarm sub-agent: graduation progress, semester plan, and risk snapshots."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.schemas.advisor import UserContextPayload

DEFAULT_MAX_PLANNING_ITERATIONS = 3


class PlanningAgentResult(BaseModel):
    status: Literal["ok", "not_found", "max_iterations", "unavailable"] = "ok"
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    sub_question: str = ""


class FinishPlanningRetrievalInput(BaseModel):
    status: Literal["ok", "not_found"] = Field(
        description="ok when planning context is sufficient; not_found when data is missing."
    )
    reasoning: str = Field(description="Why planning retrieval should stop now.")


def _max_planning_iterations() -> int:
    raw = os.environ.get("ADVISOR_MAX_PLANNING_ITERATIONS", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_MAX_PLANNING_ITERATIONS


def _planning_available(ctx: UserContextPayload) -> bool:
    envelope = ctx.planning_context or {}
    return bool(envelope.get("available"))


def _planning_block(
    intent: str,
    context: str,
    *,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "intent": intent,
        "source": "planning_agent",
        "context": context,
    }
    if facts is not None:
        block["facts"] = facts
    return block


def _build_planning_tools(
    ctx: UserContextPayload,
    state: dict[str, Any],
) -> list[StructuredTool]:
    envelope = ctx.planning_context or {}

    def get_graduation_progress_snapshot() -> str:
        graduation = envelope.get("graduation") or {}
        block = _planning_block(
            "graduation_progress",
            "Deterministic graduation progress snapshot from the API.",
            facts=graduation,
        )
        state.setdefault("blocks", []).append(block)
        return json.dumps(graduation, ensure_ascii=False)

    def get_latest_semester_plan() -> str:
        latest_plan = envelope.get("latest_plan")
        if not latest_plan:
            payload = {"status": "not_found", "message": "No stored semester plan on file."}
            block = _planning_block(
                "semester_plan",
                "No semester plan found for this student.",
                facts=payload,
            )
            state.setdefault("blocks", []).append(block)
            return json.dumps(payload, ensure_ascii=False)

        block = _planning_block(
            "semester_plan",
            "Latest stored semester plan snapshot.",
            facts=latest_plan,
        )
        state.setdefault("blocks", []).append(block)
        return json.dumps(latest_plan, ensure_ascii=False)

    def get_latest_risk_analysis() -> str:
        latest_risk = envelope.get("latest_risk")
        if not latest_risk:
            payload = {"status": "not_found", "message": "No academic risk analysis on file."}
            block = _planning_block(
                "risk_analysis",
                "No risk analysis found for this student.",
                facts=payload,
            )
            state.setdefault("blocks", []).append(block)
            return json.dumps(payload, ensure_ascii=False)

        block = _planning_block(
            "risk_analysis",
            "Latest academic risk analysis snapshot.",
            facts=latest_risk,
        )
        state.setdefault("blocks", []).append(block)
        return json.dumps(latest_risk, ensure_ascii=False)

    def finish_planning_retrieval(
        status: Literal["ok", "not_found"],
        reasoning: str,
    ) -> str:
        state["finish"] = {"status": status, "reasoning": reasoning}
        return json.dumps(state["finish"], ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=get_graduation_progress_snapshot,
            name="get_graduation_progress_snapshot",
            description=(
                "Return credits earned/required, completion percentage, and top missing requirements."
            ),
        ),
        StructuredTool.from_function(
            func=get_latest_semester_plan,
            name="get_latest_semester_plan",
            description="Return the student's latest stored semester plan (courses, credits, semester code).",
        ),
        StructuredTool.from_function(
            func=get_latest_risk_analysis,
            name="get_latest_risk_analysis",
            description="Return the latest academic risk analysis (severity counts and top risks).",
        ),
        StructuredTool.from_function(
            func=finish_planning_retrieval,
            name="finish_planning_retrieval",
            description="End planning retrieval when context is sufficient or unavailable.",
            args_schema=FinishPlanningRetrievalInput,
        ),
    ]


def run_planning_agent(
    sub_question: str,
    ctx: UserContextPayload,
    *,
    llm_factory: Any | None = None,
    max_iterations: int | None = None,
) -> PlanningAgentResult:
    """
    Planning swarm specialist: answers plan/progress/risk sub-questions using
    deterministic API snapshots embedded in user_context.planning_context.
    """
    envelope = ctx.planning_context or {}
    if not _planning_available(ctx):
        status = envelope.get("status") or "unavailable"
        return PlanningAgentResult(
            status="unavailable",
            blocks=[
                _planning_block(
                    "planning_unavailable",
                    f"Planning data unavailable ({status}). Student may need degree selection or profile.",
                    facts={"status": status},
                )
            ],
            sub_question=sub_question,
        )

    if llm_factory is None:
        from app.services.advisor_agent import _build_llm

        llm_factory = _build_llm

    limit = max_iterations or _max_planning_iterations()
    agent_state: dict[str, Any] = {"finish": None, "blocks": []}
    tools = _build_planning_tools(ctx, agent_state)
    llm = llm_factory().bind_tools(tools)
    tool_map = {tool.name: tool for tool in tools}
    steps: list[dict[str, Any]] = []

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are the UniPilot planning specialist for Technion students.\n"
                "Answer ONLY the delegated sub-question using deterministic planner snapshots.\n"
                "Tools:\n"
                "- get_graduation_progress_snapshot: degree progress and missing requirements\n"
                "- get_latest_semester_plan: stored semester plan courses and credits\n"
                "- get_latest_risk_analysis: academic risk severities and top risks\n"
                "- finish_planning_retrieval: stop when enough planning context is gathered\n\n"
                "Never invent credits, plans, or risk counts — copy numbers from tool outputs.\n"
                f"Maximum {limit} rounds."
            )
        ),
        HumanMessage(content=f"Sub-question: {sub_question}"),
    ]

    for iteration in range(1, limit + 1):
        agent_state["finish"] = None
        ai_message: AIMessage = llm.invoke(messages)
        tool_calls = getattr(ai_message, "tool_calls", None) or []

        step_record: dict[str, Any] = {
            "iteration": iteration,
            "content": ai_message.content,
            "tool_calls": [
                {"name": call["name"], "args": call.get("args", {})} for call in tool_calls
            ],
            "planning_blocks": [],
        }
        steps.append(step_record)
        messages.append(ai_message)

        if not tool_calls:
            messages.append(
                HumanMessage(
                    content="Call a planning tool or finish_planning_retrieval(status=ok)."
                )
            )
            continue

        for call in tool_calls:
            name = call["name"]
            args = call.get("args", {})
            tool_call_id = call.get("id", f"planning_{iteration}_{name}")
            tool = tool_map.get(name)
            if not tool:
                tool_output = json.dumps({"error": f"Unknown tool {name}"})
            else:
                tool_output = tool.invoke(args)

            if name in {
                "get_graduation_progress_snapshot",
                "get_latest_semester_plan",
                "get_latest_risk_analysis",
            }:
                new_blocks = agent_state.get("blocks", [])[-1:]
                step_record["planning_blocks"].extend(new_blocks)

            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call_id))

        finish = agent_state.get("finish")
        if finish:
            return PlanningAgentResult(
                status="ok" if finish.get("status") == "ok" else "not_found",
                blocks=agent_state.get("blocks", []),
                steps=steps,
                sub_question=sub_question,
            )

        messages.append(
            HumanMessage(
                content=(
                    f"Round {iteration}/{limit} complete. "
                    "Call finish_planning_retrieval when planning context is sufficient."
                )
            )
        )

    blocks = agent_state.get("blocks", [])
    if blocks:
        return PlanningAgentResult(
            status="ok",
            blocks=blocks,
            steps=steps,
            sub_question=sub_question,
        )

    return PlanningAgentResult(
        status="max_iterations",
        blocks=blocks,
        steps=steps,
        sub_question=sub_question,
    )
