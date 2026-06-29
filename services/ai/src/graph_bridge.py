"""Thin CLI bridge: JSON stdin → AcademicGraphEngine / AdvisorAgent → JSON stdout."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from academic_graph_engine import AcademicGraphEngine
from advisor_agent import UserContext, advise

_ENGINE: AcademicGraphEngine | None = None
_ENGINE_KEY: tuple[str, str, str | None] | None = None


def _paths_from_env(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    md_dir = payload.get("md_dir_path") or os.environ.get("ACADEMIC_WIKI_PATH", "")
    technion_raw_dir = payload.get("technion_raw_dir") or os.environ.get(
        "ACADEMIC_TECHNION_RAW_DIR", ""
    )
    default_semester = (
        payload.get("semester_filename")
        or os.environ.get("ACADEMIC_DEFAULT_SEMESTER_FILE", "").strip()
        or None
    )

    json_file = payload.get("json_file_path") or os.environ.get("ACADEMIC_CATALOG_JSON", "")
    if not technion_raw_dir and json_file:
        technion_raw_dir = str(Path(json_file).parent)

    if not default_semester and json_file:
        default_semester = Path(json_file).name

    return md_dir, technion_raw_dir, default_semester


def _get_engine(
    md_dir: str,
    technion_raw_dir: str,
    default_semester: str | None = None,
) -> AcademicGraphEngine:
    global _ENGINE, _ENGINE_KEY
    key = (md_dir, technion_raw_dir, default_semester)
    if _ENGINE is None or _ENGINE_KEY != key:
        engine = AcademicGraphEngine()
        engine.load_from_paths(
            md_dir,
            technion_raw_dir,
            semester_filename=default_semester,
        )
        engine.build_graph()
        _ENGINE = engine
        _ENGINE_KEY = key
    return _ENGINE


def _respond(success: bool, data: Any = None, error: str | None = None) -> None:
    print(json.dumps({"success": success, "data": data, "error": error}, ensure_ascii=False))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        _respond(False, error=f"Invalid JSON input: {exc}")
        return

    md_dir, technion_raw_dir, default_semester = _paths_from_env(payload)
    action = payload.get("action", "retrieve_context")

    if not md_dir or not technion_raw_dir:
        _respond(
            False,
            error="md_dir_path and technion_raw_dir (or env vars) are required",
        )
        return

    try:
        engine = _get_engine(md_dir, technion_raw_dir, default_semester)

        if payload.get("semester_filename"):
            engine.set_active_semester(payload["semester_filename"], technion_raw_dir)
            engine.build_graph()

        if action == "stats":
            _respond(True, data=engine.graph_stats())
            return

        if action == "parse_prerequisites":
            ast = AcademicGraphEngine.parse_prerequisites_string(
                payload.get("prereq_string", "")
            )
            _respond(True, data={"ast": ast})
            return

        if action == "evaluate_eligibility":
            eligible, missing = engine.evaluate_eligibility(
                payload["course_id"],
                payload.get("user_completed_courses", []),
            )
            _respond(True, data={"eligible": eligible, "missing": missing})
            return

        if action == "wiki_search":
            hits = engine.search_wiki(payload.get("query", ""), limit=payload.get("limit", 3))
            _respond(True, data={"hits": hits})
            return

        if action == "list_semesters":
            _respond(
                True,
                data={
                    "semesters": [
                        {
                            "filename": semester.filename,
                            "display_label": semester.display_label,
                            "plan_semester_code": semester.plan_semester_code,
                        }
                        for semester in engine.available_semesters
                    ],
                    "active_semester": (
                        engine.active_semester.filename if engine.active_semester else None
                    ),
                },
            )
            return

        if action == "retrieve_multi":
            blocks = engine.execute_retrievals(
                payload.get("actions", []),
                user_completed_courses=payload.get("user_completed_courses", []),
            )
            _respond(True, data={"blocks": blocks})
            return

        if action == "retrieve_context":
            context = engine.retrieve_context(
                payload["intent"],
                course_id=payload.get("course_id"),
                user_completed_courses=payload.get("user_completed_courses"),
                wiki_slug=payload.get("wiki_slug"),
                search_query=payload.get("search_query"),
            )
            _respond(True, data={"context": context})
            return

        if action == "advise":
            user_ctx = UserContext(**payload.get("user_context", {}))
            result = advise(
                question=payload["question"],
                engine=engine,
                technion_raw_dir=technion_raw_dir,
                user_context=user_ctx,
            )
            _respond(True, data=result)
            return

        _respond(False, error=f"Unknown action: {action}")
    except Exception as exc:
        _respond(False, error=str(exc))


if __name__ == "__main__":
    main()
