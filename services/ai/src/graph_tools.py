"""LangChain tools wrapping the academic knowledge graph engine."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from academic_graph_engine import AcademicGraphEngine

WIKI_ONLY_INTENTS = {"wiki_page", "wiki_search", "structure"}
SEMESTER_INTENTS = {
    "schedule",
    "eligibility",
    "syllabus",
    "prerequisites",
    "course_info",
}


class GraphRetrievalInput(BaseModel):
    intent: str = Field(
        description=(
            "Retrieval type: schedule, syllabus, prerequisites, eligibility, "
            "structure, course_info, wiki_page, wiki_search"
        )
    )
    course_id: str | None = Field(
        default=None, description="8-digit course code for course-related intents."
    )
    wiki_slug: str | None = Field(
        default=None, description="Wiki slug for wiki_page (e.g. student-rights)."
    )
    search_query: str | None = Field(
        default=None, description="Search terms for wiki_search."
    )
    semester_filename: str | None = Field(
        default=None,
        description=(
            "Semester JSON file e.g. courses_2025_201.json. "
            "Required for schedule/syllabus/prerequisites when switching semester."
        ),
    )


class SelectSemesterInput(BaseModel):
    semester_filename: str = Field(
        description="Semester offering file, e.g. courses_2025_201.json (Spring 2026)."
    )


def _block_is_empty(context: str) -> bool:
    lowered = context.lower()
    empty_markers = [
        "not found",
        "no matches",
        "no schedule data",
        "no syllabus",
        "not found in catalog",
    ]
    return any(marker in lowered for marker in empty_markers)


def _retrieve_graph_data(
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    completed_courses: list[str],
    intent: str,
    course_id: str | None = None,
    wiki_slug: str | None = None,
    search_query: str | None = None,
    semester_filename: str | None = None,
) -> str:
    """Execute a single graph retrieval and return JSON payload."""
    try:
        active_semester = engine.active_semester.filename if engine.active_semester else None
        if semester_filename and semester_filename != active_semester:
            engine.set_active_semester(semester_filename, technion_raw_dir)
            engine.build_graph()
            active_semester = semester_filename

        context = engine.retrieve_context(
            intent=intent,  # type: ignore[arg-type]
            course_id=course_id,
            user_completed_courses=completed_courses,
            wiki_slug=wiki_slug,
            search_query=search_query,
        )
        facts: dict[str, Any] = {}
        if intent == "eligibility" and course_id:
            eligible, missing = engine.evaluate_eligibility(course_id, completed_courses)
            facts = {
                "eligible": eligible,
                "missing_prerequisites": missing,
                "course_id": course_id,
            }

        block = {
            "intent": intent,
            "course_id": course_id,
            "wiki_slug": wiki_slug,
            "search_query": search_query,
            "semester_filename": active_semester,
            "data_source": (
                "wiki"
                if intent in WIKI_ONLY_INTENTS
                else "wiki+semester_json"
            ),
            "context": context,
            "facts": facts,
            "is_empty": _block_is_empty(context),
        }
        return json.dumps(block, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc), "is_empty": True}, ensure_ascii=False)


def build_graph_tools(
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    completed_courses: list[str] | None = None,
) -> list[StructuredTool]:
    """Build LangChain tools bound to a loaded graph engine instance."""
    completed = completed_courses or []

    def retrieve_graph_data(
        intent: str,
        course_id: str | None = None,
        wiki_slug: str | None = None,
        search_query: str | None = None,
        semester_filename: str | None = None,
    ) -> str:
        """Retrieve factual context from wiki (structure/regulations) and semester JSON (offerings)."""
        return _retrieve_graph_data(
            engine,
            technion_raw_dir,
            completed,
            intent,
            course_id=course_id,
            wiki_slug=wiki_slug,
            search_query=search_query,
            semester_filename=semester_filename,
        )

    def list_wiki_catalog() -> str:
        """List wiki concept/regulation/track pages (static knowledge graph)."""
        return engine.get_wiki_catalog_summary()

    def list_semester_catalogs() -> str:
        """List semester offering JSON files (schedule/syllabus/prereqs per semester)."""
        return engine.get_semester_catalog_summary()

    def select_semester_catalog(semester_filename: str) -> str:
        """Activate a semester JSON catalog before course offering retrievals."""
        info = engine.set_active_semester(semester_filename, technion_raw_dir)
        engine.build_graph()
        return json.dumps(
            {
                "active_semester": info.filename,
                "display_label": info.display_label,
                "plan_semester_code": info.plan_semester_code,
            },
            ensure_ascii=False,
        )

    return [
        StructuredTool.from_function(
            func=retrieve_graph_data,
            name="retrieve_graph_data",
            description=(
                "Fetch context from TWO sources: (1) wiki graph for regulations/tracks/structure, "
                "(2) semester JSON for schedule/syllabus/prerequisites/course_info. "
                "Pick semester_filename when the user names a term (חורף/אביב/קיץ) or year."
            ),
            args_schema=GraphRetrievalInput,
        ),
        StructuredTool.from_function(
            func=list_wiki_catalog,
            name="list_wiki_catalog",
            description="List wiki pages: regulations, student rights, tracks, faculties.",
        ),
        StructuredTool.from_function(
            func=list_semester_catalogs,
            name="list_semester_catalogs",
            description=(
                "List semester offering JSON catalogs. "
                "Filename year is one behind calendar year (courses_2025_202 = Summer 2026). "
                "200=Winter, 201=Spring, 202=Summer."
            ),
        ),
        StructuredTool.from_function(
            func=select_semester_catalog,
            name="select_semester_catalog",
            description="Switch active semester JSON before retrieving schedules or syllabi.",
            args_schema=SelectSemesterInput,
        ),
    ]


def parse_tool_result(payload: str) -> dict[str, Any]:
    return json.loads(payload)
