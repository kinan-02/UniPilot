"""Academic graph engine lifecycle and action dispatch."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.advisor_agent import UserContext, advise


class GraphRegistry:
    """Caches a loaded AcademicGraphEngine for the configured wiki + semester paths."""

    def __init__(self) -> None:
        self._engine: AcademicGraphEngine | None = None
        self._engine_key: tuple[str, str, str | None] | None = None
        self._cached_stats: dict[str, Any] | None = None

    def is_configured(self, settings: Settings | None = None) -> bool:
        return (settings or get_settings()).is_graph_configured()

    def get_engine(
        self,
        settings: Settings | None = None,
        *,
        md_dir: str | None = None,
        technion_raw_dir: str | None = None,
        default_semester: str | None = None,
    ) -> AcademicGraphEngine:
        cfg = settings or get_settings()
        wiki = (md_dir or cfg.academic_wiki_path or "").strip()
        raw = (technion_raw_dir or cfg.resolved_technion_raw_dir() or "").strip()
        semester = (
            default_semester
            if default_semester is not None
            else cfg.resolved_default_semester_file()
        )
        if not wiki or not raw:
            raise RuntimeError("Academic graph paths are not configured")

        key = (wiki, raw, semester)
        if self._engine is None or self._engine_key != key:
            engine = AcademicGraphEngine()
            engine.load_from_paths(
                wiki,
                raw,
                semester_filename=semester,
            )
            engine.build_graph()
            self._engine = engine
            self._engine_key = key
            self._cached_stats = None
        return self._engine

    def refresh_stats(self, settings: Settings | None = None) -> dict[str, Any]:
        cfg = settings or get_settings()
        if not cfg.is_graph_configured():
            self._cached_stats = {"configured": False}
            return self._cached_stats

        try:
            engine = self.get_engine(cfg)
            self._cached_stats = {"configured": True, **engine.graph_stats()}
        except Exception as exc:  # noqa: BLE001 — surface graph load errors in health
            self._cached_stats = {"configured": True, "error": str(exc)}
        return self._cached_stats

    def cached_stats(self) -> dict[str, Any]:
        if self._cached_stats is None:
            return self.refresh_stats()
        return self._cached_stats

    def retrieve_context(
        self,
        *,
        intent: str,
        course_id: str | None = None,
        user_completed_courses: list[str] | None = None,
        wiki_slug: str | None = None,
        search_query: str | None = None,
        semester_filename: str | None = None,
        settings: Settings | None = None,
    ) -> str:
        cfg = settings or get_settings()
        engine = self.get_engine(cfg)
        if semester_filename:
            engine.set_active_semester(semester_filename, cfg.resolved_technion_raw_dir())
            engine.build_graph()
        return engine.retrieve_context(
            intent,  # type: ignore[arg-type]
            course_id=course_id,
            user_completed_courses=user_completed_courses,
            wiki_slug=wiki_slug,
            search_query=search_query,
        )

    def run_advise(
        self,
        *,
        question: str,
        user_context: dict[str, Any] | None = None,
        settings: Settings | None = None,
    ) -> dict[str, Any]:
        cfg = settings or get_settings()
        engine = self.get_engine(cfg)
        user_ctx = UserContext(**(user_context or {}))
        return advise(
            question=question,
            engine=engine,
            technion_raw_dir=cfg.resolved_technion_raw_dir(),
            user_context=user_ctx,
        )

    def dispatch_action(
        self,
        payload: dict[str, Any],
        settings: Settings | None = None,
    ) -> tuple[bool, Any, str | None]:
        """Execute a graph_bridge-style action. Returns (success, data, error)."""
        cfg = settings or get_settings()
        md_dir = (payload.get("md_dir_path") or cfg.academic_wiki_path or "").strip()
        technion_raw_dir = (
            payload.get("technion_raw_dir") or cfg.resolved_technion_raw_dir() or ""
        ).strip()
        default_semester = (
            payload.get("semester_filename")
            or cfg.resolved_default_semester_file()
        )

        if not md_dir or not technion_raw_dir:
            return False, None, "md_dir_path and technion_raw_dir (or env vars) are required"

        action = payload.get("action", "retrieve_context")

        try:
            engine = self.get_engine(
                cfg,
                md_dir=md_dir,
                technion_raw_dir=technion_raw_dir,
                default_semester=default_semester,
            )

            if payload.get("semester_filename"):
                engine.set_active_semester(payload["semester_filename"], technion_raw_dir)
                engine.build_graph()

            if action == "stats":
                return True, engine.graph_stats(), None

            if action == "parse_prerequisites":
                ast = AcademicGraphEngine.parse_prerequisites_string(
                    payload.get("prereq_string", "")
                )
                return True, {"ast": ast}, None

            if action == "evaluate_eligibility":
                eligible, missing = engine.evaluate_eligibility(
                    payload["course_id"],
                    payload.get("user_completed_courses", []),
                )
                return True, {"eligible": eligible, "missing": missing}, None

            if action == "wiki_search":
                hits = engine.search_wiki(payload.get("query", ""), limit=payload.get("limit", 3))
                return True, {"hits": hits}, None

            if action == "list_semesters":
                return True, {
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
                }, None

            if action == "retrieve_multi":
                blocks = engine.execute_retrievals(
                    payload.get("actions", []),
                    user_completed_courses=payload.get("user_completed_courses", []),
                )
                return True, {"blocks": blocks}, None

            if action == "retrieve_context":
                context = engine.retrieve_context(
                    payload["intent"],
                    course_id=payload.get("course_id"),
                    user_completed_courses=payload.get("user_completed_courses"),
                    wiki_slug=payload.get("wiki_slug"),
                    search_query=payload.get("search_query"),
                )
                return True, {"context": context}, None

            if action == "advise":
                result = self.run_advise(
                    question=payload["question"],
                    user_context=payload.get("user_context", {}),
                    settings=cfg,
                )
                return True, result, None

            return False, None, f"Unknown action: {action}"
        except Exception as exc:  # noqa: BLE001 — CLI/script compatibility
            return False, None, str(exc)


graph_registry = GraphRegistry()
