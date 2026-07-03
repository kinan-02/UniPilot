"""Deterministic degree-progress signals for the Progress Scout agent."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import parse_course_credits


def _normalize_course_number(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(8) if digits else str(value).strip()


def _remaining_mandatory_numbers(graduation_progress: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for entry in graduation_progress.get("remainingMandatoryCourses") or []:
        number = entry.get("courseNumber") or entry.get("number")
        if number is not None:
            numbers.add(_normalize_course_number(str(number)))
    for bucket in graduation_progress.get("requirementProgress") or []:
        for entry in bucket.get("remainingCourses") or []:
            number = entry.get("courseNumber") or entry.get("number")
            if number is not None:
                numbers.add(_normalize_course_number(str(number)))
    return numbers


def _evaluate_graduation_progress_impact(
    *,
    graduation_progress: dict[str, Any],
    course_ids: list[str],
    engine: AcademicGraphEngine,
) -> tuple[int, float, list[dict[str, Any]], list[str]]:
    """Score plan against real graduation-progress baseline (when available)."""
    references: list[str] = []
    critiques: list[dict[str, Any]] = []

    remaining = _remaining_mandatory_numbers(graduation_progress)
    if not remaining:
        references.append("progress:graduation_baseline=complete_or_unavailable")
        return 0, 0.0, critiques, references

    planned_numbers = {_normalize_course_number(course_id) for course_id in course_ids}
    satisfied = sorted(planned_numbers.intersection(remaining))
    references.append(f"progress:mandatory_satisfied={len(satisfied)}")
    references.append(f"progress:mandatory_remaining={len(remaining)}")

    credits_remaining = float(graduation_progress.get("creditsRemaining") or 0)
    plan_credits = sum(parse_course_credits(engine, course_id) for course_id in course_ids)
    references.append(f"progress:baseline_credits_remaining={credits_remaining}")
    references.append(f"progress:plan_credits={plan_credits}")

    if satisfied:
        references.append(f"progress:satisfies_mandatory={','.join(satisfied)}")
    elif course_ids:
        critiques.append(
            {
                "type": "no_mandatory_progress",
                "message": (
                    "Plan does not include any remaining mandatory degree requirements "
                    "from the student's graduation progress baseline."
                ),
            }
        )

    mandatory_ratio = len(satisfied) / max(1, min(len(remaining), 4))
    credit_ratio = min(1.0, plan_credits / max(1.0, credits_remaining)) if credits_remaining else 0.5
    graduation_score = min(1.0, mandatory_ratio * 0.7 + credit_ratio * 0.3)
    return len(satisfied), graduation_score, critiques, references


def _downstream_unlock_count(
    engine: AcademicGraphEngine,
    course_id: str,
    completed_courses: list[str],
) -> int:
    """Count catalog courses that list course_id as a direct prerequisite and are not yet eligible."""
    if not engine._built:
        return 0

    completed_set = set(completed_courses)
    unlock = 0
    for node_id in engine.course_catalog:
        if node_id in completed_set:
            continue
        eligible, _missing = engine.evaluate_eligibility(node_id, completed_courses)
        if eligible:
            continue
        if course_id in _missing:
            unlock += 1
    return unlock


def evaluate_degree_progress(
    *,
    engine: AcademicGraphEngine,
    course_ids: list[str],
    completed_courses: list[str],
    user_context: dict[str, Any],
    graduation_progress: dict[str, Any] | None = None,
) -> tuple[float, int, list[dict[str, Any]], list[str]]:
    """
    Return (progress_score, unlock_count, critiques, references).

    Soft critic only — never hard-vetoes.
    """
    references: list[str] = []
    critiques: list[dict[str, Any]] = []
    completed_set = set(completed_courses)

    if not course_ids:
        critiques.append(
            {
                "type": "no_progress_courses",
                "message": "Plan includes no courses that advance degree progress.",
            }
        )
        return 0.0, 0, critiques, references

    redundant = [course_id for course_id in course_ids if course_id in completed_set]
    if redundant:
        critiques.append(
            {
                "type": "already_completed",
                "courseIds": redundant,
                "message": (
                    f"Plan repeats already completed course(s): {', '.join(redundant)}."
                ),
            }
        )
        references.append(f"progress:redundant={len(redundant)}")

    unlock_total = 0
    credit_total = 0.0
    for course_id in course_ids:
        unlock_total += _downstream_unlock_count(engine, course_id, completed_courses)
        credit_total += parse_course_credits(engine, course_id)

    references.append(f"progress:unlock_count={unlock_total}")
    references.append(f"progress:credits={credit_total}")

    track_slug = user_context.get("track_slug")
    if track_slug:
        references.append(f"progress:track_slug={track_slug}")

    graduation_progress = graduation_progress or user_context.get("graduation_progress")
    graduation_score = 0.0
    mandatory_satisfied = 0
    if isinstance(graduation_progress, dict):
        mandatory_satisfied, graduation_score, grad_critiques, grad_refs = (
            _evaluate_graduation_progress_impact(
                graduation_progress=graduation_progress,
                course_ids=course_ids,
                engine=engine,
            )
        )
        critiques.extend(grad_critiques)
        references.extend(grad_refs)
        source = (
            "graduation_progress_projection"
            if graduation_progress.get("projectionMeta")
            else "graduation_progress_api"
        )
        references.append(f"progress:source={source}")
    else:
        references.append("progress:source=graph_heuristic")

    if unlock_total == 0 and len(course_ids) >= 1 and mandatory_satisfied == 0:
        critiques.append(
            {
                "type": "low_unlock_value",
                "message": (
                    "Plan courses do not unlock additional downstream degree requirements "
                    "in the active catalog graph."
                ),
            }
        )

    graph_score = min(1.0, (unlock_total / 5.0) + min(1.0, credit_total / 12.0) * 0.3)
    if isinstance(graduation_progress, dict):
        progress_score = min(1.0, graph_score * 0.35 + graduation_score * 0.65)
    else:
        progress_score = graph_score

    if any(critique.get("type") == "no_mandatory_progress" for critique in critiques):
        progress_score = min(progress_score, 0.22)

    if not critiques:
        references.append("progress:aligned")

    return progress_score, unlock_total, critiques, references
