"""Targeted coverage for graduation progress and transcript import helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.clients.transcript_parser_client import TranscriptParserClientError, parse_transcript_pdf
from app.repositories import catalog_repository
from app.schemas.transcript_import import CommitTranscriptCourseInput, CommitTranscriptImportRequest
from app.services.course_pool_classification import resolve_claiming_pool
from app.services.course_reference_keys import (
    build_remaining_mandatory_course_entries,
    course_matches_equivalence_group,
    course_number_keys,
    course_references_number_keys,
    filter_remaining_mandatory_courses,
    is_mandatory_curriculum_course,
    mandatory_group_for_course,
    merge_overlapping_equivalence_groups,
)
from app.services.graduation_progress_calculator import is_course_eligible_for_pools
from app.services.transcript_import_normalization import resolve_import_credits, resolve_import_grade_points
from app.services.transcript_import_service import commit_transcript_import
from tests.fixtures.completed_course_fixtures import seed_production_course_fixture


def test_course_number_keys_none_returns_empty_set():
    assert course_number_keys(None) == set()


def test_course_references_number_keys_expands_list():
    keys = course_references_number_keys([{"courseNumber": "01040031"}])
    assert "01040031" in keys


def test_merge_overlapping_equivalence_groups_skips_empty_group():
    assert merge_overlapping_equivalence_groups([set(), {"01040031"}]) == [{"01040031"}]


def test_course_matches_equivalence_group_handles_empty_inputs():
    assert course_matches_equivalence_group(None, {"01040031"}) is False
    assert course_matches_equivalence_group("01040031", set()) is False


def test_mandatory_group_for_course_returns_none_for_missing_number():
    assert mandatory_group_for_course(None, [{"01040031"}]) is None


def test_is_mandatory_curriculum_course_with_flat_number_set():
    assert is_mandatory_curriculum_course("01040031", {"01040031"})
    assert not is_mandatory_curriculum_course(None, {"01040031"})


def test_filter_remaining_mandatory_without_groups_uses_completed_keys():
    remaining = filter_remaining_mandatory_courses(
        [{"courseNumber": "01040031"}],
        [{"courseNumber": "01040031"}],
    )
    assert remaining == []


def test_filter_remaining_mandatory_keeps_ungrouped_remaining():
    remaining = filter_remaining_mandatory_courses(
        [{"courseNumber": "00940102"}],
        [],
        mandatory_groups=[{"00940101"}],
    )
    assert len(remaining) == 1


def test_build_remaining_mandatory_course_entries_uses_catalog_lookup():
    catalog_id = "665f2b0f2a3f7b2a1a9a7c99"
    remaining = build_remaining_mandatory_course_entries(
        [{"courseReferences": [{"courseNumber": "01040031", "titleHint": "Intro CS"}]}],
        set(),
        catalog_courses_by_id={
            catalog_id: {
                "courseNumber": "01040031",
                "title": "Intro CS",
                "credits": 3.5,
            }
        },
    )
    assert remaining[0]["courseId"] == catalog_id
    assert remaining[0]["catalogCredits"] == 3.5


def test_build_remaining_mandatory_course_entries_skips_catalog_without_number():
    remaining = build_remaining_mandatory_course_entries(
        [{"courseReferences": [{"courseNumber": "01040031"}]}],
        set(),
        catalog_courses_by_id={"bad": {"title": "No number"}},
    )
    assert remaining[0]["courseId"] == "matrix:01040031"


def test_is_course_eligible_for_pools_false_for_empty_pool_list():
    assert is_course_eligible_for_pools("01040031", []) is False


def test_resolve_claiming_pool_returns_none_without_course_or_pools():
    assert resolve_claiming_pool(None, [], program_code="009216-1-000") is None


def test_resolve_claiming_pool_returns_none_when_no_match():
    pool = {
        "requirementGroupId": "009216-1-000:elective-ds-pool",
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [{"courseNumber": "00940411"}],
    }
    assert resolve_claiming_pool("99999999", [pool], program_code="009216-1-000") is None


def test_resolve_import_credits_falls_back_to_catalog():
    credits = resolve_import_credits(
        CommitTranscriptCourseInput(
            courseNumber="01040031",
            semesterCode="2024-1",
            grade=85,
            creditsEarned=0,
        ),
        {"credits": 3.5},
    )
    assert credits == 3.5


def test_resolve_import_grade_points_returns_none_for_non_zero_grade():
    assert resolve_import_grade_points(
        CommitTranscriptCourseInput(
            courseNumber="01040031",
            semesterCode="2024-1",
            grade=85,
            creditsEarned=3,
        )
    ) is None


@pytest.mark.asyncio
async def test_parse_transcript_pdf_sends_internal_token_header():
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {"parseResult": {"courses": [], "warnings": [], "parseMetadata": {}}},
            "error": None,
        },
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    settings = MagicMock()
    settings.resolved_transcript_parser_url.return_value = "http://transcript-parser:8010"
    settings.resolved_internal_service_token.return_value = "secret-token"
    settings.transcript_parser_timeout_seconds = 30

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        await parse_transcript_pdf(b"%PDF", filename="t.pdf", settings=settings)

    headers = mock_client.post.await_args.kwargs["headers"]
    assert headers["X-Internal-Service-Token"] == "secret-token"


@pytest.mark.asyncio
async def test_parse_transcript_pdf_uses_fallback_error_when_payload_missing_detail():
    response = httpx.Response(
        502,
        content=b"{}",
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"%PDF", filename="t.pdf")

    assert exc_info.value.detail == "Transcript parser request failed"


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_when_parse_result_missing():
    response = httpx.Response(
        200,
        json={"success": True, "data": {"unexpected": True}, "error": None},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"%PDF", filename="t.pdf")

    assert "parseResult" in exc_info.value.detail


@pytest.mark.asyncio
async def test_commit_transcript_import_rejects_invalid_course_number(mongo_database):
    result = await commit_transcript_import(
        mongo_database,
        "665f2b0f2a3f7b2a1a9a7c03",
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput.model_construct(
                    courseNumber="123",
                    semesterCode="2024-1",
                    grade=85,
                    creditsEarned=3,
                )
            ]
        ),
    )
    assert result["createdCount"] == 0
    assert result["unresolvedCount"] == 1


@pytest.mark.asyncio
async def test_commit_transcript_import_reports_missing_catalog_course(mongo_database):
    result = await commit_transcript_import(
        mongo_database,
        "665f2b0f2a3f7b2a1a9a7c04",
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber="00999999",
                    semesterCode="2024-1",
                    grade=85,
                    creditsEarned=3,
                )
            ]
        ),
    )
    assert result["unresolvedCount"] == 1


@pytest.mark.asyncio
async def test_commit_transcript_import_handles_duplicate_key_error(mongo_database, monkeypatch):
    course = await seed_production_course_fixture(mongo_database)
    user_id = "665f2b0f2a3f7b2a1a9a7c05"

    async def raise_duplicate(*_args, **_kwargs):
        raise DuplicateKeyError("duplicate")

    monkeypatch.setattr(
        "app.services.transcript_import_service.create_completed_course",
        raise_duplicate,
    )

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            skipDuplicates=False,
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2024-2",
                    grade=90,
                    creditsEarned=3,
                )
            ],
        ),
    )
    assert result["skippedCount"] == 1


@pytest.mark.asyncio
async def test_find_course_by_number_returns_none_for_invalid_number(mongo_database):
    assert await catalog_repository.find_course_by_number(mongo_database, "bad") is None
