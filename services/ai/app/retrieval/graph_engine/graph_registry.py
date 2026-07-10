"""Academic graph engine lifecycle and action dispatch for the agent service."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine


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

    def execute_retrievals(
        self,
        actions: list[dict[str, Any]],
        *,
        user_completed_courses: list[str] | None = None,
        semester_filename: str | None = None,
        settings: Settings | None = None,
    ) -> list[dict[str, Any]]:
        cfg = settings or get_settings()
        engine = self.get_engine(cfg)
        # `semester_filename` is resolved per-request (e.g. "next semester"
        # relative to the student's profile) and is truthy on almost every
        # call — only actually reload + rebuild when it names a *different*
        # semester than the one already active, instead of unconditionally
        # rebuilding the whole graph on every single turn.
        active_filename = engine.active_semester.filename if engine.active_semester else None
        if semester_filename and semester_filename != active_filename:
            engine.set_active_semester(semester_filename, cfg.resolved_technion_raw_dir())
            engine.build_graph()
        return engine.execute_retrievals(
            actions,
            user_completed_courses=user_completed_courses,
            settings=cfg,
        )


graph_registry = GraphRegistry()


def warmup_graph_engine(*, settings: Settings | None = None) -> dict[str, Any]:
    """Pre-load the wiki + semester JSON graph (e.g. for eval runs / startup
    warmup) -- moved here from the retired intent-driven `graph_retriever.py`,
    unchanged, since it never touched anything intent-shaped itself.
    """
    cfg = settings or get_settings()
    if not cfg.is_graph_configured():
        return {"configured": False}
    return graph_registry.refresh_stats(cfg)
