"""Planner agent — proposes and revises semester course plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.effectors.gateway import get_effector_gateway
from app.orchestrator.artifacts import GoalIntent, ViolationType
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn, PlanProposal
from app.orchestrator.violations import has_violation_type
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.api_catalog import api_suggested_course_numbers, uses_api_semester_catalog
from app.services.planner_candidates import build_candidate_variants
from app.services.path_relevant_planner import (
    reconcile_proposal_with_path_alignment,
    select_path_aligned_plan_courses,
)
from app.services.planner_support import (
    extract_course_codes,
    filter_eligible_courses,
    parse_course_credits,
    resolve_semester_for_goal,
    sum_plan_credits,
)
from app.services.plan_risk import resolve_max_credits
from app.services.reasoning_trace import (
    build_planner_repair_trace,
    build_planner_tool_loop_trace,
)
from app.services.schedule_conflict import (
    courses_involved_in_conflicts,
    detect_plan_schedule_conflicts,
)


class PlannerAgent:
    role = "planner"

    @staticmethod
    def _turn_payload(
        *,
        proposal: PlanProposal,
        variants: list[PlanProposal],
        reasoning_trace: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "primary": proposal.model_dump(),
            "variants": [variant.model_dump() for variant in variants],
        }
        if reasoning_trace is not None:
            payload["reasoningTrace"] = reasoning_trace
        return payload

    async def propose(self, blackboard: Blackboard) -> AgentTurn:
        proposal, references, reasoning_trace = await self._build_proposal(blackboard)
        technion_raw_dir = self._technion_raw_dir(blackboard.settings, blackboard.engine)
        llm_variants = None
        if blackboard.settings and blackboard.settings.llm_configured():
            from app.llm.planner_variants_layer import synthesize_planner_variants_with_llm

            llm_variants = await synthesize_planner_variants_with_llm(
                goal=blackboard.goal,
                primary=proposal,
                engine=blackboard.engine,
                technion_raw_dir=technion_raw_dir,
                completed_courses=blackboard.completed_courses,
                user_context=blackboard.user_context,
                settings=blackboard.settings,
            )

        variants = llm_variants or build_candidate_variants(
            proposal,
            engine=blackboard.engine,
            user_context=blackboard.user_context,
            completed_courses=blackboard.completed_courses,
            technion_raw_dir=technion_raw_dir,
        )
        blackboard.set_candidates(variants)
        return AgentTurn(
            agent_role=self.role,
            action="propose",
            payload=self._turn_payload(
                proposal=proposal,
                variants=variants,
                reasoning_trace=reasoning_trace,
            ),
            rationale=proposal.notes,
            references=references,
        )

    async def revise(self, blackboard: Blackboard) -> AgentTurn:
        if blackboard.candidate_plan is None:
            return await self.propose(blackboard)

        proposal = blackboard.candidate_plan
        typed = list(blackboard.typed_violations)
        settings = blackboard.settings
        repaired_by_llm = False
        reasoning_trace: dict[str, Any] | None = None

        if settings and settings.llm_configured() and typed:
            from app.llm.planner_repair import repair_plan_with_llm
            from app.orchestrator.violations import violation_messages

            repair_result = await repair_plan_with_llm(
                goal=blackboard.goal,
                proposal=proposal,
                violations=typed,
                completed_courses=blackboard.completed_courses,
                settings=settings,
            )
            if repair_result is not None and repair_result.course_ids:
                reasoning_trace = build_planner_repair_trace(
                    course_ids=repair_result.course_ids,
                    reasoning=repair_result.reasoning,
                    violations=violation_messages(typed),
                )
                proposal = PlanProposal(
                    course_ids=repair_result.course_ids,
                    semester_filename=proposal.semester_filename,
                    notes=repair_result.reasoning or "Planner LLM repair layer applied a minimal edit after veto.",
                    variant=proposal.variant,
                )
                repaired_by_llm = True

        if not repaired_by_llm:
            veto_agent = blackboard.last_veto_agent
            if veto_agent == "risk_sentinel" or has_violation_type(typed, ViolationType.CREDIT_OVERLOAD):
                proposal = self._revise_after_credit_veto(
                    proposal,
                    blackboard.engine,
                    blackboard.user_context,
                )
            elif has_violation_type(typed, ViolationType.SCHEDULE_CONFLICT):
                proposal = self._revise_after_schedule_veto(
                    proposal,
                    blackboard.engine,
                    blackboard.completed_courses,
                    self._technion_raw_dir(blackboard.settings, blackboard.engine),
                    blackboard.user_context,
                )
            else:
                proposal = self._revise_after_feasibility_veto(
                    proposal,
                    blackboard.engine,
                    blackboard.completed_courses,
                    self._technion_raw_dir(blackboard.settings, blackboard.engine),
                    blackboard.user_context,
                )
        else:
            proposal = self._revise_after_feasibility_veto(
                proposal,
                blackboard.engine,
                blackboard.completed_courses,
                self._technion_raw_dir(blackboard.settings, blackboard.engine),
                blackboard.user_context,
            )

        technion_raw_dir = self._technion_raw_dir(blackboard.settings, blackboard.engine)
        if proposal.course_ids and blackboard.engine is not None:
            aligned, _align_refs, _reconcile_mode = self._align_proposal_courses(
                course_ids=proposal.course_ids,
                engine=blackboard.engine,
                technion_raw_dir=technion_raw_dir,
                completed_courses=blackboard.completed_courses,
                user_context=blackboard.user_context,
                semester_filename=proposal.semester_filename,
            )
            if aligned:
                proposal = PlanProposal(
                    course_ids=aligned,
                    semester_filename=proposal.semester_filename,
                    notes=proposal.notes,
                    variant=proposal.variant,
                )

        llm_variants = None
        if blackboard.settings and blackboard.settings.llm_configured():
            from app.llm.planner_variants_layer import synthesize_planner_variants_with_llm

            llm_variants = await synthesize_planner_variants_with_llm(
                goal=blackboard.goal,
                primary=proposal,
                engine=blackboard.engine,
                technion_raw_dir=technion_raw_dir,
                completed_courses=blackboard.completed_courses,
                user_context=blackboard.user_context,
                settings=blackboard.settings,
            )

        variants = llm_variants or build_candidate_variants(
            proposal,
            engine=blackboard.engine,
            user_context=blackboard.user_context,
            completed_courses=blackboard.completed_courses,
            technion_raw_dir=technion_raw_dir,
        )
        blackboard.set_candidates(variants)
        if reasoning_trace is None:
            reasoning_trace = {
                "kind": "deterministic_revision",
                "veto_agent": blackboard.last_veto_agent,
                "notes": proposal.notes,
            }
        return AgentTurn(
            agent_role=self.role,
            action="revise",
            payload=self._turn_payload(
                proposal=proposal,
                variants=variants,
                reasoning_trace=reasoning_trace,
            ),
            rationale=proposal.notes,
        )

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        if blackboard.open_vetoes:
            return await self.revise(blackboard)
        return await self.propose(blackboard)

    def _technion_raw_dir(self, settings: Settings | None, engine: AcademicGraphEngine | None) -> str:
        if settings is not None:
            resolver = getattr(settings, "resolved_technion_raw_dir", None)
            if callable(resolver):
                return resolver()

        if engine is not None and engine.active_semester is not None:
            return str(Path(engine.active_semester.path).parent)

        from app.config import get_settings

        return get_settings().resolved_technion_raw_dir()

    def _align_proposal_courses(
        self,
        *,
        course_ids: list[str],
        engine: AcademicGraphEngine,
        technion_raw_dir: str,
        completed_courses: list[str],
        user_context: dict[str, Any],
        semester_filename: str | None,
        explicit_course_ids: list[str] | None = None,
    ) -> tuple[list[str], list[str], str]:
        verified, verify_refs = filter_eligible_courses(
            engine=engine,
            technion_raw_dir=technion_raw_dir,
            course_ids=course_ids,
            completed_courses=completed_courses,
            semester_filename=semester_filename,
            user_context=user_context,
        )
        references = list(verify_refs)
        if not verified:
            return [], references, "empty"

        max_credits = resolve_max_credits(user_context)
        reconciled, reconcile_refs, reconcile_mode = reconcile_proposal_with_path_alignment(
            verified,
            engine=engine,
            completed_courses=completed_courses,
            user_context=user_context,
            max_credits=max_credits,
            explicit_course_ids=explicit_course_ids,
        )
        references.extend(reconcile_refs)
        if reconcile_mode != "skipped":
            return reconciled, references, reconcile_mode
        return verified, references, reconcile_mode

    async def _build_proposal(
        self,
        blackboard: Blackboard,
    ) -> tuple[PlanProposal, list[str], dict[str, Any] | None]:
        engine = blackboard.engine
        settings = blackboard.settings
        goal = blackboard.goal
        completed = blackboard.completed_courses
        references: list[str] = []
        goal_spec = blackboard.goal_spec

        if engine is None:
            raise RuntimeError("Planner requires an AcademicGraphEngine on the blackboard")

        technion_raw_dir = self._technion_raw_dir(settings, engine)
        semester, semester_refs = resolve_semester_for_goal(
            goal,
            engine,
            technion_raw_dir,
            profile_plan_semester_code=blackboard.user_context.get("plan_semester_code"),
        )
        references.extend(semester_refs)
        semester_filename = semester.filename if semester else None
        semester_label = semester.display_label if semester else "default"

        codes_in_goal = (
            list(goal_spec.explicit_course_ids)
            if goal_spec and goal_spec.explicit_course_ids
            else extract_course_codes(goal)
        )
        if (
            not codes_in_goal
            and goal_spec
            and goal_spec.intent == GoalIntent.EXPLICIT_COURSES
            and goal_spec.explicit_course_ids
        ):
            codes_in_goal = list(goal_spec.explicit_course_ids)
        if codes_in_goal:
            aligned, align_refs, reconcile_mode = self._align_proposal_courses(
                course_ids=codes_in_goal,
                engine=engine,
                technion_raw_dir=technion_raw_dir,
                completed_courses=completed,
                user_context=blackboard.user_context,
                semester_filename=semester_filename,
                explicit_course_ids=codes_in_goal,
            )
            references.extend(align_refs)
            notes = (
                "Planner verified goal course codes against the semester catalog and degree path."
                if aligned
                else "Goal named courses but none passed eligibility or catalog checks."
            )
            if reconcile_mode in {"merged", "replaced", "explicit_merge"}:
                notes = "Plan aligned to your remaining degree requirements and explicit goal courses."
            return (
                PlanProposal(
                    course_ids=aligned,
                    semester_filename=semester_filename,
                    notes=notes,
                ),
                references,
                {
                    "kind": "deterministic_explicit_courses",
                    "requested_course_ids": list(codes_in_goal),
                    "verified_course_ids": list(aligned),
                    "reconcile_mode": reconcile_mode,
                },
            )

        api_suggested = api_suggested_course_numbers(blackboard.user_context)
        if (
            not codes_in_goal
            and uses_api_semester_catalog(blackboard.user_context)
            and api_suggested
        ):
            aligned, align_refs, reconcile_mode = self._align_proposal_courses(
                course_ids=api_suggested,
                engine=engine,
                technion_raw_dir=technion_raw_dir,
                completed_courses=completed,
                user_context=blackboard.user_context,
                semester_filename=semester_filename,
            )
            references.extend(align_refs)
            references.append("catalog:source=api_mongo")
            references.append(f"api:suggested_count={len(api_suggested)}")
            notes = (
                "Plan seeded from Progress-aligned API semester planner (Mongo catalog)."
                if aligned
                else "API semester planner returned courses but none passed validation."
            )
            return (
                PlanProposal(
                    course_ids=aligned or api_suggested,
                    semester_filename=semester_filename,
                    notes=notes,
                ),
                references,
                {
                    "kind": "api_semester_suggestion",
                    "suggested_course_ids": list(api_suggested),
                    "verified_course_ids": list(aligned),
                    "reconcile_mode": reconcile_mode,
                },
            )

        catalog = get_effector_gateway().list_eligible_catalog_courses(
            engine=engine,
            completed_courses=completed,
            user_context=blackboard.user_context,
        )
        max_credits = resolve_max_credits(blackboard.user_context)
        llm_trace: dict[str, Any] | None = None
        if settings and settings.llm_configured():
            try:
                from app.llm.planner_tool_loop import run_planner_tool_loop

                loop_result = await run_planner_tool_loop(
                    goal=goal,
                    engine=engine,
                    technion_raw_dir=technion_raw_dir,
                    completed_courses=completed,
                    semester_label=semester_label,
                    semester_filename=semester_filename,
                    settings=settings,
                    session_id=blackboard.session_id,
                    user_context=blackboard.user_context,
                )
                references.extend(loop_result.references)
                llm_trace = build_planner_tool_loop_trace(
                    status=loop_result.status,
                    reasoning=loop_result.reasoning,
                    notes=loop_result.notes,
                    steps=loop_result.steps,
                )

                if loop_result.course_ids:
                    aligned, align_refs, reconcile_mode = self._align_proposal_courses(
                        course_ids=loop_result.course_ids,
                        engine=engine,
                        technion_raw_dir=technion_raw_dir,
                        completed_courses=completed,
                        user_context=blackboard.user_context,
                        semester_filename=semester_filename,
                        explicit_course_ids=codes_in_goal or None,
                    )
                    references.extend(align_refs)
                    if aligned:
                        notes = loop_result.notes or loop_result.reasoning
                        if reconcile_mode in {"replaced", "merged", "explicit_merge"}:
                            notes = (
                                "Plan realigned to your remaining degree requirements "
                                "after planner research."
                            )
                        elif not notes:
                            notes = "Planner LLM proposal via graph tool loop."
                        references.append(f"path:reconcile_mode={reconcile_mode}")
                        return (
                            PlanProposal(
                                course_ids=aligned,
                                semester_filename=semester_filename,
                                notes=notes,
                            ),
                            references,
                            llm_trace,
                        )
                    references.append("tool:eligibility_filter:empty_after_llm")
                else:
                    references.append("tool:planner_loop:no_course_ids")
            except Exception:  # noqa: BLE001 — fall back to deterministic planner
                pass

        max_credits = resolve_max_credits(blackboard.user_context)
        fallback, path_refs = select_path_aligned_plan_courses(
            engine,
            completed,
            blackboard.user_context,
            max_credits=max_credits,
        )
        references.extend(path_refs)

        fallback_trace = llm_trace or {
            "kind": "path_aligned_fallback",
            "eligible_catalog_count": len(catalog),
            "selected_course_ids": list(fallback),
        }
        notes = (
            "Path-aligned planner using your remaining degree requirements and eligible courses."
            if fallback
            else "No path-aligned eligible courses found under the current credit cap."
        )
        return (
            PlanProposal(
                course_ids=fallback,
                semester_filename=semester_filename,
                notes=notes,
            ),
            references,
            fallback_trace,
        )

    def _revise_after_feasibility_veto(
        self,
        proposal: PlanProposal,
        engine: AcademicGraphEngine | None,
        completed_courses: list[str],
        technion_raw_dir: str,
        user_context: dict[str, Any],
    ) -> PlanProposal:
        if engine is None:
            return PlanProposal(
                course_ids=[],
                semester_filename=proposal.semester_filename,
                notes="Revised plan after veto (no graph engine available).",
            )

        revised, _refs = filter_eligible_courses(
            engine=engine,
            technion_raw_dir=technion_raw_dir,
            course_ids=proposal.course_ids,
            completed_courses=completed_courses,
            semester_filename=proposal.semester_filename,
            user_context=user_context,
        )
        return PlanProposal(
            course_ids=revised,
            semester_filename=proposal.semester_filename,
            notes="Revised plan after Catalog Scout veto (ineligible courses removed).",
        )

    def _revise_after_credit_veto(
        self,
        proposal: PlanProposal,
        engine: AcademicGraphEngine | None,
        user_context: dict,
    ) -> PlanProposal:
        if engine is None:
            return PlanProposal(
                course_ids=[],
                semester_filename=proposal.semester_filename,
                notes="Revised plan after credit veto (no graph engine available).",
            )

        max_credits = resolve_max_credits(user_context)
        remaining = list(proposal.course_ids)
        while remaining and sum_plan_credits(engine, remaining, user_context=user_context) > max_credits:
            drop_id = max(
                remaining,
                key=lambda course_id: parse_course_credits(engine, course_id, user_context=user_context),
            )
            remaining = [course_id for course_id in remaining if course_id != drop_id]

        return PlanProposal(
            course_ids=remaining,
            semester_filename=proposal.semester_filename,
            notes="Revised plan after Risk Sentinel veto (trimmed to credit workload limit).",
        )

    def _resolve_schedule_conflicts(
        self,
        engine: AcademicGraphEngine,
        course_ids: list[str],
    ) -> list[str]:
        remaining = list(course_ids)
        while len(remaining) > 1:
            conflicts, _refs = detect_plan_schedule_conflicts(engine, remaining)
            if not conflicts:
                break
            involved = courses_involved_in_conflicts(conflicts).intersection(remaining)
            if not involved:
                break
            drop_id = max(involved, key=lambda course_id: parse_course_credits(engine, course_id))
            remaining = [course_id for course_id in remaining if course_id != drop_id]
        return remaining

    def _revise_after_schedule_veto(
        self,
        proposal: PlanProposal,
        engine: AcademicGraphEngine | None,
        completed_courses: list[str],
        technion_raw_dir: str,
        user_context: dict[str, Any],
    ) -> PlanProposal:
        if engine is None:
            return PlanProposal(
                course_ids=[],
                semester_filename=proposal.semester_filename,
                notes="Revised plan after schedule veto (no graph engine available).",
            )

        resolved = self._resolve_schedule_conflicts(engine, proposal.course_ids)
        revised, _refs = filter_eligible_courses(
            engine=engine,
            technion_raw_dir=technion_raw_dir,
            course_ids=resolved,
            completed_courses=completed_courses,
            semester_filename=proposal.semester_filename,
            user_context=user_context,
        )
        return PlanProposal(
            course_ids=revised,
            semester_filename=proposal.semester_filename,
            notes="Revised plan after Catalog Scout veto (schedule conflicts resolved).",
        )
