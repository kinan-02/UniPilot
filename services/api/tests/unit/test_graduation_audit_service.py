"""Unit tests for graduation audit service."""

from app.agent.schemas import AgentContextPack, ContextValidation
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


def test_match_degree_requirements_counts_statuses():
    from app.services.requirement_matching_service import match_degree_requirements

    progress = {
        "requirementProgress": [
            {
                "requirementGroupId": "prog:core",
                "title": "Core",
                "status": "satisfied",
                "minCredits": 10,
                "creditsCompleted": 10,
                "creditsRemaining": 0,
                "remainingCourses": [],
            },
            {
                "requirementGroupId": "prog:elective",
                "title": "Electives",
                "status": "in_progress",
                "minCredits": 8,
                "creditsCompleted": 3,
                "creditsRemaining": 5,
                "remainingCourses": [{"courseNumber": "00940101"}],
            },
        ]
    }
    summary = match_degree_requirements(
        progress=progress,
        catalog_requirements=[
            {"requirementGroupId": "prog:core"},
            {"requirementGroupId": "prog:elective"},
            {"requirementGroupId": "prog:orphan"},
        ],
    )
    assert summary.total_requirements == 2
    assert summary.satisfied_count == 1
    assert summary.partial_count == 1
    assert "prog:orphan" in summary.unmatched_catalog_rules


def test_build_graduation_summary_text():
    from app.agent.graduation_response_builder import build_graduation_summary_text
    from app.services.graduation_audit_service import GraduationAuditResult
    from app.services.requirement_matching_service import RequirementMatchingSummary

    audit = GraduationAuditResult(
        status="ok",
        progress={
            "degreeName": "Information Systems Engineering",
            "completedCredits": 112,
            "totalRequiredCredits": 160,
            "creditsRemaining": 48,
            "completionPercentage": 70,
        },
        graduation_status="not_ready",
        blockers=["Missing track electives"],
    )
    matching = RequirementMatchingSummary(total_requirements=5, satisfied_count=3)
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
    )
    text = build_graduation_summary_text(audit=audit, matching=matching, context=context)
    assert "Information Systems Engineering" in text
    assert "70%" in text
    assert "Main blocker" in text
