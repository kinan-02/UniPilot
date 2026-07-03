"""Academic graph engine lifecycle for MAS ground-truth tools."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.semester_catalog import semester_filename_for_plan_code


class GraphRegistry:
    """Caches a loaded AcademicGraphEngine for wiki + semester JSON paths."""

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

    def get_engine_for_user_context(
        self,
        user_context: dict[str, Any],
        settings: Settings | None = None,
    ) -> AcademicGraphEngine:
        profile_semester = semester_filename_for_plan_code(
            str(user_context.get("plan_semester_code") or "")
        )
        return self.get_engine(settings, default_semester=profile_semester)

    def refresh_stats(self, settings: Settings | None = None) -> dict[str, Any]:
        cfg = settings or get_settings()
        if not cfg.is_graph_configured():
            self._cached_stats = {"configured": False}
            return self._cached_stats

        try:
            engine = self.get_engine(cfg)
            self._cached_stats = {"configured": True, **engine.graph_stats()}
        except Exception as exc:  # noqa: BLE001
            self._cached_stats = {"configured": True, "error": str(exc)}
        return self._cached_stats

    def cached_stats(self) -> dict[str, Any]:
        if self._cached_stats is None:
            return self.refresh_stats()
        return self._cached_stats


graph_registry = GraphRegistry()
