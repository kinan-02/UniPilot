"""Deterministic watchdog checks (AGT-8) — no LLM logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.planning.academic_risk_analyzer import analyze_academic_risks
from app.services.academic_risk_service import build_plan_view_from_semester_plan

WatchdogNudgeType = Literal["pace", "prereq", "risk"]
WatchdogSeverity = Literal["high", "medium"]


@dataclass(frozen=True)
class WatchdogNudge:
    nudge_type: WatchdogNudgeType
    severity: WatchdogSeverity
    title: str
    body: str
    evidence: dict[str, Any]
    dedupe_key: str
    plan_id: str | None = None
    risk_analysis_id: str | None = None


def parse_plan_semester_code(semester_code: str | None) -> tuple[int, int] | None:
    """Return (calendar_year, term_index 1-3) from codes like 2025-201 or 2025-2."""
    if not semester_code or not isinstance(semester_code, str):
        return None

    cleaned = semester_code.strip()
    if "-" not in cleaned:
        return None

    year_part, term_part = cleaned.rsplit("-", 1)
    try:
        year = int(year_part)
        term = int(term_part)
    except ValueError:
        return None

    if term >= 200:
        term_index = {200: 1, 201: 2, 202: 3}.get(term, 1)
    else:
        term_index = max(1, min(3, term))
    return year, term_index


def program_semester_index(catalog_year: int | None, semester_code: str | None) -> int | None:
    if catalog_year is None:
        return None
    parsed = parse_plan_semester_code(semester_code)
    if parsed is None:
        return None
    year, term_index = parsed
    return max(1, (year - int(catalog_year)) * 3 + term_index)


def _completed_course_numbers(graduation_progress: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for course in graduation_progress.get("completedMandatoryCourses") or []:
        if not isinstance(course, dict):
            continue
        number = course.get("courseNumber")
        if number is not None:
            numbers.add(str(number))
    return numbers


def _matrix_courses_due_by_semester(
    semester_matrix_documents: list[dict[str, Any]],
    *,
    max_matrix_semester: int,
) -> set[str]:
    due_numbers: set[str] = set()
    for document in semester_matrix_documents:
        expression = document.get("ruleExpression") or {}
        semester = expression.get("semester")
        if semester is None or int(semester) > max_matrix_semester:
            continue
        for reference in document.get("courseReferences") or []:
            number = reference.get("courseNumber")
            if number is not None:
                due_numbers.add(str(number))
    return due_numbers


def check_mandatory_courses_remaining(
    *,
    profile: dict[str, Any],
    graduation_progress: dict[str, Any],
) -> WatchdogNudge | None:
    """Alert when multiple required curriculum courses are still open."""
    remaining = graduation_progress.get("remainingMandatoryCourses") or []
    if len(remaining) < 2:
        return None

    numbers = [
        str(course.get("courseNumber"))
        for course in remaining
        if isinstance(course, dict) and course.get("courseNumber")
    ]
    preview = ", ".join(numbers[:4])
    suffix = "…" if len(numbers) > 4 else ""
    degree_id = profile.get("degreeId")
    return WatchdogNudge(
        nudge_type="pace",
        severity="high" if len(remaining) >= 4 else "medium",
        title="Required courses still open",
        body=(
            f"You still have {len(remaining)} mandatory courses to complete "
            f"(e.g. {preview}{suffix}). Review your graduation progress."
        ),
        evidence={
            "remainingMandatoryCount": len(remaining),
            "remainingMandatoryCourseNumbers": numbers,
        },
        dedupe_key=f"mandatory-remaining:{degree_id or 'unknown'}",
    )


def check_credits_behind_track(
    *,
    profile: dict[str, Any],
    graduation_progress: dict[str, Any],
    semester_matrix_documents: list[dict[str, Any]],
) -> WatchdogNudge | None:
    catalog_year = profile.get("catalogYear")
    current_semester = profile.get("currentSemesterCode")
    program_semester = program_semester_index(catalog_year, current_semester)
    if program_semester is None or program_semester < 2:
        return None

    matrix_semesters = [
        int((doc.get("ruleExpression") or {}).get("semester"))
        for doc in semester_matrix_documents
        if (doc.get("ruleExpression") or {}).get("semester") is not None
    ]
    if not matrix_semesters:
        completion = float(graduation_progress.get("completionPercentage") or 0)
        expected = min(95.0, program_semester * 12.5)
        if completion + 15 < expected:
            return WatchdogNudge(
                nudge_type="pace",
                severity="medium",
                title="Degree progress is behind expected pace",
                body=(
                    f"You are in program semester {program_semester} but only "
                    f"{completion:.0f}% complete. Review your graduation progress and plan."
                ),
                evidence={
                    "programSemesterIndex": program_semester,
                    "completionPercentage": completion,
                    "expectedCompletionPercentage": expected,
                    "currentSemesterCode": current_semester,
                },
                dedupe_key=f"pace:{catalog_year}:{current_semester}",
            )
        return None

    max_matrix_semester = max(matrix_semesters)
    due_by_now = max(1, min(program_semester - 1, max_matrix_semester))
    due_numbers = _matrix_courses_due_by_semester(
        semester_matrix_documents,
        max_matrix_semester=due_by_now,
    )
    if not due_numbers:
        return None

    completed_numbers = _completed_course_numbers(graduation_progress)
    missing = sorted(number for number in due_numbers if number not in completed_numbers)
    if len(missing) < 1:
        return None

    severity: WatchdogSeverity = "high" if len(missing) >= 3 else "medium"
    preview = ", ".join(missing[:4])
    suffix = "…" if len(missing) > 4 else ""
    return WatchdogNudge(
        nudge_type="pace",
        severity=severity,
        title="Mandatory curriculum is behind schedule",
        body=(
            f"By semester {program_semester}, {len(missing)} expected mandatory courses are still open "
            f"(e.g. {preview}{suffix}). Adjust your plan or speak with your faculty advisor."
        ),
        evidence={
            "programSemesterIndex": program_semester,
            "missingMandatoryCourseNumbers": missing,
            "dueByMatrixSemester": due_by_now,
            "currentSemesterCode": current_semester,
        },
        dedupe_key=f"pace:{catalog_year}:{current_semester}",
    )


def check_unmet_prerequisites_on_plan(
    *,
    plan_document: dict[str, Any],
    planning_context: dict[str, Any],
) -> WatchdogNudge | None:
    plan_view = build_plan_view_from_semester_plan(plan_document)
    analysis = analyze_academic_risks(
        profile=planning_context["profile"],
        degree=planning_context["degree"],
        catalog_courses=planning_context["catalogCourses"],
        graduation_progress=planning_context["graduationProgress"],
        completed_course_records=planning_context["completedCourseRecords"],
        plan_view=plan_view,
        pool_documents=planning_context.get("poolDocuments") or [],
    )

    prereq_risks = [
        risk
        for risk in analysis.get("risks") or []
        if risk.get("riskType") == "unmet_prerequisites" and risk.get("severity") == "high"
    ]
    if not prereq_risks:
        return None

    primary = prereq_risks[0]
    plan_id = str(plan_document.get("_id"))
    course_number = None
    related = primary.get("relatedCourseIds") or []
    if related:
        course_number = str(related[0])

    return WatchdogNudge(
        nudge_type="prereq",
        severity="high",
        title=primary.get("title") or "Planned course has unmet prerequisites",
        body=primary.get("explanation")
        or "A course on your semester plan requires prerequisites you have not completed.",
        evidence={
            "riskCount": len(prereq_risks),
            "planId": plan_id,
            "semesterCode": plan_view.get("semesterCode"),
            "risks": prereq_risks[:3],
        },
        dedupe_key=f"prereq:{plan_id}:{course_number or 'plan'}",
        plan_id=plan_id,
    )


def check_open_high_severity_risks(
  analysis_document: dict[str, Any],
) -> WatchdogNudge | None:
    if analysis_document.get("status") != "open":
        return None

    summary = analysis_document.get("summary") or {}
    if summary.get("highestSeverity") != "high":
        return None

    analysis_id = str(analysis_document.get("_id"))
    top_risks = [
        {
            "severity": risk.get("severity"),
            "title": risk.get("title"),
            "riskType": risk.get("riskType"),
        }
        for risk in (analysis_document.get("risks") or [])[:3]
        if isinstance(risk, dict)
    ]
    primary = (analysis_document.get("risks") or [{}])[0]
    return WatchdogNudge(
        nudge_type="risk",
        severity="high",
        title=primary.get("title") or "High-severity academic risk detected",
        body=primary.get("explanation")
        or "Your latest academic risk analysis flagged high-severity issues.",
        evidence={
            "analysisId": analysis_id,
            "summary": summary,
            "topRisks": top_risks,
        },
        dedupe_key=f"risk:{analysis_id}",
        risk_analysis_id=analysis_id,
        plan_id=(
            str(analysis_document["planId"])
            if analysis_document.get("planId") is not None
            else None
        ),
    )


def collect_watchdog_nudges(
    *,
    profile: dict[str, Any],
    graduation_progress: dict[str, Any],
    semester_matrix_documents: list[dict[str, Any]],
    latest_plan: dict[str, Any] | None,
    latest_risk_analysis: dict[str, Any] | None,
    planning_context: dict[str, Any] | None,
) -> list[WatchdogNudge]:
    nudges: list[WatchdogNudge] = []

    mandatory = check_mandatory_courses_remaining(
        profile=profile,
        graduation_progress=graduation_progress,
    )
    if mandatory:
        nudges.append(mandatory)

    pace = check_credits_behind_track(
        profile=profile,
        graduation_progress=graduation_progress,
        semester_matrix_documents=semester_matrix_documents,
    )
    if pace:
        nudges.append(pace)

    if latest_plan and planning_context and planning_context.get("status") == "ok":
        prereq = check_unmet_prerequisites_on_plan(
            plan_document=latest_plan,
            planning_context=planning_context,
        )
        if prereq:
            nudges.append(prereq)

    if latest_risk_analysis:
        risk = check_open_high_severity_risks(latest_risk_analysis)
        if risk:
            nudges.append(risk)

    return nudges
