"""MAS Planner LLM tool-calling loop over graph_tools."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.llm.client import build_mas_llm
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.graph_tools import build_graph_tools, parse_tool_result
from app.services.tool_result_cache import (
    CACHEABLE_TOOLS,
    get_cached_tool_result,
    set_cached_tool_result,
)

COURSE_CODE_RE = re.compile(r"\d{8}")
DEFAULT_MAX_TOOL_ITERATIONS = 5
LLM_INVOKE_TIMEOUT_SEC = 90
LLM_INVOKE_MAX_RETRIES = 3


class ProposePlanInput(BaseModel):
    course_ids: list[str] = Field(
        min_length=1,
        max_length=12,
        description="8-digit Technion course codes offered in the active semester catalog.",
    )
    reasoning: str = Field(description="Why this plan satisfies the student goal.")
    notes: str = Field(default="", description="Optional planner notes for the transcript.")

    @field_validator("course_ids")
    @classmethod
    def validate_course_ids(cls, value: list[str]) -> list[str]:
        normalized = _normalize_course_ids(value)
        if not normalized:
            raise ValueError("At least one valid 8-digit course code is required.")
        return normalized


class PlannerToolLoopResult(BaseModel):
    status: Literal["proposed", "no_proposal", "max_iterations"] = "no_proposal"
    course_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    reasoning: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


def _normalize_course_ids(raw_ids: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in raw_ids:
        digits = "".join(character for character in str(raw) if character.isdigit())
        if len(digits) == 8:
            cleaned.append(digits)
    return list(dict.fromkeys(cleaned))


def _max_tool_iterations(settings: Settings | None) -> int:
    cfg = settings or get_settings()
    raw = getattr(cfg, "mas_planner_max_tool_iterations", DEFAULT_MAX_TOOL_ITERATIONS)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TOOL_ITERATIONS


def _block_key(block: dict[str, Any]) -> tuple[Any, ...]:
    return (
        block.get("intent"),
        block.get("course_id"),
        block.get("wiki_slug"),
        block.get("search_query"),
    )


def _dedupe_blocks(
    existing: list[dict[str, Any]],
    new_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {_block_key(block) for block in existing}
    unique: list[dict[str, Any]] = []
    for block in new_blocks:
        key = _block_key(block)
        if key in seen:
            continue
        seen.add(key)
        unique.append(block)
    return unique


def _parse_tool_call_block(tool_result: str) -> dict[str, Any]:
    block = parse_tool_result(tool_result)
    if "error" in block:
        block["is_empty"] = True
    return block


def _build_propose_plan_tool(state: dict[str, Any]) -> StructuredTool:
    def propose_plan(course_ids: list[str], reasoning: str, notes: str = "") -> str:
        """Submit the final next-semester course plan after graph tool research."""
        normalized = _normalize_course_ids(course_ids)
        if not normalized:
            return json.dumps({"error": "No valid 8-digit course codes in proposal."})

        state["proposal"] = {
            "course_ids": normalized,
            "reasoning": reasoning,
            "notes": notes or "Planner LLM proposal after graph tool research.",
        }
        return json.dumps(state["proposal"], ensure_ascii=False)

    return StructuredTool.from_function(
        func=propose_plan,
        name="propose_plan",
        description=(
            "Submit the final next-semester plan. Call ONLY after using graph tools to verify "
            "catalog offerings, prerequisites, and schedules. course_ids must be 8-digit codes."
        ),
        args_schema=ProposePlanInput,
    )


def _references_from_steps(steps: list[dict[str, Any]]) -> list[str]:
    references: list[str] = []
    for step in steps:
        iteration = step.get("iteration")
        for call in step.get("tool_calls", []):
            name = call.get("name")
            if name:
                references.append(f"tool:{name}:round={iteration}")
        for block in step.get("retrieved_blocks", []):
            intent = block.get("intent")
            course_id = block.get("course_id")
            if intent and course_id:
                references.append(f"tool:retrieve_graph_data:{intent}:{course_id}")
    if steps:
        references.append(f"planner_tool_iterations:{len(steps)}")
    return list(dict.fromkeys(references))


async def run_planner_tool_loop(
    *,
    goal: str,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    completed_courses: list[str],
    semester_label: str,
    semester_filename: str | None,
    settings: Settings | None = None,
    max_iterations: int | None = None,
    session_id: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> PlannerToolLoopResult:
    """
    Planner-stage LLM loop: research with graph_tools, then propose_plan.

    Returns normalized course_ids when the model submits a proposal.
    """
    cfg = settings or get_settings()
    limit = max_iterations or _max_tool_iterations(cfg)
    agent_state: dict[str, Any] = {"proposal": None}
    graph_tools = build_graph_tools(engine, technion_raw_dir, completed_courses)
    propose_tool = _build_propose_plan_tool(agent_state)
    all_tools = graph_tools + [propose_tool]
    llm = build_mas_llm(cfg).bind_tools(all_tools)

    accumulated: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    codes_in_goal = _normalize_course_ids(COURSE_CODE_RE.findall(goal))
    ctx = user_context or {}
    path_priority = list(ctx.get("path_priority_courses") or [])
    track_slug = str(ctx.get("track_slug") or "unknown")
    credits_remaining = None
    graduation = ctx.get("graduation_progress")
    if isinstance(graduation, dict):
        credits_remaining = graduation.get("creditsRemaining")

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are the UniPilot MAS Planner agent for Technion next-semester planning.\n"
                "Research with graph tools, then call propose_plan with ONLY real catalog course codes.\n\n"
                "Knowledge sources:\n"
                "1) Wiki graph — regulations, tracks, student rights.\n"
                "2) Semester JSON catalogs — offerings, schedules, prerequisites, syllabi.\n"
                "   Filename rule: courses_2025_202 = Summer 2026; 200=Winter, 201=Spring, 202=Summer.\n\n"
                "Tools:\n"
                "- retrieve_graph_data — fetch wiki and/or semester JSON facts\n"
                "- list_wiki_catalog / list_semester_catalogs — browse sources\n"
                "- select_semester_catalog — switch semester JSON before offering lookups\n"
                "- propose_plan — submit final course_ids when research is complete\n\n"
                "Rules:\n"
                "- Verify eligibility/prerequisites before proposing a course.\n"
                "- Respect completed courses; do not propose courses with unmet prerequisites.\n"
                "- Prioritize the student's remaining degree requirements and track-aligned courses.\n"
                "- Do not propose random unrelated electives when mandatory requirements remain.\n"
                "- Never invent course codes.\n"
                f"- Maximum {limit} tool rounds."
            )
        ),
        HumanMessage(
            content=(
                f"Planning goal: {goal}\n"
                f"Active semester: {semester_label} ({semester_filename or 'default'})\n"
                f"Student track slug: {track_slug}\n"
                f"Completed courses: {', '.join(completed_courses) or 'none'}\n"
                f"Priority remaining requirement courses: {', '.join(path_priority[:12]) or 'unknown'}\n"
                f"Credits remaining toward degree: {credits_remaining if credits_remaining is not None else 'unknown'}\n"
                f"Course codes mentioned in goal: {', '.join(codes_in_goal) or 'none'}\n"
                "Use graph tools, then call propose_plan with courses that advance THIS student's degree path."
            )
        ),
    ]

    tool_map = {tool.name: tool for tool in all_tools}

    async def _invoke_llm() -> AIMessage:
        last_error: Exception | None = None
        for attempt in range(1, LLM_INVOKE_MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(
                    llm.ainvoke(messages),
                    timeout=LLM_INVOKE_TIMEOUT_SEC,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= LLM_INVOKE_MAX_RETRIES:
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM invoke failed without error")

    cache_hits = 0
    cache_misses = 0

    for iteration in range(1, limit + 1):
        agent_state["proposal"] = None
        ai_message: AIMessage = await _invoke_llm()
        tool_calls = getattr(ai_message, "tool_calls", None) or []

        step_record: dict[str, Any] = {
            "iteration": iteration,
            "content": ai_message.content,
            "tool_calls": [
                {"name": call["name"], "args": call.get("args", {})} for call in tool_calls
            ],
            "retrieved_blocks": [],
        }
        steps.append(step_record)
        messages.append(ai_message)

        if not tool_calls:
            messages.append(
                HumanMessage(
                    content=(
                        "Call retrieve_graph_data, list_semester_catalogs, or propose_plan "
                        "with verified course codes."
                    )
                )
            )
            continue

        for call in tool_calls:
            name = call["name"]
            args = call.get("args", {})
            tool_call_id = call.get("id", f"call_{iteration}_{name}")
            tool = tool_map.get(name)

            if not tool:
                tool_output = json.dumps({"error": f"Unknown tool {name}"})
            elif name in CACHEABLE_TOOLS and session_id:
                cached = await get_cached_tool_result(
                    session_id=session_id,
                    tool_name=name,
                    args=dict(args),
                )
                if cached is not None:
                    cache_hits += 1
                    tool_output = cached
                else:
                    cache_misses += 1
                    tool_output = tool.invoke(args)
                    await set_cached_tool_result(
                        session_id=session_id,
                        tool_name=name,
                        args=dict(args),
                        result=tool_output,
                    )
            else:
                tool_output = tool.invoke(args)

            if name == "retrieve_graph_data":
                block = _parse_tool_call_block(tool_output)
                new_blocks = _dedupe_blocks(accumulated, [block])
                accumulated.extend(new_blocks)
                step_record["retrieved_blocks"].extend(new_blocks)

            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call_id))

        step_record["tool_cache_hits"] = cache_hits
        step_record["tool_cache_misses"] = cache_misses

        proposal = agent_state.get("proposal")
        if proposal:
            step_record["proposal"] = proposal
            references = _references_from_steps(steps)
            references.append(f"tool:propose_plan:count={len(proposal['course_ids'])}")
            references.append(f"tool:cache_hits={cache_hits}")
            references.append(f"tool:cache_misses={cache_misses}")
            return PlannerToolLoopResult(
                status="proposed",
                course_ids=list(proposal["course_ids"]),
                notes=str(proposal.get("notes") or ""),
                reasoning=str(proposal.get("reasoning") or ""),
                steps=steps,
                references=references,
            )

        messages.append(
            HumanMessage(
                content=(
                    f"Round {iteration}/{limit} complete. Accumulated blocks: {len(accumulated)}. "
                    "If you can propose a feasible plan, call propose_plan. "
                    "Otherwise retrieve more catalog/eligibility facts with different parameters."
                )
            )
        )

    references = _references_from_steps(steps)
    references.append(f"tool:cache_hits={cache_hits}")
    references.append(f"tool:cache_misses={cache_misses}")
    return PlannerToolLoopResult(
        status="max_iterations",
        course_ids=[],
        notes="Planner tool loop reached max iterations without propose_plan.",
        steps=steps,
        references=references,
    )
