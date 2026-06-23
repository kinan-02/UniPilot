"""Reject client attempts to override the authenticated user on self-scoped routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

_FORBIDDEN_QUERY_KEYS = frozenset(
    {
        "userid",
        "user_id",
        "studentid",
        "student_id",
    }
)


def reject_impersonation_query_params(request: Request) -> None:
    for key in request.query_params:
        normalized = key.lower().replace("-", "_")
        if normalized in _FORBIDDEN_QUERY_KEYS:
            raise HTTPException(
                status_code=403,
                detail="Cross-user access is not permitted on this endpoint",
            )
