"""Rank eligible catalog courses by the student's degree path and graduation progress."""

from __future__ import annotations

from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.api_catalog import (
    api_offered_course_numbers,
    is_course_in_active_catalog,
    uses_api_semester_catalog,
)
from app.services.plan_progress import _normalize_course_number, _remaining_mandatory_numbers
from app.services.planner_support import parse_course_credits, sum_plan_credits
from app.services.user_data_quality import normalize_completed_course_numbers


def extract_path_priority_course_ids(user_context: dict[str, Any]) -> list[str]:
    """Ordered remaining requirement course numbers from graduation progress."""
    graduation = user_context.get("graduation_progress")
    if not isinstance(graduation, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def append(number: str) -> None:
        normalized = _normalize_course_number(number)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        ordered.append(normalized)

    for entry in graduation.get("remainingMandatoryCourses") or []:
        if not isinstance(entry, dict):
            continue
        append(str(entry.get("courseNumber") or entry.get("number") or ""))

    for bucket in graduation.get("requirementProgress") or []:
        if not isinstance(bucket, dict):
            continue
        if bucket.get("status") == "satisfied":
            continue
        for entry in bucket.get("remainingCourses") or []:
            if not isinstance(entry, dict):
                continue
            append(str(entry.get("courseNumber") or entry.get("number") or ""))

    for number in sorted(_remaining_mandatory_numbers(graduation)):
        append(number)

    return ordered


def enrich_user_context_with_graduation_path(user_context: dict[str, Any]) -> dict[str, Any]:
    """Merge transcript completions and expose path priority courses for planners."""
    graduation = user_context.get("graduation_progress")
    if not isinstance(graduation, dict):
        return user_context

    completed = {
        _normalize_course_number(str(course_id))
        for course_id in user_context.get("completed_courses") or []
        if str(course_id).strip()
    }

    for entry in graduation.get("completedMandatoryCourses") or []:
        if not isinstance(entry, dict):
            continue
        number = entry.get("courseNumber") or entry.get("number")
        if number is not None:
            completed.add(_normalize_course_number(str(number)))

    for bucket in graduation.get("requirementProgress") or []:
        if not isinstance(bucket, dict):
            continue
        for entry in bucket.get("completedCourses") or []:
            if not isinstance(entry, dict):
                continue
            number = entry.get("courseNumber") or entry.get("number")
            if number is not None:
                completed.add(_normalize_course_number(str(number)))

    updated = dict(user_context)
    updated["completed_courses"] = normalize_completed_course_numbers(sorted(completed))
    updated["path_priority_courses"] = extract_path_priority_course_ids(updated)
    return updated


def build_path_context_summary(user_context: dict[str, Any]) -> dict[str, Any]:
    """Serializable path metadata for finalDecision and UI."""
    graduation = user_context.get("graduation_progress")
    summary: dict[str, Any] = {
        "trackSlug": user_context.get("track_slug"),
        "planSemesterCode": user_context.get("plan_semester_code"),
        "priorityRemainingCourses": list(user_context.get("path_priority_courses") or []),
        "completedCourseCount": len(user_context.get("completed_courses") or []),
    }
    transcript_stats = user_context.get("transcript_stats")
    if isinstance(transcript_stats, dict):
        summary["transcriptStats"] = transcript_stats
    if isinstance(graduation, dict):
        summary["creditsRemaining"] = graduation.get("creditsRemaining")
        summary["remainingMandatoryCount"] = len(graduation.get("remainingMandatoryCourses") or [])

    data_quality = user_context.get("data_quality")
    if isinstance(data_quality, dict):
        summary["dataQuality"] = data_quality
    context_source = user_context.get("context_source")
    if isinstance(context_source, str) and context_source.strip():
        summary["contextSource"] = context_source.strip()
    planning_source = user_context.get("planning_source")
    if isinstance(planning_source, str) and planning_source.strip():
        summary["planningSource"] = planning_source.strip()
    if "planning_ready" in user_context:
        summary["planningReady"] = bool(user_context.get("planning_ready"))
    planning_context = user_context.get("planning_context")
    if isinstance(planning_context, dict):
        summary["transcriptCourseCount"] = len(planning_context.get("transcriptCourseNumbers") or [])
        summary["pathPriorityCourseCount"] = len(
            planning_context.get("pathPriorityCourseNumbers") or []
        )
    catalog_source = user_context.get("catalog_source")
    if isinstance(catalog_source, str) and catalog_source.strip():
        summary["catalogSource"] = catalog_source.strip()
    api_catalog = user_context.get("api_semester_catalog")
    if isinstance(api_catalog, dict) and api_catalog.get("status") == "ok":
        summary["offeredCourseCount"] = len(api_catalog.get("offeredCourseNumbers") or [])
        summary["apiSuggestedCourseCount"] = len(user_context.get("api_suggested_course_numbers") or [])
    return summary


def _course_in_catalog(
    engine: AcademicGraphEngine,
    course_id: str,
    user_context: dict[str, Any] | None = None,
) -> bool:
    return is_course_in_active_catalog(
        engine=engine,
        course_id=course_id,
        user_context=user_context,
    )


def list_path_relevant_eligible_courses(
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any],
    *,
    limit: int = 50,
) -> tuple[list[str], list[str]]:
    """
    Eligible courses ordered by degree-path relevance.

    Priority: remaining mandatory/requirement courses, then other eligible catalog courses.
    """
    if not engine._built:
        engine.build_graph()

    completed = set(completed_courses)
    priority_ids = list(user_context.get("path_priority_courses") or [])
    if not priority_ids:
        priority_ids = extract_path_priority_course_ids(user_context)

    references: list[str] = []
    if user_context.get("track_slug"):
        references.append(f"path:track_slug={user_context['track_slug']}")
    references.append(f"path:priority_remaining={len(priority_ids)}")

    eligible_priority: list[str] = []
    for course_id in priority_ids:
        if course_id in completed or not _course_in_catalog(engine, course_id, user_context):
            continue
        ok, _missing = engine.evaluate_eligibility(course_id, completed_courses)
        if ok:
            eligible_priority.append(course_id)

    references.append(f"path:eligible_priority={len(eligible_priority)}")

    eligible_other: list[str] = []
    priority_set = set(eligible_priority)
    if uses_api_semester_catalog(user_context):
        catalog_candidates = sorted(api_offered_course_numbers(user_context) or set())
        references.append("catalog:source=api_mongo")
    else:
        catalog_candidates = list(engine.course_catalog.keys())

    for course_id in catalog_candidates:
        if course_id in completed or course_id in priority_set:
            continue
        ok, _missing = engine.evaluate_eligibility(course_id, completed_courses)
        if ok:
            eligible_other.append(course_id)

    def _other_sort_key(course_id: str) -> tuple[int, str]:
        unlock_score = 0
        for priority_id in priority_ids:
            if priority_id in completed:
                continue
            eligible, missing = engine.evaluate_eligibility(priority_id, completed_courses)
            if not eligible and course_id in missing:
                unlock_score += 1
        return (-unlock_score, course_id)

    eligible_other.sort(key=_other_sort_key)

    ordered = eligible_priority + eligible_other[: max(0, limit - len(eligible_priority))]
    references.append(f"path:eligible_total={len(ordered)}")
    return ordered, references


def select_path_aligned_plan_courses(
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any],
    *,
    max_credits: float,
    max_courses: int = 5,
) -> tuple[list[str], list[str]]:
    """Pick a credit-bounded plan from path-relevant eligible courses."""
    ranked, references = list_path_relevant_eligible_courses(
        engine,
        completed_courses,
        user_context,
    )
    priority_ids = {
        _normalize_course_number(course_id)
        for course_id in (user_context.get("path_priority_courses") or [])
    }
    if not priority_ids:
        priority_ids = set(extract_path_priority_course_ids(user_context))

    selection_pool = [course_id for course_id in ranked if course_id in priority_ids] if priority_ids else ranked
    if priority_ids and not selection_pool:
        selection_pool = ranked
        references.append("path:selection_pool=fallback_to_ranked")
    references.append(f"path:selection_pool={len(selection_pool)}")

    selected: list[str] = []
    running_credits = 0.0
    for course_id in selection_pool:
        credits = parse_course_credits(engine, course_id, user_context=user_context)
        if running_credits + credits > max_credits:
            continue
        selected.append(course_id)
        running_credits += credits
        if len(selected) >= max_courses:
            break

    references.append(f"path:selected_count={len(selected)}")
    if selected:
        references.append(
            f"path:selected_credits={sum_plan_credits(engine, selected, user_context=user_context)}"
        )
    return selected, references


def score_plan_path_relevance(
    course_ids: list[str],
    user_context: dict[str, Any],
) -> tuple[float, int, list[str]]:
    """Score how well a plan covers remaining degree-path requirements (0–1)."""
    references: list[str] = []
    priority_ids = list(user_context.get("path_priority_courses") or [])
    if not priority_ids:
        priority_ids = extract_path_priority_course_ids(user_context)

    if not priority_ids:
        references.append("path:score=no_priority_baseline")
        return 0.5, 0, references

    if not course_ids:
        references.append("path:score=empty_plan")
        return 0.0, 0, references

    planned = {_normalize_course_number(course_id) for course_id in course_ids}
    priority_set = {_normalize_course_number(course_id) for course_id in priority_ids}
    hits = sorted(planned.intersection(priority_set))
    hit_count = len(hits)

    references.append(f"path:score_priority_total={len(priority_set)}")
    references.append(f"path:score_hits={hit_count}")
    if hits:
        references.append(f"path:score_hit_courses={','.join(hits[:8])}")

    coverage = hit_count / min(len(priority_set), 4)
    precision = hit_count / len(planned)
    score = min(1.0, coverage * 0.65 + precision * 0.35)
    return score, hit_count, references


def _trim_plan_to_limits(
    engine: AcademicGraphEngine,
    course_ids: list[str],
    *,
    max_credits: float,
    max_courses: int,
    user_context: dict[str, Any] | None = None,
) -> list[str]:
    selected: list[str] = []
    running_credits = 0.0
    for course_id in course_ids:
        credits = parse_course_credits(engine, course_id, user_context=user_context)
        if running_credits + credits > max_credits:
            continue
        selected.append(course_id)
        running_credits += credits
        if len(selected) >= max_courses:
            break
    return selected


def reconcile_proposal_with_path_alignment(
    proposed: list[str],
    *,
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any],
    max_credits: float,
    max_courses: int = 5,
    explicit_course_ids: list[str] | None = None,
) -> tuple[list[str], list[str], str]:
    """
    Align planner output with remaining degree requirements.

    Replaces or merges LLM/deterministic proposals that ignore the student's path.
    """
    references: list[str] = []
    path_priority = list(user_context.get("path_priority_courses") or [])
    if not path_priority:
        path_priority = extract_path_priority_course_ids(user_context)

    if not path_priority:
        references.append("path:reconcile=skipped_no_baseline")
        return list(proposed), references, "skipped"

    path_aligned, path_refs = select_path_aligned_plan_courses(
        engine,
        completed_courses,
        user_context,
        max_credits=max_credits,
        max_courses=max_courses,
    )
    references.extend(path_refs)

    proposed_norm = [_normalize_course_number(course_id) for course_id in proposed]
    explicit = {
        _normalize_course_number(course_id)
        for course_id in (explicit_course_ids or [])
        if str(course_id).strip()
    }

    if explicit:
        merged: list[str] = []
        seen: set[str] = set()
        for course_id in [*path_aligned, *proposed_norm]:
            if course_id not in explicit and course_id not in path_aligned:
                continue
            if course_id in seen:
                continue
            seen.add(course_id)
            merged.append(course_id)
        if not merged:
            merged = list(dict.fromkeys([*path_aligned, *proposed_norm]))
        trimmed = _trim_plan_to_limits(
            engine,
            merged,
            max_credits=max_credits,
            max_courses=max_courses,
            user_context=user_context,
        )
        references.append("path:reconcile=explicit_goal_merge")
        return trimmed, references, "explicit_merge"

    if not path_aligned:
        ranked, ranked_refs = list_path_relevant_eligible_courses(
            engine,
            completed_courses,
            user_context,
            limit=max(max_courses * 4, 12),
        )
        references.extend(ranked_refs)
        fallback = _trim_plan_to_limits(
            engine,
            ranked,
            max_credits=max_credits,
            max_courses=max_courses,
            user_context=user_context,
        )
        if fallback:
            references.append("path:reconcile=replaced_ranked_fallback")
            return fallback, references, "replaced"
        references.append("path:reconcile=kept_proposed_no_aligned_plan")
        return proposed_norm, references, "kept"

    proposed_score, proposed_hits, proposed_score_refs = score_plan_path_relevance(
        proposed_norm,
        user_context,
    )
    aligned_score, aligned_hits, aligned_score_refs = score_plan_path_relevance(
        path_aligned,
        user_context,
    )
    references.extend(proposed_score_refs)
    references.extend(aligned_score_refs)

    priority_set = {_normalize_course_number(course_id) for course_id in path_priority}
    merged_ids = list(dict.fromkeys([*path_aligned, *proposed_norm]))
    trimmed = _trim_plan_to_limits(
        engine,
        merged_ids,
        max_credits=max_credits,
        max_courses=max_courses,
        user_context=user_context,
    )
    merged_hits = len(
        {_normalize_course_number(course_id) for course_id in trimmed}.intersection(priority_set)
    )

    if proposed_hits == 0 and aligned_hits > 0:
        references.append("path:reconcile=replaced_zero_path_hits")
        return path_aligned, references, "replaced"

    if merged_hits > proposed_hits or aligned_score >= proposed_score:
        references.append(
            f"path:reconcile=merged_priority_first aligned={aligned_score:.3f} proposed={proposed_score:.3f}"
        )
        return trimmed, references, "merged"

    references.append("path:reconcile=kept_proposed")
    return proposed_norm, references, "kept"
