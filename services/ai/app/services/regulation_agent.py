"""Regulation & Rights specialist sub-agent for policy-heavy advisor questions."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.academic_graph_engine import AcademicGraphEngine

DEFAULT_MAX_REGULATION_ITERATIONS = 4


class RegulationAgentResult(BaseModel):
    status: Literal["ok", "not_found", "max_iterations"] = "ok"
    message: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    cited_slugs: list[str] = Field(default_factory=list)
    suggested_contacts: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    sub_question: str = ""


class WikiSearchInput(BaseModel):
    search_query: str = Field(description="Keywords for wiki search (Hebrew or English).")


class WikiPageInput(BaseModel):
    wiki_slug: str = Field(description="Wiki page slug, e.g. student-rights.")


class CiteSourcesInput(BaseModel):
    wiki_slugs: list[str] = Field(
        min_length=1,
        description="Wiki slugs that must appear in the final answer citations.",
    )


class SuggestedContactsInput(BaseModel):
    contacts: list[str] = Field(
        min_length=1,
        description="Offices or roles the student should contact (name + brief role).",
    )


class FinishRegulationRetrievalInput(BaseModel):
    status: Literal["ok", "not_found"] = Field(
        description="ok when regulation context is sufficient; not_found when wiki lacks policy text."
    )
    reasoning: str = Field(description="Why regulation retrieval should stop now.")


def _max_regulation_iterations() -> int:
    raw = os.environ.get("ADVISOR_MAX_REGULATION_ITERATIONS", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_MAX_REGULATION_ITERATIONS


def _regulation_block(intent: str, **fields: Any) -> dict[str, Any]:
    return {"source": "regulation_agent", "intent": intent, **fields}


def _wiki_search(engine: AcademicGraphEngine, search_query: str) -> str:
    return engine.retrieve_context("wiki_search", search_query=search_query)


def _wiki_page(engine: AcademicGraphEngine, wiki_slug: str) -> str:
    return engine.retrieve_context("wiki_page", wiki_slug=wiki_slug)


def build_regulation_agent_tools(
    engine: AcademicGraphEngine,
    agent_state: dict[str, Any],
) -> list[StructuredTool]:
    def wiki_search(search_query: str) -> str:
        context = _wiki_search(engine, search_query)
        agent_state["blocks"].append(
            _regulation_block("wiki_search", search_query=search_query, context=context)
        )
        return context

    def wiki_page(wiki_slug: str) -> str:
        context = _wiki_page(engine, wiki_slug)
        agent_state["blocks"].append(
            _regulation_block("wiki_page", wiki_slug=wiki_slug, context=context)
        )
        return context

    def cite_sources(wiki_slugs: list[str]) -> str:
        cited = agent_state.setdefault("cited_slugs", [])
        for slug in wiki_slugs:
            normalized = slug.strip()
            if normalized and normalized not in cited:
                cited.append(normalized)
        agent_state["blocks"].append(
            _regulation_block("cited_sources", wiki_slugs=list(cited))
        )
        return json.dumps({"recorded_slugs": cited}, ensure_ascii=False)

    def suggested_contacts(contacts: list[str]) -> str:
        stored = agent_state.setdefault("suggested_contacts", [])
        for contact in contacts:
            normalized = contact.strip()
            if normalized and normalized not in stored:
                stored.append(normalized)
        agent_state["blocks"].append(
            _regulation_block("suggested_contacts", contacts=list(stored))
        )
        return json.dumps({"contacts": stored}, ensure_ascii=False)

    def finish_regulation_retrieval(
        status: Literal["ok", "not_found"],
        reasoning: str,
    ) -> str:
        agent_state["finish"] = {"status": status, "reasoning": reasoning}
        return json.dumps(agent_state["finish"], ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=wiki_search,
            name="wiki_search",
            description="Search wiki for regulations, student rights, appeals, leave policies.",
            args_schema=WikiSearchInput,
        ),
        StructuredTool.from_function(
            func=wiki_page,
            name="wiki_page",
            description="Load full text of a wiki regulation page by slug.",
            args_schema=WikiPageInput,
        ),
        StructuredTool.from_function(
            func=cite_sources,
            name="cite_sources",
            description="Record wiki slugs that must be cited in the final answer (call before finish).",
            args_schema=CiteSourcesInput,
        ),
        StructuredTool.from_function(
            func=suggested_contacts,
            name="suggested_contacts",
            description="Suggest offices or roles the student should contact.",
            args_schema=SuggestedContactsInput,
        ),
        StructuredTool.from_function(
            func=finish_regulation_retrieval,
            name="finish_regulation_retrieval",
            description="Return regulation blocks to the retrieval orchestrator.",
            args_schema=FinishRegulationRetrievalInput,
        ),
    ]


def run_regulation_agent(
    sub_question: str,
    engine: AcademicGraphEngine,
    *,
    max_iterations: int | None = None,
    llm_factory: Any | None = None,
) -> RegulationAgentResult:
    """Run the regulation specialist (wiki policy retrieval)."""
    if llm_factory is None:
        from app.services.advisor_agent import _build_llm

        llm_factory = _build_llm

    limit = max_iterations or _max_regulation_iterations()
    agent_state: dict[str, Any] = {
        "finish": None,
        "blocks": [],
        "cited_slugs": [],
        "suggested_contacts": [],
    }
    tools = build_regulation_agent_tools(engine, agent_state)
    llm = llm_factory().bind_tools(tools)
    tool_map = {tool.name: tool for tool in tools}
    steps: list[dict[str, Any]] = []

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are the UniPilot Regulation & Rights specialist for Technion students.\n"
                "Answer ONLY the delegated sub-question using wiki regulation pages.\n"
                "Topics: grade appeals, ombudsman, leave of absence, student rights, discipline.\n\n"
                "Tools:\n"
                "- wiki_search: find relevant regulation pages\n"
                "- wiki_page: load full policy text by slug\n"
                "- cite_sources: record wiki slugs for mandatory citations (call before finish)\n"
                "- suggested_contacts: offices the student should contact\n"
                "- finish_regulation_retrieval: stop when enough policy context is gathered\n\n"
                "Never invent policy text. Always cite_sources before finish when status=ok.\n"
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
            "regulation_blocks": [],
        }
        steps.append(step_record)
        messages.append(ai_message)

        if not tool_calls:
            messages.append(
                HumanMessage(
                    content="Call wiki_search, wiki_page, or finish_regulation_retrieval."
                )
            )
            continue

        for call in tool_calls:
            name = call["name"]
            args = call.get("args", {})
            tool_call_id = call.get("id", f"regulation_{iteration}_{name}")
            tool = tool_map.get(name)
            if not tool:
                tool_output = json.dumps({"error": f"Unknown tool {name}"})
            else:
                tool_output = tool.invoke(args)

            if name in {"wiki_search", "wiki_page", "cite_sources", "suggested_contacts"}:
                new_blocks = agent_state.get("blocks", [])[-1:]
                step_record["regulation_blocks"].extend(new_blocks)

            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call_id))

        finish = agent_state.get("finish")
        if finish:
            status = "ok" if finish.get("status") == "ok" else "not_found"
            return RegulationAgentResult(
                status=status,
                message=str(finish.get("reasoning") or ""),
                blocks=agent_state.get("blocks", []),
                cited_slugs=agent_state.get("cited_slugs", []),
                suggested_contacts=agent_state.get("suggested_contacts", []),
                steps=steps,
                sub_question=sub_question,
            )

        messages.append(
            HumanMessage(
                content=(
                    f"Round {iteration}/{limit} complete. "
                    "Call cite_sources then finish_regulation_retrieval when policy context is sufficient."
                )
            )
        )

    blocks = agent_state.get("blocks", [])
    if blocks:
        return RegulationAgentResult(
            status="ok",
            message="Partial regulation retrieval (max iterations).",
            blocks=blocks,
            cited_slugs=agent_state.get("cited_slugs", []),
            suggested_contacts=agent_state.get("suggested_contacts", []),
            steps=steps,
            sub_question=sub_question,
        )

    return RegulationAgentResult(
        status="not_found",
        message="Could not retrieve regulation context for this question.",
        blocks=[],
        steps=steps,
        sub_question=sub_question,
    )
