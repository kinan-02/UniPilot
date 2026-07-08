"""Unit tests for graduation audit service (api-side computation)."""

from app.services.graduation_audit_service import _extract_blockers, _map_graduation_status


def test_map_graduation_status_complete():
    assert _map_graduation_status("complete", credits_remaining=0) == "ready_to_graduate"


def test_map_graduation_status_in_progress():
    assert _map_graduation_status("in_progress", credits_remaining=20) == "not_ready"


def test_extract_blockers_from_mandatory_and_missing():
    progress = {
        "remainingMandatoryCourses": [{"courseNumber": "00940139"}],
        "missingRequirements": [
            {
                "title": "Elective pool",
                "status": "in_progress",
                "creditsRemaining": 6,
            }
        ],
    }
    blockers = _extract_blockers(progress)
    assert any("00940139" in blocker for blocker in blockers)
    assert any("Elective pool" in blocker for blocker in blockers)
