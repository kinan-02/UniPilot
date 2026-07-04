"""Profile specialist sub-agent: transcript, academic path, course-fit assessment."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.schemas.advisor import UserContextPayload
from app.services.academic_graph_engine import AcademicGraphEngine

DEFAULT_MAX_PROFILE_ITERATIONS = 3


class ProfileAgentResult(BaseModel):
    status: Literal["ok", "not_found", "max_iterations", "empty_profile"] = "ok"
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    sub_question: str = ""


class FinishProfileRetrievalInput(BaseModel):
    status: Literal["ok", "not_found"] = Field(
        description="ok when profile context is sufficient; not_found when data is missing."
    )
    reasoning: str = Field(description="Why profile retrieval should stop now.")


class AssessCourseFitInput(BaseModel):
    course_id: str = Field(description="8-digit Technion course number.")


class ListCompletedCoursesInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100, description="Max transcript rows to return.")


def _max_profile_iterations() -> int:
    raw = os.environ.get("ADVISOR_MAX_PROFILE_ITERATIONS", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_MAX_PROFILE_ITERATIONS


def _profile_has_data(ctx: UserContextPayload) -> bool:
    return bool(
        ctx.completed_courses
        or ctx.track_slug
        or ctx.transcript
        or ctx.degree_id
        or ctx.catalog_year
    )


def _build_profile_summary(ctx: UserContextPayload) -> str:
    academic_path = ctx.academic_path or {}
    minors = academic_path.get("minors") or []
    minor_text = ", ".join(str(item) for item in minors) if minors else "none"
    return (
        f"Track: {ctx.track_slug or 'unknown'}\n"
        f"Faculty: {ctx.faculty or 'unknown'}\n"
        f"Degree: {ctx.degree_id or 'unknown'}\n"
        f"Catalog year: {ctx.catalog_year or 'unknown'}\n"
        f"Current semester: {ctx.plan_semester_code or 'unknown'}\n"
        f"Program type: {ctx.program_type or 'unknown'}\n"
        f"Minors: {minor_text}\n"
        f"Completed courses: {len(ctx.completed_courses)}"
    )


def _format_transcript(ctx: UserContextPayload, limit: int) -> str:
    rows = ctx.transcript[:limit]
    if not rows:
        numbers = ctx.completed_courses[:limit]
        if not numbers:
            return "No completed courses on file."
        return "Completed course numbers: " + ", ".join(numbers)

    lines = []
    for row in rows:
        grade = f", grade {row.grade}" if row.grade else ""
        semester = f", semester {row.semester_code}" if row.semester_code else ""
        lines.append(f"- {row.course_number}{semester}{grade}")
    return "\n".join(lines)


def _assess_course_fit(
    course_id: str,
    ctx: UserContextPayload,
    engine: AcademicGraphEngine,
) -> dict[str, Any]:
    eligible, missing = engine.evaluate_eligibility(course_id, ctx.completed_courses)
    return {
        "course_id": course_id,
        "eligible": eligible,
        "missing_prerequisites": missing,
        "completed_count": len(ctx.completed_courses),
    }


def _profile_block(
    intent: str,
    context: str,
    *,
    course_id: str | None = None,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "source": "profile_agent",
        "intent": intent,
        "course_id": course_id,
        "wiki_slug": None,
        "search_query": None,
        "context": context,
        "is_empty": not context.strip(),
    }
    if facts is not None:
        block["facts"] = facts
    return block


def _build_profile_tools(
    ctx: UserContextPayload,
    engine: AcademicGraphEngine,
    state: dict[str, Any],
) -> list[StructuredTool]:
    def get_profile_summary() -> str:
        """Return a concise summary of the student's academic profile."""
        summary = _build_profile_summary(ctx)
        block = _profile_block("profile_summary", summary)
        state.setdefault("blocks", []).append(block)
        return summary

    def list_completed_courses(limit: int = 20) -> str:
        """List completed courses from the student transcript."""
        text = _format_transcript(ctx, limit)
        block = _profile_block("transcript", text)
        state.setdefault("blocks", []).append(block)
        return text

    def assess_course_fit(course_id: str) -> str:
        """Check prerequisite eligibility for a course given completed courses."""
        facts = _assess_course_fit(course_id, ctx, engine)
        if facts["eligible"]:
            context = f"{course_id}: eligible (prerequisites satisfied)."
        else:
            missing = ", ".join(facts["missing_prerequisites"]) or "unknown"
            context = f"{course_id}: not eligible. Missing prerequisites: {missing}."
        block = _profile_block("course_fit", context, course_id=course_id, facts=facts)
        state.setdefault("blocks", []).append(block)
        return json.dumps(facts, ensure_ascii=False)

    def finish_profile_retrieval(
        status: Literal["ok", "not_found"],
        reasoning: str,
    ) -> str:
        """Signal that profile retrieval is complete."""
        state["finish"] = {"status": status, "reasoning": reasoning}
        return json.dumps(state["finish"], ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=get_profile_summary,
            name="get_profile_summary",
            description="Summarize track, faculty, catalog year, and completed course count.",
        ),
        StructuredTool.from_function(
            func=list_completed_courses,
            name="list_completed_courses",
            description="List transcript rows (course numbers, grades, semesters).",
            args_schema=ListCompletedCoursesInput,
        ),
        StructuredTool.from_function(
            func=assess_course_fit,
            name="assess_course_fit",
            description=(
                "Evaluate whether the student meets prerequisites for an 8-digit course."
            ),
            args_schema=AssessCourseFitInput,
        ),
        StructuredTool.from_function(
            func=finish_profile_retrieval,
            name="finish_profile_retrieval",
            description="End profile retrieval when context is sufficient or unavailable.",
            args_schema=FinishProfileRetrievalInput,
        ),
    ]


def run_profile_agent(
    sub_question: str,
    ctx: UserContextPayload,
    engine: AcademicGraphEngine,
    *,
    llm_factory: Any | None = None,
    max_iterations: int | None = None,
) -> ProfileAgentResult:
    """
    Agent 2: answers student-specific sub-questions using profile tools.
    Invoked by the retrieval orchestrator via consult_profile_agent.
    """
    if not _profile_has_data(ctx):
        return ProfileAgentResult(
            status="empty_profile",
            blocks=[
                _profile_block(
                    "profile_summary",
                    "No student profile or transcript data was provided.",
                )
            ],
            sub_question=sub_question,
        )

    if llm_factory is None:
        from app.services.advisor_agent import _build_llm

        llm_factory = _build_llm

    limit = max_iterations or _max_profile_iterations()
    agent_state: dict[str, Any] = {"finish": None, "blocks": []}
    tools = _build_profile_tools(ctx, engine, agent_state)
    llm = llm_factory().bind_tools(tools)
    tool_map = {tool.name: tool for tool in tools}
    steps: list[dict[str, Any]] = []

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are the UniPilot profile specialist for Technion students.\n"
                "Answer ONLY the delegated sub-question using the student's profile data.\n"
                "Tools:\n"
                "- get_profile_summary: track, faculty, catalog year, semester\n"
                "- list_completed_courses: transcript slice\n"
                "- assess_course_fit: prerequisite eligibility for one course\n"
                "- finish_profile_retrieval: stop when enough profile context is gathered\n\n"
                "Never invent transcript data. For eligibility questions, call assess_course_fit.\n"
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
            "profile_blocks": [],
        }
        steps.append(step_record)
        messages.append(ai_message)

        if not tool_calls:
            messages.append(
                HumanMessage(
                    content="Call a profile tool or finish_profile_retrieval(status=ok)."
                )
            )
            continue

        for call in tool_calls:
            name = call["name"]
            args = call.get("args", {})
            tool_call_id = call.get("id", f"profile_{iteration}_{name}")
            tool = tool_map.get(name)
            if not tool:
                tool_output = json.dumps({"error": f"Unknown tool {name}"})
            else:
                tool_output = tool.invoke(args)

            if name in {"get_profile_summary", "list_completed_courses", "assess_course_fit"}:
                new_blocks = agent_state.get("blocks", [])[-1:]
                step_record["profile_blocks"].extend(new_blocks)

            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call_id))

        finish = agent_state.get("finish")
        if finish:
            return ProfileAgentResult(
                status="ok" if finish.get("status") == "ok" else "not_found",
                blocks=agent_state.get("blocks", []),
                steps=steps,
                sub_question=sub_question,
            )

        messages.append(
            HumanMessage(
                content=(
                    f"Round {iteration}/{limit} complete. "
                    "Call finish_profile_retrieval when profile context is sufficient."
                )
            )
        )

    blocks = agent_state.get("blocks", [])
    if blocks:
        return ProfileAgentResult(
            status="ok",
            blocks=blocks,
            steps=steps,
            sub_question=sub_question,
        )

    return ProfileAgentResult(
        status="max_iterations",
        blocks=blocks,
        steps=steps,
        sub_question=sub_question,
    )
