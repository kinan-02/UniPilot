"""Unit tests for impersonation guard."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.security.impersonation_guard import reject_impersonation_query_params


def _request(query: str) -> Request:
    return Request({"type": "http", "query_string": query.encode(), "headers": []})


def test_reject_impersonation_query_params_allows_clean_requests() -> None:
    reject_impersonation_query_params(_request("limit=10"))


@pytest.mark.parametrize(
    "query",
    [
        "userId=abc",
        "studentId=abc",
        "user_id=abc",
        "student-id=abc",
    ],
)
def test_reject_impersonation_query_params_blocks_cross_user_keys(query: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        reject_impersonation_query_params(_request(query))
    assert exc_info.value.status_code == 403
