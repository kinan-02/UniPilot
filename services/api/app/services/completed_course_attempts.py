"""Attempt numbering for retaken courses on a student transcript."""

from __future__ import annotations

MAX_COURSE_ATTEMPTS = 10


def resolve_available_attempt(used_attempts: set[int], requested: int = 1) -> int:
    """Return requested attempt when free, otherwise the next open attempt slot."""
    normalized_requested = max(1, min(int(requested), MAX_COURSE_ATTEMPTS))
    if normalized_requested not in used_attempts:
        return normalized_requested

    for attempt in range(1, MAX_COURSE_ATTEMPTS + 1):
        if attempt not in used_attempts:
            return attempt

    raise ValueError(f"Maximum of {MAX_COURSE_ATTEMPTS} attempts reached for this course")


def latest_attempt_rank(
    *,
    attempt: int,
    recorded_at_timestamp: float,
    semester_code: str = "",
) -> tuple[int, float, str]:
    """Rank transcript rows so the latest retake wins (grade is not considered)."""
    return (
        max(1, int(attempt)),
        recorded_at_timestamp,
        semester_code,
    )
