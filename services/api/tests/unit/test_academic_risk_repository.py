"""Unit tests for academic_risk_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.academic_risk_repository import (
    _format_datetime,
    build_academic_risk_document,
    create_academic_risk_analysis,
    find_academic_risk_analyses_by_user_id,
    find_academic_risk_analysis_by_id_and_user_id,
    to_public_academic_risk_analysis,
    to_public_academic_risk_summary,
)

VALID_USER_ID = str(ObjectId())

VALID_ANALYSIS_DATA = {
    "planId": str(ObjectId()),
    "semesterCode": "2025-2",
    "analyzerType": "deterministic",
    "analysisSource": "semester_plan",
    "status": "open",
    "summary": {"totalRisks": 2, "highestSeverity": "high", "counts": {"low": 0, "medium": 1, "high": 1}},
    "risks": [
        {"riskType": "overload", "severity": "high", "message": "Too many credits"},
        {"riskType": "prerequisite", "severity": "medium", "message": "Missing prereq"},
    ],
    "contextSnapshot": {"semesterCode": "2025-2"},
}


# ---------------------------------------------------------------------------
# _format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_converts_to_iso_z():
    dt = datetime(2025, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    result = _format_datetime(dt)
    assert result == "2025-05-20T12:00:00Z"


def test_format_datetime_returns_none_for_none():
    assert _format_datetime(None) is None


def test_format_datetime_stringifies_other():
    assert _format_datetime("raw") == "raw"


# ---------------------------------------------------------------------------
# build_academic_risk_document
# ---------------------------------------------------------------------------

def test_build_academic_risk_document_returns_expected_shape():
    doc = build_academic_risk_document(VALID_USER_ID, VALID_ANALYSIS_DATA)
    assert isinstance(doc["userId"], ObjectId)
    assert isinstance(doc["planId"], ObjectId)
    assert doc["semesterCode"] == "2025-2"
    assert doc["analyzerType"] == "deterministic"
    assert doc["analysisSource"] == "semester_plan"
    assert doc["status"] == "open"
    assert doc["summary"]["totalRisks"] == 2
    assert len(doc["risks"]) == 2
    assert isinstance(doc["createdAt"], datetime)


def test_build_academic_risk_document_defaults_analyzer_type():
    data = {**VALID_ANALYSIS_DATA}
    del data["analyzerType"]
    doc = build_academic_risk_document(VALID_USER_ID, data)
    assert doc["analyzerType"] == "deterministic"


def test_build_academic_risk_document_handles_null_plan_id():
    data = {**VALID_ANALYSIS_DATA, "planId": None}
    doc = build_academic_risk_document(VALID_USER_ID, data)
    assert doc["planId"] is None


def test_build_academic_risk_document_raises_on_invalid_user_id():
    with pytest.raises(ValueError, match="Invalid user id"):
        build_academic_risk_document("bad-id", VALID_ANALYSIS_DATA)


# ---------------------------------------------------------------------------
# to_public_academic_risk_summary
# ---------------------------------------------------------------------------

def test_to_public_academic_risk_summary_returns_none_for_none():
    assert to_public_academic_risk_summary(None) is None


def test_to_public_academic_risk_summary_extracts_fields():
    doc = {
        "_id": ObjectId(),
        "planId": ObjectId(),
        "semesterCode": "2025-2",
        "analyzerType": "deterministic",
        "analysisSource": "semester_plan",
        "status": "open",
        "summary": {"totalRisks": 1},
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }
    result = to_public_academic_risk_summary(doc)
    assert result is not None
    assert result["semesterCode"] == "2025-2"
    assert result["status"] == "open"
    assert "risks" not in result


def test_to_public_academic_risk_summary_null_plan_id():
    doc = {
        "_id": ObjectId(),
        "planId": None,
        "semesterCode": "2025-2",
        "analyzerType": "deterministic",
        "analysisSource": "semester_plan",
        "status": "open",
        "summary": {},
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_academic_risk_summary(doc)
    assert result is not None
    assert result["planId"] is None


# ---------------------------------------------------------------------------
# to_public_academic_risk_analysis
# ---------------------------------------------------------------------------

def test_to_public_academic_risk_analysis_returns_none_for_none():
    assert to_public_academic_risk_analysis(None) is None


def test_to_public_academic_risk_analysis_includes_risks():
    doc = {
        "_id": ObjectId(),
        "planId": None,
        "semesterCode": "2025-2",
        "analyzerType": "deterministic",
        "analysisSource": "semester_plan",
        "status": "open",
        "summary": {},
        "risks": [{"riskType": "overload"}],
        "contextSnapshot": {},
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_academic_risk_analysis(doc)
    assert result is not None
    assert len(result["risks"]) == 1
    assert result["risks"][0]["riskType"] == "overload"


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_academic_risk_analysis_returns_document_with_id(mongo_database):
    result = await create_academic_risk_analysis(mongo_database, VALID_USER_ID, VALID_ANALYSIS_DATA)
    assert "_id" in result
    assert result["semesterCode"] == "2025-2"
    assert result["status"] == "open"


@pytest.mark.asyncio
async def test_find_academic_risk_analyses_by_user_id_returns_created(mongo_database):
    await create_academic_risk_analysis(mongo_database, VALID_USER_ID, VALID_ANALYSIS_DATA)
    result = await find_academic_risk_analyses_by_user_id(mongo_database, VALID_USER_ID)
    assert result["total"] == 1
    assert len(result["analyses"]) == 1
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_find_academic_risk_analyses_by_user_id_empty_for_unknown(mongo_database):
    result = await find_academic_risk_analyses_by_user_id(mongo_database, str(ObjectId()))
    assert result["total"] == 0
    assert result["analyses"] == []


@pytest.mark.asyncio
async def test_find_academic_risk_analyses_by_user_id_empty_for_invalid(mongo_database):
    result = await find_academic_risk_analyses_by_user_id(mongo_database, "bad-id")
    assert result["total"] == 0
    assert result["analyses"] == []


@pytest.mark.asyncio
async def test_find_academic_risk_analysis_by_id_and_user_id_returns_analysis(mongo_database):
    created = await create_academic_risk_analysis(mongo_database, VALID_USER_ID, VALID_ANALYSIS_DATA)
    analysis_id = str(created["_id"])

    result = await find_academic_risk_analysis_by_id_and_user_id(
        mongo_database, analysis_id, VALID_USER_ID
    )
    assert result is not None
    assert result["semesterCode"] == "2025-2"


@pytest.mark.asyncio
async def test_find_academic_risk_analysis_by_id_returns_none_for_wrong_user(mongo_database):
    created = await create_academic_risk_analysis(mongo_database, VALID_USER_ID, VALID_ANALYSIS_DATA)
    analysis_id = str(created["_id"])

    result = await find_academic_risk_analysis_by_id_and_user_id(
        mongo_database, analysis_id, str(ObjectId())
    )
    assert result is None


@pytest.mark.asyncio
async def test_find_academic_risk_analysis_returns_none_for_invalid_ids(mongo_database):
    result = await find_academic_risk_analysis_by_id_and_user_id(mongo_database, "bad", VALID_USER_ID)
    assert result is None
    result = await find_academic_risk_analysis_by_id_and_user_id(
        mongo_database, str(ObjectId()), "bad"
    )
    assert result is None


@pytest.mark.asyncio
async def test_find_academic_risk_analyses_pagination(mongo_database):
    for i in range(5):
        data = {**VALID_ANALYSIS_DATA, "semesterCode": f"2025-{i}"}
        await create_academic_risk_analysis(mongo_database, VALID_USER_ID, data)

    result = await find_academic_risk_analyses_by_user_id(
        mongo_database, VALID_USER_ID, page=1, limit=3
    )
    assert len(result["analyses"]) == 3
    assert result["total"] == 5
    assert result["limit"] == 3
