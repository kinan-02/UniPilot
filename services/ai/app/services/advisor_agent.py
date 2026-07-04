"""Agentic academic advisor: retrieval agent loop → profile merge → synthesis."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.schemas.advisor import UserContextPayload
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.graph_tools import build_graph_tools, parse_tool_result
from app.services.planning_agent import run_planning_agent
from app.services.profile_agent import run_profile_agent
from app.services.regulation_agent import RegulationAgentResult, run_regulation_agent
from app.services.semester_catalog import resolve_semester_from_query

# Backward-compatible alias used by scripts and graph_registry.
UserContext = UserContextPayload

COURSE_CODE_RE = re.compile(r"\d{8}")
HEBREW_RE = re.compile(r"[\u0590-\u05FF]")

DEFAULT_MAX_RETRIEVAL_ITERATIONS = 5

DEFAULT_FALLBACK_EN = (
    "I could not find enough information in the Technion catalog or wiki to answer "
    "your question. Please contact your faculty undergraduate studies office, "
    "the course coordinator, or the Student Ombudsman (נציב קבילות סטודנטים)."
)
DEFAULT_FALLBACK_HE = (
    "לא מצאתי מספיק מידע בקטלוג או בוויקי של הטכניון כדי לענות על השאלה. "
    "מומלץ לפנות ללשכת לימודי הסמכה בפקולטה, לאחראי/ת הקורס, "
    "או לנציב קבילות הסטודנטים."
)


class ConsultProfileAgentInput(BaseModel):
    sub_question: str = Field(
        description="Student-specific sub-question for the profile specialist agent."
    )
    reasoning: str = Field(
        description="Why profile data is needed to answer the main question."
    )


class ConsultPlanningAgentInput(BaseModel):
    sub_question: str = Field(
        description="Planning sub-question for the planning swarm specialist."
    )
    reasoning: str = Field(
        description="Why graduation progress, semester plan, or risk data is needed."
    )


class ConsultRegulationAgentInput(BaseModel):
    sub_question: str = Field(
        description="Regulation/rights sub-question for the regulation specialist."
    )
    reasoning: str = Field(
        description="Why policy, student rights, or appeal process data is needed."
    )


class AdvisorResponse(BaseModel):
    answer: str = Field(description="Primary answer in the user's language.")
    confidence: Literal["high", "medium", "low"] = "medium"
    course_ids: list[str] = Field(default_factory=list)
    wiki_slugs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    eligibility: dict[str, Any] | None = None
    contacts: list[str] = Field(default_factory=list)


class RetrievalAgentResult(BaseModel):
    status: Literal["ok", "not_found", "max_iterations"] = "ok"
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    fallback_message: str | None = None
    contacts: list[str] = Field(default_factory=list)


class FinishRetrievalInput(BaseModel):
    status: Literal["ok", "not_found"] = Field(
        description="ok when accumulated context is sufficient; not_found when graph cannot answer."
    )
    reasoning: str = Field(description="Why retrieval should stop now.")
    relevance_assessment: str = Field(
        description="How well current accumulated context matches the user question."
    )
    fallback_message: str | None = Field(
        default=None,
        description="User-facing message when status=not_found.",
    )
    suggested_contacts: list[str] = Field(
        default_factory=list,
        description="Who the student should contact if info is missing.",
    )


def _default_model() -> str:
    return os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-mini")


def _llm_base_url() -> str | None:
    """Optional OpenAI-compatible API base (e.g. https://api.deepseek.com)."""
    raw = os.environ.get("OPENAI_BASE_URL", "").strip()
    return raw or None


def _max_iterations() -> int:
    raw = os.environ.get("ADVISOR_MAX_RETRIEVAL_ITERATIONS", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_MAX_RETRIEVAL_ITERATIONS


def _build_llm() -> ChatOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for advisor routing")
    kwargs: dict[str, Any] = {
        "model": _default_model(),
        "temperature": 0,
        "api_key": api_key,
    }
    base_url = _llm_base_url()
    if base_url:
        kwargs["base_url"] = base_url
        # DeepSeek thinking mode blocks tool_choice / json_schema structured output.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(**kwargs)


def _structured_output_method() -> str:
    """OpenAI json_schema is unavailable on many compatible APIs (e.g. DeepSeek)."""
    return "json_mode" if _llm_base_url() else "json_schema"


def _structured_output_llm(schema: type[BaseModel]) -> Any:
    return _build_llm().with_structured_output(schema, method=_structured_output_method())


def _extract_course_codes(text: str) -> list[str]:
    return list(dict.fromkeys(COURSE_CODE_RE.findall(text)))


def _question_is_hebrew(question: str) -> bool:
    return bool(HEBREW_RE.search(question))


def _default_fallback(question: str) -> str:
    return DEFAULT_FALLBACK_HE if _question_is_hebrew(question) else DEFAULT_FALLBACK_EN


def _block_key(block: dict[str, Any]) -> tuple[Any, ...]:
    return (
        block.get("source"),
        block.get("intent"),
        block.get("course_id"),
        block.get("wiki_slug"),
        block.get("search_query"),
    )


def _dedupe_blocks(
    existing: list[dict[str, Any]], new_blocks: list[dict[str, Any]]
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


def _build_finish_tool(state: dict[str, Any]) -> StructuredTool:
    def finish_retrieval(
        status: Literal["ok", "not_found"],
        reasoning: str,
        relevance_assessment: str,
        fallback_message: str | None = None,
        suggested_contacts: list[str] | None = None,
    ) -> str:
        """Signal that retrieval is complete or that required information was not found."""
        state["finish"] = {
            "status": status,
            "reasoning": reasoning,
            "relevance_assessment": relevance_assessment,
            "fallback_message": fallback_message,
            "suggested_contacts": suggested_contacts or [],
        }
        return json.dumps(state["finish"], ensure_ascii=False)

    return StructuredTool.from_function(
        func=finish_retrieval,
        name="finish_retrieval",
        description=(
            "End the retrieval loop. Use status=ok when context is sufficient to answer, "
            "or status=not_found when the knowledge graph lacks the required information."
        ),
        args_schema=FinishRetrievalInput,
    )


def _build_consult_profile_tool(
    ctx: UserContextPayload,
    engine: AcademicGraphEngine,
    profile_invocations: list[dict[str, Any]],
) -> StructuredTool:
    def consult_profile_agent(sub_question: str, reasoning: str) -> str:
        """Delegate a student-specific sub-question to the profile specialist agent."""
        result = run_profile_agent(sub_question, ctx, engine)
        profile_invocations.append(
            {
                "sub_question": sub_question,
                "reasoning": reasoning,
                "status": result.status,
                "steps": result.steps,
                "blocks": result.blocks,
            }
        )
        return json.dumps(
            {
                "status": result.status,
                "block_count": len(result.blocks),
                "blocks": result.blocks,
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        func=consult_profile_agent,
        name="consult_profile_agent",
        description=(
            "Delegate to the profile specialist when the question needs the student's "
            "transcript, academic path, or personal eligibility (e.g. 'can I take X?')."
        ),
        args_schema=ConsultProfileAgentInput,
    )


def _build_consult_regulation_tool(
    engine: AcademicGraphEngine,
    regulation_invocations: list[dict[str, Any]],
) -> StructuredTool:
    def consult_regulation_agent(sub_question: str, reasoning: str) -> str:
        result: RegulationAgentResult = run_regulation_agent(sub_question, engine)
        regulation_invocations.append(
            {
                "sub_question": sub_question,
                "reasoning": reasoning,
                "status": result.status,
                "message": result.message,
                "steps": result.steps,
                "blocks": result.blocks,
                "cited_slugs": result.cited_slugs,
                "suggested_contacts": result.suggested_contacts,
            }
        )
        return json.dumps(
            {
                "status": result.status,
                "message": result.message,
                "blocks": result.blocks,
                "cited_slugs": result.cited_slugs,
                "suggested_contacts": result.suggested_contacts,
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        func=consult_regulation_agent,
        name="consult_regulation_agent",
        description=(
            "Delegate regulation and student-rights questions to the Regulation specialist. "
            "Use for grade appeals, ombudsman, leave of absence, disciplinary rules, and policy text."
        ),
        args_schema=ConsultRegulationAgentInput,
    )


def _build_consult_planning_tool(
    ctx: UserContextPayload,
    planning_invocations: list[dict[str, Any]],
) -> StructuredTool:
    def consult_planning_agent(sub_question: str, reasoning: str) -> str:
        """Delegate plan/progress/risk sub-questions to the planning swarm specialist."""
        result = run_planning_agent(sub_question, ctx)
        planning_invocations.append(
            {
                "sub_question": sub_question,
                "reasoning": reasoning,
                "status": result.status,
                "steps": result.steps,
                "blocks": result.blocks,
            }
        )
        return json.dumps(
            {
                "status": result.status,
                "block_count": len(result.blocks),
                "blocks": result.blocks,
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        func=consult_planning_agent,
        name="consult_planning_agent",
        description=(
            "Delegate when the question needs graduation progress, semester planning, "
            "degree completion gaps, or academic risk analysis "
            "(e.g. 'what should I take next semester?', 'am I on track to graduate?')."
        ),
        args_schema=ConsultPlanningAgentInput,
    )


def run_retrieval_agent(
    question: str,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    user_context: UserContext | None = None,
    *,
    max_iterations: int | None = None,
    semester_resolution: dict[str, object] | None = None,
) -> RetrievalAgentResult:
    """
    Stage A+B: LLM agent loops over graph tools until context is sufficient,
    information is confirmed missing, or max iterations is reached.
    """
    ctx = user_context or UserContext()
    limit = max_iterations or _max_iterations()
    agent_state: dict[str, Any] = {"finish": None}
    profile_invocations: list[dict[str, Any]] = []
    planning_invocations: list[dict[str, Any]] = []
    regulation_invocations: list[dict[str, Any]] = []
    graph_tools = build_graph_tools(engine, technion_raw_dir, ctx.completed_courses)
    finish_tool = _build_finish_tool(agent_state)
    consult_tool = _build_consult_profile_tool(ctx, engine, profile_invocations)
    planning_tool = _build_consult_planning_tool(ctx, planning_invocations)
    regulation_tool = _build_consult_regulation_tool(engine, regulation_invocations)
    all_tools = graph_tools + [consult_tool, planning_tool, regulation_tool, finish_tool]
    llm = _build_llm().bind_tools(all_tools)

    accumulated: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    codes_in_question = _extract_course_codes(question)
    semester_note = ""
    if semester_resolution:
        semester = semester_resolution.get("semester")
        if semester is not None:
            semester_note = (
                f"Active semester: {semester.display_label} ({semester.filename}). "
            )
        assumption = semester_resolution.get("assumption_note")
        if assumption:
            semester_note += str(assumption)

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are the UniPilot retrieval agent for Technion academic advising.\n"
                "Gather ENOUGH factual context to answer the student question.\n\n"
                "TWO knowledge sources:\n"
                "1) Wiki graph — regulations, student rights, tracks, faculties (timeless).\n"
                "2) Semester JSON catalogs — schedule, syllabus, prerequisites per semester.\n"
                "   Filename rule: courses_2025_202 = Summer 2026; 200=Winter, 201=Spring, 202=Summer.\n\n"
                "Tools:\n"
                "- retrieve_graph_data: fetch wiki and/or semester JSON facts\n"
                "- list_wiki_catalog / list_semester_catalogs: browse available sources\n"
                "- select_semester_catalog: switch semester JSON before offering lookups\n"
                "- consult_profile_agent: delegate student-specific sub-questions "
                "(transcript, track, personal eligibility)\n"
                "- consult_planning_agent: delegate graduation progress, semester plan, "
                "and academic risk sub-questions\n"
                "- consult_regulation_agent: delegate grade appeals, ombudsman, leave of absence, "
                "student rights, and other policy questions\n"
                "- finish_retrieval: stop when context is sufficient OR confirmed missing\n\n"
                "Use consult_profile_agent when the answer depends on THIS student's "
                "completed courses, track, or whether they can take a course.\n"
                "Use consult_planning_agent for degree completion, next-semester planning, "
                "or risk questions — numbers must come from planning tools, not guesses.\n"
                "Use consult_regulation_agent for regulations, appeals, ombudsman, leave, "
                "and student rights — policy text must come from the regulation specialist.\n"
                "Use graph tools for course catalog facts, schedules, and syllabi.\n"
                "If the user did not specify a semester, use the active default and note the assumption.\n"
                "Never invent facts. Avoid duplicate retrievals.\n"
                f"Maximum {limit} rounds."
            )
        ),
        HumanMessage(
            content=(
                f"Question: {question}\n"
                f"Detected course codes: {', '.join(codes_in_question) or 'none'}\n"
                f"{semester_note}\n"
                "Student profile is available via consult_profile_agent when needed.\n"
                "Planning snapshots (progress, plan, risk) via consult_planning_agent when needed.\n"
                "Regulation and student-rights policy via consult_regulation_agent when needed."
            )
        ),
    ]

    tool_map = {tool.name: tool for tool in all_tools}

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
            "retrieved_blocks": [],
        }
        steps.append(step_record)
        messages.append(ai_message)

        if not tool_calls:
            messages.append(
                HumanMessage(
                    content="Call retrieve_graph_data, list_wiki_catalog, or finish_retrieval."
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
            else:
                tool_output = tool.invoke(args)

            if name == "retrieve_graph_data":
                block = _parse_tool_call_block(tool_output)
                new_blocks = _dedupe_blocks(accumulated, [block])
                accumulated.extend(new_blocks)
                step_record["retrieved_blocks"].extend(new_blocks)
            elif name == "consult_profile_agent":
                try:
                    payload = json.loads(tool_output)
                except json.JSONDecodeError:
                    payload = {}
                profile_blocks = payload.get("blocks") or []
                new_blocks = _dedupe_blocks(accumulated, profile_blocks)
                accumulated.extend(new_blocks)
                step_record["retrieved_blocks"].extend(new_blocks)
                step_record["profile_agent"] = profile_invocations[-1] if profile_invocations else None
            elif name == "consult_planning_agent":
                try:
                    payload = json.loads(tool_output)
                except json.JSONDecodeError:
                    payload = {}
                planning_blocks = payload.get("blocks") or []
                new_blocks = _dedupe_blocks(accumulated, planning_blocks)
                accumulated.extend(new_blocks)
                step_record["retrieved_blocks"].extend(new_blocks)
                step_record["planning_agent"] = (
                    planning_invocations[-1] if planning_invocations else None
                )
            elif name == "consult_regulation_agent":
                try:
                    payload = json.loads(tool_output)
                except json.JSONDecodeError:
                    payload = {}
                regulation_blocks = payload.get("blocks") or []
                new_blocks = _dedupe_blocks(accumulated, regulation_blocks)
                accumulated.extend(new_blocks)
                step_record["retrieved_blocks"].extend(new_blocks)
                step_record["regulation_agent"] = (
                    regulation_invocations[-1] if regulation_invocations else None
                )

            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call_id))

        finish = agent_state.get("finish")
        if finish:
            step_record["finish"] = finish
            if finish.get("status") == "not_found":
                return RetrievalAgentResult(
                    status="not_found",
                    blocks=accumulated,
                    steps=steps,
                    fallback_message=finish.get("fallback_message")
                    or _default_fallback(question),
                    contacts=finish.get("suggested_contacts", []),
                )
            return RetrievalAgentResult(
                status="ok",
                blocks=accumulated,
                steps=steps,
                contacts=finish.get("suggested_contacts", []),
            )

        messages.append(
            HumanMessage(
                content=(
                    f"Round {iteration}/{limit} complete. "
                    f"Accumulated blocks: {len(accumulated)}. "
                    "If context is sufficient call finish_retrieval(status=ok). "
                    "If missing after alternatives, finish_retrieval(status=not_found). "
                    "Otherwise retrieve more with different parameters."
                )
            )
        )

    nonempty = [block for block in accumulated if not block.get("is_empty")]
    if nonempty:
        return RetrievalAgentResult(status="ok", blocks=accumulated, steps=steps)

    return RetrievalAgentResult(
        status="max_iterations",
        blocks=accumulated,
        steps=steps,
        fallback_message=_default_fallback(question),
        contacts=[
            "Faculty undergraduate studies office",
            "Course coordinator",
            "Student Ombudsman (נציב קבילות סטודנטים)",
        ],
    )


def _merge_user_profile(user_context: UserContextPayload) -> dict[str, Any]:
    """Explicit profile envelope merged after retrieval, before synthesis."""
    return {
        "track_slug": user_context.track_slug,
        "faculty": user_context.faculty,
        "catalog_year": user_context.catalog_year,
        "completed_courses": user_context.completed_courses,
        "display_name": user_context.display_name,
        "degree_id": user_context.degree_id,
        "plan_semester_code": user_context.plan_semester_code,
        "program_type": user_context.program_type,
        "institution_id": user_context.institution_id,
        "academic_path": user_context.academic_path,
        "preferences": user_context.preferences,
        "transcript_count": len(user_context.transcript),
        "completed_count": len(user_context.completed_courses),
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Synthesis JSON must be an object")
    return payload


def _eligibility_from_loose_data(data: dict[str, Any]) -> dict[str, Any] | None:
    if "eligible" not in data:
        return data.get("eligibility") if isinstance(data.get("eligibility"), dict) else None
    return {
        "eligible": data.get("eligible"),
        "missing_prerequisites": data.get("missing_prerequisites", []),
        "course_id": data.get("course_id"),
    }


def _course_ids_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    codes = [
        str(block.get("course_id"))
        for block in blocks
        if block.get("course_id")
    ]
    return list(dict.fromkeys(codes))


def _answer_from_blocks(question: str, blocks: list[dict[str, Any]]) -> str | None:
    parts = [
        str(block.get("context", "")).strip()
        for block in blocks
        if not block.get("is_empty") and block.get("context")
    ]
    if not parts:
        return None
    joined = "\n\n".join(parts[:3])
    return joined[:3000]


def _normalize_advisor_response(
    data: dict[str, Any],
    question: str,
    retrieval_blocks: list[dict[str, Any]],
) -> AdvisorResponse:
    """Map loosely-typed LLM JSON (common on compatible APIs) into AdvisorResponse."""
    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip():
        return AdvisorResponse(
            answer=answer.strip(),
            confidence=data.get("confidence", "medium"),
            course_ids=list(data.get("course_ids") or _course_ids_from_blocks(retrieval_blocks)),
            wiki_slugs=list(data.get("wiki_slugs") or []),
            sources=list(data.get("sources") or []),
            eligibility=_eligibility_from_loose_data(data),
            contacts=list(data.get("contacts") or []),
        )

    eligibility = _eligibility_from_loose_data(data)
    if eligibility is not None:
        course_id = str(eligibility.get("course_id") or "")
        missing = eligibility.get("missing_prerequisites") or []
        if eligibility.get("eligible"):
            answer_text = (
                f"כן, אתה זכאי לקורס {course_id}."
                if _question_is_hebrew(question)
                else f"Yes, you are eligible for course {course_id}."
            )
        else:
            missing_text = ", ".join(str(code) for code in missing)
            answer_text = (
                f"לא, אינך זכאי לקורס {course_id}. חסרים קורסי קדם: {missing_text}."
                if _question_is_hebrew(question)
                else f"No, you are not eligible for course {course_id}. Missing: {missing_text}."
            )
        return AdvisorResponse(
            answer=answer_text,
            confidence="medium",
            course_ids=[course_id] if course_id else _course_ids_from_blocks(retrieval_blocks),
            eligibility=eligibility,
        )

    schedule = data.get("schedule")
    if isinstance(schedule, dict):
        course_id = str(schedule.get("course_id") or "")
        course_name = str(schedule.get("course_name") or "")
        slots = schedule.get("slots") or schedule.get("entries") or []
        lines = [f"{course_id} {course_name}".strip()]
        if isinstance(slots, list):
            for slot in slots:
                if isinstance(slot, dict):
                    lines.append(
                        f"- {slot.get('day', slot.get('יום', ''))} "
                        f"{slot.get('time', slot.get('שעה', ''))}"
                    )
        return AdvisorResponse(
            answer="\n".join(lines).strip() or json.dumps(schedule, ensure_ascii=False),
            confidence="medium",
            course_ids=[course_id] if course_id else _course_ids_from_blocks(retrieval_blocks),
        )

    block_answer = _answer_from_blocks(question, retrieval_blocks)
    if block_answer:
        return AdvisorResponse(
            answer=block_answer,
            confidence="medium",
            course_ids=_course_ids_from_blocks(retrieval_blocks),
            eligibility=eligibility,
        )

    return AdvisorResponse(
        answer=json.dumps(data, ensure_ascii=False)[:2000],
        confidence="low",
        course_ids=_course_ids_from_blocks(retrieval_blocks),
        eligibility=eligibility,
    )


def _synthesis_messages(
    question: str,
    profile: dict[str, Any],
    retrieval_blocks: list[dict[str, Any]],
    semester_resolution: dict[str, object] | None,
    *,
    strict_json: bool = False,
) -> list[Any]:
    context_payload = json.dumps(
        {
            "question": question,
            "user_profile": profile,
            "retrieval_blocks": retrieval_blocks,
            "semester_resolution": _serialize_semester_resolution(semester_resolution),
        },
        ensure_ascii=False,
    )
    json_rules = ""
    if strict_json:
        json_rules = (
            "\nReturn ONE JSON object with keys: "
            "answer (string, full user-facing reply), confidence (high|medium|low), "
            "course_ids (string[]), wiki_slugs (string[]), sources (string[]), "
            "eligibility (object|null), contacts (string[]).\n"
            "Do NOT return only eligibility or schedule sub-objects — put the full reply in answer."
        )
    system = SystemMessage(
        content=(
            "You are UniPilot, a Technion academic advisor (synthesis stage).\n"
            "Answer ONLY from retrieval_blocks and user_profile.\n"
            "Match the question language (Hebrew or English).\n"
            "Personalize using track_slug and completed_courses when relevant.\n"
            "When planning_agent blocks are present, cite graduation credits, plan courses, "
            "and risk severities exactly as given — do not recompute.\n"
            "When regulation_agent blocks are present, include wiki_slugs from cited_sources "
            "in wiki_slugs and mention suggested_contacts when relevant.\n"
            "Copy eligibility facts exactly from retrieval blocks — do not recompute.\n"
            "Include contacts only when the answer references who to contact."
            f"{json_rules}"
        )
    )
    return [system, HumanMessage(content=context_payload)]


def _synthesize_with_json_prompt(
    question: str,
    retrieval_blocks: list[dict[str, Any]],
    profile: dict[str, Any],
    semester_resolution: dict[str, object] | None,
) -> AdvisorResponse:
    llm = _build_llm().bind(response_format={"type": "json_object"})
    messages = _synthesis_messages(
        question,
        profile,
        retrieval_blocks,
        semester_resolution,
        strict_json=True,
    )
    raw = llm.invoke(messages)
    content = raw.content if isinstance(raw.content, str) else str(raw.content)
    data = _extract_json_object(content)
    return _normalize_advisor_response(data, question, retrieval_blocks)


def synthesize_answer(
    question: str,
    retrieval_blocks: list[dict[str, Any]],
    user_context: UserContext | None = None,
    *,
    retrieval_status: str = "ok",
    fallback_message: str | None = None,
    contacts: list[str] | None = None,
    semester_resolution: dict[str, object] | None = None,
) -> AdvisorResponse:
    """Stage C: LLM synthesis with retrieved facts + user profile."""
    if retrieval_status in {"not_found", "max_iterations"}:
        return AdvisorResponse(
            answer=fallback_message or _default_fallback(question),
            confidence="low",
            contacts=contacts or [],
            sources=[],
        )

    ctx = user_context or UserContext()
    profile = _merge_user_profile(ctx)

    if _llm_base_url():
        return _synthesize_with_json_prompt(
            question, retrieval_blocks, profile, semester_resolution
        )

    llm = _structured_output_llm(AdvisorResponse)
    messages = _synthesis_messages(
        question, profile, retrieval_blocks, semester_resolution
    )
    return llm.invoke(messages)


def _serialize_semester_resolution(
    resolution: dict[str, object] | None,
) -> dict[str, Any] | None:
    if not resolution:
        return None
    semester = resolution.get("semester")
    return {
        "confidence": resolution.get("confidence"),
        "needs_clarification": resolution.get("needs_clarification"),
        "assumption_note": resolution.get("assumption_note"),
        "semester": (
            {
                "filename": semester.filename,
                "display_label": semester.display_label,
                "plan_semester_code": semester.plan_semester_code,
            }
            if semester is not None
            else None
        ),
    }


def advise(
    question: str,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    user_context: UserContext | None = None,
) -> dict[str, Any]:
    """Full pipeline: semester resolve → retrieval agent → profile merge → synthesis."""
    ctx = user_context or UserContext()

    semester_resolution = resolve_semester_from_query(
        question,
        engine.available_semesters,
        explicit_filename=ctx.semester_filename,
        explicit_plan_code=ctx.plan_semester_code,
    )
    semester = semester_resolution.get("semester")
    if semester is not None:
        engine.set_active_semester(semester.filename, technion_raw_dir)
        engine.build_graph()

    retrieval = run_retrieval_agent(
        question,
        engine,
        technion_raw_dir,
        ctx,
        semester_resolution=semester_resolution,
    )
    profile = _merge_user_profile(ctx)

    profile_invocations = [
        step.get("profile_agent")
        for step in retrieval.steps
        if step.get("profile_agent")
    ]
    planning_invocations = [
        step.get("planning_agent")
        for step in retrieval.steps
        if step.get("planning_agent")
    ]
    regulation_invocations = [
        step.get("regulation_agent")
        for step in retrieval.steps
        if step.get("regulation_agent")
    ]

    response = synthesize_answer(
        question,
        retrieval.blocks,
        ctx,
        retrieval_status=retrieval.status,
        fallback_message=retrieval.fallback_message,
        contacts=retrieval.contacts,
        semester_resolution=semester_resolution,
    )

    merged_eligibility = response.eligibility
    for block in retrieval.blocks:
        if block.get("facts"):
            merged_eligibility = block["facts"]
            break

    return {
        "question": question,
        "semester_resolution": _serialize_semester_resolution(semester_resolution),
        "retrieval_agent": {
            "status": retrieval.status,
            "iterations": len(retrieval.steps),
            "steps": retrieval.steps,
        },
        "profile_agent_invocations": profile_invocations,
        "planning_agent_invocations": planning_invocations,
        "regulation_agent_invocations": regulation_invocations,
        "retrieval_blocks": retrieval.blocks,
        "user_profile": profile,
        "response": response.model_dump(),
        "eligibility": merged_eligibility,
    }
