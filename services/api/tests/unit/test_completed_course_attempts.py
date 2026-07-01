"""Tests for completed course attempt resolution."""

import pytest

from app.services.completed_course_attempts import (
    MAX_COURSE_ATTEMPTS,
    latest_attempt_rank,
    resolve_available_attempt,
)


def test_resolve_available_attempt_returns_requested_when_free():
    assert resolve_available_attempt(set(), 1) == 1
    assert resolve_available_attempt({1}, 2) == 2


def test_resolve_available_attempt_bumps_when_requested_attempt_is_taken():
    assert resolve_available_attempt({1}, 1) == 2
    assert resolve_available_attempt({1, 2}, 1) == 3


def test_resolve_available_attempt_raises_when_all_slots_used():
    used = set(range(1, MAX_COURSE_ATTEMPTS + 1))
    with pytest.raises(ValueError, match="Maximum"):
        resolve_available_attempt(used, 1)


def test_resolve_available_attempt_allows_sixth_slot_when_limit_is_ten():
    used = {1, 2, 3, 4, 5}
    assert resolve_available_attempt(used, 1) == 6


def test_latest_attempt_rank_prefers_higher_attempt_over_recorded_at():
    first = latest_attempt_rank(attempt=1, recorded_at_timestamp=10.0)
    retake = latest_attempt_rank(attempt=2, recorded_at_timestamp=0.0)
    assert retake > first
