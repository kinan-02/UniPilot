"""Deterministic synthetic-world oracles for offline eval (Phase 23)."""

from __future__ import annotations

from typing import Any


def _courses(world: dict[str, Any]) -> dict[str, Any]:
    return world.get("courses") if isinstance(world.get("courses"), dict) else {}


def _student(world: dict[str, Any]) -> dict[str, Any]:
    return world.get("student") if isinstance(world.get("student"), dict) else {}


def _degree(world: dict[str, Any]) -> dict[str, Any]:
    return world.get("degree") if isinstance(world.get("degree"), dict) else {}


def compute_graduation_oracle_facts(synthetic_world: dict[str, Any]) -> dict[str, Any]:
    """Credits, missing mandatory courses, missing credits."""
    try:
        courses = _courses(synthetic_world)
        student = _student(synthetic_world)
        degree = _degree(synthetic_world)

        completed = [str(code) for code in (student.get("completedCourses") or [])]
        completed_credits = sum(float(courses.get(code, {}).get("credits") or 0) for code in completed)

        mandatory = [str(code) for code in (degree.get("mandatoryCourses") or [])]
        missing_mandatory = [code for code in mandatory if code not in completed]

        total_required = float(degree.get("totalRequiredCredits") or 0)
        missing_credits = max(0.0, total_required - completed_credits)

        return {
            "completedCredits": completed_credits,
            "missingMandatoryCourses": missing_mandatory,
            "missingCredits": missing_credits,
        }
    except Exception:  # noqa: BLE001
        return {}


def compute_prerequisite_oracle_facts(synthetic_world: dict[str, Any]) -> dict[str, Any]:
    try:
        courses = _courses(synthetic_world)
        student = _student(synthetic_world)
        completed = {str(code) for code in (student.get("completedCourses") or [])}
        satisfied: dict[str, bool] = {}
        for code, meta in courses.items():
            if not isinstance(meta, dict):
                continue
            prereqs = [str(item) for item in (meta.get("prerequisites") or [])]
            satisfied[str(code)] = all(prereq in completed for prereq in prereqs)
        return {"satisfiedPrerequisites": satisfied}
    except Exception:  # noqa: BLE001
        return {"satisfiedPrerequisites": {}}


def compute_requirement_bucket_oracle_facts(synthetic_world: dict[str, Any]) -> dict[str, Any]:
    try:
        buckets = synthetic_world.get("requirementBuckets")
        if not isinstance(buckets, list):
            return {}
        student = _student(synthetic_world)
        completed = {str(code) for code in (student.get("completedCourses") or [])}
        unsatisfied: list[str] = []
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            required = {str(code) for code in (bucket.get("requiredCourses") or [])}
            if required and not required.issubset(completed):
                unsatisfied.append(str(bucket.get("name") or "bucket"))
        return {"unsatisfiedRequirementBuckets": unsatisfied}
    except Exception:  # noqa: BLE001
        return {}


def compute_course_lookup_oracle_facts(synthetic_world: dict[str, Any], *, course_code: str | None = None) -> dict[str, Any]:
    try:
        courses = _courses(synthetic_world)
        if course_code and course_code in courses:
            meta = courses[course_code]
            return {"courseExists": True, "courseCredits": meta.get("credits") if isinstance(meta, dict) else None}
        return {"courseExists": course_code in courses if course_code else False}
    except Exception:  # noqa: BLE001
        return {"courseExists": False}


def compute_semester_plan_oracle_facts(synthetic_world: dict[str, Any]) -> dict[str, Any]:
    try:
        plan = synthetic_world.get("semesterPlan")
        if not isinstance(plan, dict):
            return {}
        max_credits = float(plan.get("maxCredits") or 0)
        selected = plan.get("selectedCourses") or []
        total = 0.0
        courses = _courses(synthetic_world)
        for code in selected:
            total += float(courses.get(str(code), {}).get("credits") or 0)
        return {
            "plannedCredits": total,
            "creditLimitExceeded": bool(max_credits and total > max_credits),
        }
    except Exception:  # noqa: BLE001
        return {}


def derive_oracle_facts(synthetic_world: dict[str, Any]) -> dict[str, Any]:
    """Aggregate all supported oracle facts for a synthetic world."""
    facts: dict[str, Any] = {}
    facts.update(compute_graduation_oracle_facts(synthetic_world))
    facts.update(compute_prerequisite_oracle_facts(synthetic_world))
    facts.update(compute_requirement_bucket_oracle_facts(synthetic_world))
    facts.update(compute_semester_plan_oracle_facts(synthetic_world))
    return facts


def check_oracle_contradictions(
    *,
    expected_facts: dict[str, Any],
    derived_facts: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    for key, expected in expected_facts.items():
        if key not in derived_facts:
            continue
        actual = derived_facts[key]
        if actual != expected:
            failures.append(f"oracle_mismatch:{key}")
    return failures
