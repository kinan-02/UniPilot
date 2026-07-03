"""Unified gateway for catalog, graduation, and risk effectors."""

from __future__ import annotations

from typing import Any

from app.clients.graduation_progress_client import (
    fetch_graduation_progress_for_user,
    fetch_graduation_progress_with_meta,
    preview_graduation_progress_for_user,
)
from app.config import Settings
from app.orchestrator.artifacts import HardConstraintResult
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.academic_risk_cache import (
    fetch_and_cache_academic_risk,
    get_cached_academic_risk,
)
from app.services import academic_risk_cache as risk_cache_module
from app.services.plan_hard_constraints import evaluate_hard_constraints, hard_violation_messages
from app.services.planner_support import list_eligible_catalog_courses
from app.validator.pre_commit import validate_plan_proposal

_gateway: MasEffectorGateway | None = None


def _prefix_refs(references: list[str], source: str) -> list[str]:
    prefixed: list[str] = []
    marker = f"effector:{source}:"
    for reference in references:
        if reference.startswith("effector:"):
            prefixed.append(reference)
        else:
            prefixed.append(f"{marker}{reference}")
    return prefixed


class MasEffectorGateway:
    """Single entry point for deterministic academic effectors."""

    def validate_catalog_plan(
        self,
        *,
        engine: AcademicGraphEngine,
        course_ids: list[str],
        completed_courses: list[str],
        user_context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], list[str]]:
        ok, violations, references = validate_plan_proposal(
            course_ids=list(course_ids),
            engine=engine,
            completed_courses=completed_courses,
            user_context=user_context,
        )
        return ok, violations, _prefix_refs(references, "catalog")

    def evaluate_hard_constraints(
        self,
        *,
        course_ids: list[str],
        engine: AcademicGraphEngine,
        completed_courses: list[str],
        user_context: dict[str, Any],
        academic_risk_analysis: dict[str, Any] | None = None,
    ) -> HardConstraintResult:
        result = evaluate_hard_constraints(
            course_ids=course_ids,
            engine=engine,
            completed_courses=completed_courses,
            user_context=user_context,
            academic_risk_analysis=academic_risk_analysis,
        )
        return result.model_copy(
            update={
                "references": _prefix_refs(list(result.references), "hard_gate"),
                "feasibility": result.feasibility.model_copy(
                    update={
                        "references": _prefix_refs(
                            list(result.feasibility.references),
                            "catalog",
                        )
                    }
                ),
                "risk": result.risk.model_copy(
                    update={
                        "references": _prefix_refs(list(result.risk.references), "risk")
                    }
                ),
            }
        )

    async def fetch_academic_risk_preview(
        self,
        *,
        blackboard: Blackboard,
        course_ids: list[str],
    ) -> dict[str, Any] | None:
        return await fetch_and_cache_academic_risk(blackboard, course_ids)

    async def preload_academic_risk_cache(
        self,
        blackboard: Blackboard,
        proposals: list[PlanProposal],
    ) -> None:
        await risk_cache_module.preload_academic_risk_cache(blackboard, proposals)

    def list_eligible_catalog_courses(
        self,
        *,
        engine: AcademicGraphEngine,
        completed_courses: list[str],
        user_context: dict[str, Any] | None = None,
    ) -> list[str]:
        return list_eligible_catalog_courses(
            engine,
            completed_courses,
            user_context=user_context,
        )

    async def fetch_graduation_progress(
        self,
        *,
        user_id: str,
        settings: Settings | None = None,
    ) -> dict[str, Any] | None:
        return await fetch_graduation_progress_for_user(user_id=user_id, settings=settings)

    async def fetch_graduation_progress_with_meta(
        self,
        *,
        user_id: str,
        settings: Settings | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        return await fetch_graduation_progress_with_meta(user_id=user_id, settings=settings)

    async def preview_graduation_progress(
        self,
        *,
        user_id: str,
        completed_course_numbers: list[str] | None = None,
        additional_course_numbers: list[str] | None = None,
        settings: Settings | None = None,
    ) -> dict[str, Any] | None:
        return await preview_graduation_progress_for_user(
            user_id=user_id,
            completed_course_numbers=completed_course_numbers,
            additional_course_numbers=additional_course_numbers,
            settings=settings,
        )

    def validate_committed_plan(
        self,
        *,
        blackboard: Blackboard,
        course_ids: list[str],
    ) -> tuple[bool, list[str], list[str]]:
        engine = blackboard.engine
        if engine is None:
            return False, ["Pre-commit validation requires an active catalog engine."], []

        references: list[str] = []
        ok, catalog_violations, catalog_refs = self.validate_catalog_plan(
            engine=engine,
            course_ids=list(course_ids),
            completed_courses=blackboard.completed_courses,
            user_context=blackboard.user_context,
        )
        references.extend(catalog_refs)
        if not ok:
            return False, catalog_violations, references

        academic_risk = get_cached_academic_risk(blackboard, list(course_ids))
        hard = self.evaluate_hard_constraints(
            course_ids=list(course_ids),
            engine=engine,
            completed_courses=blackboard.completed_courses,
            user_context=blackboard.user_context,
            academic_risk_analysis=academic_risk,
        )
        references.extend(hard.references)
        if not hard.ok:
            return False, hard_violation_messages(hard), references

        references.append("effector:validator:pre_commit_validated")
        return True, [], references


def get_effector_gateway() -> MasEffectorGateway:
    global _gateway
    if _gateway is None:
        _gateway = MasEffectorGateway()
    return _gateway
