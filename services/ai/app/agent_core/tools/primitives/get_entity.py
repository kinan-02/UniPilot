"""`get_entity` -- structured fetch of any named record (docs/agent/AGENT_VISION.md §5, primitive 1).

`entity_type` is intentionally kept as a plain `str`, not a `Literal`, and
validated at runtime against `_KNOWN_ENTITY_TYPES` -- per §5's closing
paragraph, "a new entity type ... is an additive change to the graph's
schema -- it never requires ... touching the orchestrator", which would be
defeated by baking the vocabulary into the Pydantic schema itself.

Two data sources, dispatched by `entity_type`:
- `course`/`track`/`program`/`minor`/`faculty`/`wiki_page` -- the wiki +
  raw-offering `AcademicGraphEngine` graph (§2.1's sole academic source of
  truth).
- `student_profile`/`completed_courses`/`semester_plan` -- this service's
  own read-only Mongo repositories (§2.1's user-specific/operational data).

Fails closed: an unknown `entity_type`, an id that resolves to nothing, or a
requested wiki entity_type that doesn't structurally match the page found at
that id all return `ok=False` with a distinct error -- never a placeholder
success.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel

from app.agent_core.planning.state import CertaintyTag, SourceRef
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor
from app.db.mongo import get_database
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.semester_plan_repository import find_semester_plans_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
from app.retrieval.graph_engine.graph_registry import graph_registry

TOOL_NAME = "get_entity"

_WIKI_ENTITY_TYPES: frozenset[str] = frozenset({"track", "program", "minor", "faculty", "wiki_page"})
_MONGO_ENTITY_TYPES: frozenset[str] = frozenset({"student_profile", "completed_courses", "semester_plan"})
_KNOWN_ENTITY_TYPES: frozenset[str] = _WIKI_ENTITY_TYPES | _MONGO_ENTITY_TYPES | {"course"}


class GetEntityInput(BaseModel):
    entity_type: str
    entity_id: str


def _sanitize_value(value: Any) -> Any:
    """Mongo documents carry `ObjectId`/`datetime` values that aren't
    JSON-safe inside `ToolOutputEnvelope.data` -- convert them, recursively.
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _sanitize_mongo_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_value(value) for key, value in doc.items()}


def _classify_wiki_path(path: str, slug: str) -> str:
    """Structural classification of a wiki page's own kind, used to validate
    a requested wiki-backed `entity_type` actually matches what's at that
    slug. Mirrors `AcademicGraphEngine._classify_page`'s course/track split,
    but:
    - fixes the faculty-directory prefix: the real directory is
      `entities/faculties/` (plural); the engine's own
      `rel_path.startswith("entities/faculty")` check never matches it
      (`"entities/faculties/x.md".startswith("entities/faculty")` is
      `False` -- verified directly), so the engine classifies every real
      faculty page as generic `"wiki"`.
    - adds program/minor detection from `entities/programs/` (a real
      directory the engine does not classify at all today) using the
      `program-`/`minor-` filename-prefix convention already used by
      `entity_slug_registry.py`'s `_slug_priority`.
    """
    if path.startswith("courses/"):
        return "course"
    if path.startswith("entities/tracks/"):
        return "track"
    if path.startswith("entities/faculties/"):
        return "faculty"
    if path.startswith("entities/programs/"):
        if slug.startswith("minor-"):
            return "minor"
        if slug.startswith("program-"):
            return "program"
        return "wiki_page"
    return "wiki_page"


def _wiki_page_meta(engine: AcademicGraphEngine, slug: str) -> dict[str, Any]:
    return next((entry for entry in engine.wiki_catalog if entry.get("slug") == slug), {})


def _wiki_entity_result(engine: AcademicGraphEngine, entity_type: str, slug: str) -> ToolOutputEnvelope:
    page = engine.wiki_pages.get(slug)
    if page is None:
        return ToolOutputEnvelope(ok=False, data=None, error=f"entity_not_found: {entity_type}:{slug}")

    actual_kind = _classify_wiki_path(page.get("path", ""), slug)
    if entity_type != "wiki_page" and actual_kind != entity_type:
        return ToolOutputEnvelope(
            ok=False,
            data=None,
            error=f"entity_type_mismatch: requested {entity_type}, {slug} is {actual_kind}",
        )

    meta = _wiki_page_meta(engine, slug)
    return ToolOutputEnvelope(
        ok=True,
        data={
            "entityType": entity_type,
            "entityId": slug,
            "slug": slug,
            "path": page.get("path"),
            "title": meta.get("title"),
            "titleHe": meta.get("title_he"),
            "aliases": meta.get("aliases", []),
            "content": page.get("content", ""),
        },
        certainty=CertaintyTag(basis="wiki_derived", confidence=1.0, source_ref=SourceRef(page=slug)),
    )


def _course_wiki_slug(engine: AcademicGraphEngine, course_code: str) -> str | None:
    for slug, code in engine.slug_to_course_code.items():
        if code == course_code:
            return slug
    return None


def _course_entity_result(engine: AcademicGraphEngine, course_code: str) -> ToolOutputEnvelope:
    node = engine.graph.nodes.get(course_code)
    catalog_entry_found = course_code in engine.course_catalog
    wiki_slug = _course_wiki_slug(engine, course_code)
    wiki_page = engine.wiki_pages.get(wiki_slug) if wiki_slug else None

    if not catalog_entry_found and wiki_page is None:
        return ToolOutputEnvelope(ok=False, data=None, error=f"entity_not_found: course:{course_code}")

    data: dict[str, Any] = {"entityType": "course", "entityId": course_code}
    warnings: list[str] = []

    if catalog_entry_found and node is not None:
        data.update(
            {
                "name": node.get("name"),
                "credits": node.get("credits"),
                "faculty": node.get("faculty"),
                "prerequisitesRaw": node.get("prerequisites_raw"),
                "prerequisitesAst": node.get("prerequisites_ast"),
                "schedule": node.get("schedule"),
                "syllabus": node.get("syllabus"),
            }
        )
    else:
        warnings.append("course_not_in_active_semester_catalog")

    if wiki_page is not None:
        data["wikiSlug"] = wiki_slug
        data["wikiContent"] = wiki_page.get("content", "")
    else:
        warnings.append("no_wiki_page_found_for_course")

    return ToolOutputEnvelope(
        ok=True,
        data=data,
        certainty=CertaintyTag(
            basis="official_record" if catalog_entry_found else "wiki_derived",
            confidence=1.0,
            source_ref=SourceRef(page=wiki_slug or course_code),
        ),
    )


async def _mongo_entity_result(entity_type: str, user_id: str) -> ToolOutputEnvelope:
    database = await get_database()

    if entity_type == "student_profile":
        profile = await find_student_profile_by_user_id(database, user_id)
        if profile is None:
            return ToolOutputEnvelope(ok=False, data=None, error=f"entity_not_found: student_profile:{user_id}")
        return ToolOutputEnvelope(
            ok=True,
            data=_sanitize_mongo_doc(profile),
            certainty=CertaintyTag(basis="official_record", confidence=1.0),
        )

    if entity_type == "completed_courses":
        courses = await find_all_completed_courses_by_user_id(database, user_id)
        return ToolOutputEnvelope(
            ok=True,
            data={"completedCourses": [_sanitize_mongo_doc(course) for course in courses]},
            certainty=CertaintyTag(basis="official_record", confidence=1.0),
        )

    # entity_type == "semester_plan"
    result = await find_semester_plans_by_user_id(database, user_id)
    return ToolOutputEnvelope(
        ok=True,
        data={
            "plans": [_sanitize_mongo_doc(plan) for plan in result["plans"]],
            "total": result["total"],
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


async def run_get_entity(payload: GetEntityInput) -> ToolOutputEnvelope:
    entity_type = (payload.entity_type or "").strip()
    entity_id = (payload.entity_id or "").strip()

    if entity_type not in _KNOWN_ENTITY_TYPES:
        return ToolOutputEnvelope(ok=False, data=None, error=f"unknown_entity_type: {entity_type}")
    if not entity_id:
        return ToolOutputEnvelope(ok=False, data=None, error="entity_id_required")

    if entity_type in _MONGO_ENTITY_TYPES:
        try:
            return await _mongo_entity_result(entity_type, entity_id)
        except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
            return ToolOutputEnvelope(ok=False, data=None, error=f"mongo_lookup_failed: {exc}")

    # entity_type is "course" or one of the wiki-backed kinds.
    try:
        if not graph_registry.is_configured():
            return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")
        engine = graph_registry.get_engine()
    except Exception as exc:  # noqa: BLE001 -- a tool must fail closed, never raise
        return ToolOutputEnvelope(ok=False, data=None, error=f"academic_graph_unavailable: {exc}")

    if entity_type == "course":
        return _course_entity_result(engine, entity_id)
    return _wiki_entity_result(engine, entity_type, entity_id)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Structured fetch of any named record: course, track, program, minor, "
    "faculty, wiki_page (generic wiki entity, incl. regulation topics), student profile, "
    "completed courses, or semester plans.",
    input_model=GetEntityInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_entity,
)
