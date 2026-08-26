"""Unit tests for the term-plan service (DB wiring around the pure `plan_terms`).

The pure orchestration is covered in `test_term_plan.py`; here we test the wiring:
context/error passthrough, candidate resolution, the credit-cap default + ceiling,
and that a resolved, offered candidate reaches a placement.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.term_plan_service import build_term_plan

_CTX = "app.services.term_plan_service.load_planning_context"
_OFFERINGS = "app.services.term_plan_service._load_term_offerings"


def _context(catalog_courses: list[dict] | None = None, preferences: dict | None = None) -> dict:
    return {
        "status": "ok",
        "profile": {"preferences": preferences or {}},
        "degree": {"programCode": "009216-1-000"},
        "catalogCourses": catalog_courses or [],
        "completedCourseRecords": [],
        "hardRequirements": [],
        "poolDocuments": [],
        "semesterMatrixDocuments": [],
        "graduationProgress": {"buckets": []},
    }


def _offering(number: str) -> dict:
    return {
        "courseNumber": number,
        "academicYear": 2025,
        "semesterCode": 200,
        "scheduleGroups": [{"day": "Sunday", "time": "09:00-11:00", "type": "lecture"}],
        "examDates": {"moedA": "2026-02-01"},
    }


@pytest.mark.asyncio
async def test_rejects_empty_semester_codes():
    result = await build_term_plan(
        AsyncMock(), "u1", semester_codes=[], candidates=[{"courseNumber": "10001"}]
    )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_rejects_empty_candidates():
    result = await build_term_plan(
        AsyncMock(), "u1", semester_codes=["2025-2"], candidates=[]
    )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_rejects_an_invalid_semester_code():
    result = await build_term_plan(
        AsyncMock(), "u1", semester_codes=["2025-9"], candidates=[{"courseNumber": "10001"}]
    )
    assert result["status"] == "validation_error"
    assert "Invalid semesterCode" in result["errors"][0]


@pytest.mark.asyncio
async def test_propagates_a_planning_context_error():
    with patch(_CTX, new_callable=AsyncMock, return_value={"status": "profile_not_found"}):
        result = await build_term_plan(
            AsyncMock(), "u1", semester_codes=["2025-2"], candidates=[{"courseNumber": "10001"}]
        )
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_an_unknown_candidate_number_is_reported_unscheduled():
    with (
        patch(_CTX, new_callable=AsyncMock, return_value=_context(catalog_courses=[])),
        patch(_OFFERINGS, new_callable=AsyncMock, return_value={}),
    ):
        result = await build_term_plan(
            AsyncMock(), "u1", semester_codes=["2025-2"], candidates=[{"courseNumber": "99999999"}]
        )

    assert result["status"] == "ok"
    reasons = {row["courseNumber"]: row["reason"] for row in result["unscheduled"]}
    assert "99999999" in reasons
    assert "catalog" in reasons["99999999"].lower()


@pytest.mark.asyncio
async def test_places_a_resolved_offered_candidate_and_defaults_the_cap():
    catalog = [{"_id": "c1", "courseNumber": "10001", "title": "A", "credits": 3, "prerequisites": []}]
    with (
        patch(_CTX, new_callable=AsyncMock, return_value=_context(catalog_courses=catalog)),
        patch(_OFFERINGS, new_callable=AsyncMock, return_value={"10001": _offering("10001")}),
    ):
        result = await build_term_plan(
            AsyncMock(),
            "u1",
            semester_codes=["2025-2"],
            candidates=[{"courseNumber": "10001", "category": "mandatory"}],
        )

    assert result["status"] == "ok"
    assert result["maxCredits"] == 18.0  # profile has no preference -> default
    placed = [c["courseNumber"] for term in result["terms"] for c in term["placedCourses"]]
    assert placed == ["10001"]
    assert result["terms"][0]["weeklySchedule"]["status"] == "valid"


@pytest.mark.asyncio
async def test_a_bare_term_name_plans_and_echoes_its_label():
    """The agent names a term ("winter"); the plan comes back split on that same
    label, and the offering lookup runs against the resolved (year, term) keys."""
    catalog = [{"_id": "c1", "courseNumber": "10001", "title": "A", "credits": 3, "prerequisites": []}]
    with (
        patch(_CTX, new_callable=AsyncMock, return_value=_context(catalog_courses=catalog)),
        patch(_OFFERINGS, new_callable=AsyncMock, return_value={"10001": _offering("10001")}) as offerings,
    ):
        result = await build_term_plan(
            AsyncMock(),
            "u1",
            semester_codes=["winter"],
            candidates=[{"courseNumber": "10001", "category": "mandatory"}],
            current_year=2025,
        )

    assert result["status"] == "ok"
    assert result["terms"][0]["semesterCode"] == "winter"
    # winter -> preferred_year 2025, technion semesterCode 200.
    assert offerings.await_args.args[2:] == (2025, 200)
    placed = [c["courseNumber"] for term in result["terms"] for c in term["placedCourses"]]
    assert placed == ["10001"]


@pytest.mark.asyncio
async def test_explicit_max_credits_is_clamped_to_the_ceiling():
    with (
        patch(_CTX, new_callable=AsyncMock, return_value=_context(preferences={"maxCreditsPerSemester": 20})),
        patch(_OFFERINGS, new_callable=AsyncMock, return_value={}),
    ):
        result = await build_term_plan(
            AsyncMock(),
            "u1",
            semester_codes=["2025-2"],
            candidates=[{"courseNumber": "10001"}],
            max_credits=50.0,  # above the 40 ceiling
        )

    assert result["maxCredits"] == 40.0
