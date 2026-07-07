"""Unit tests for the agent-local requirement matching + response building
that consume `GraduationAuditResult` (the client mirror of `api`'s type)."""

from app.agent.graduation_response_builder import build_graduation_summary_text
from app.agent.schemas import AgentContextPack
from app.services.graduation_audit_client import GraduationAuditResult
from app.services.requirement_matching_service import RequirementMatchingSummary, match_degree_requirements


def test_match_degree_requirements_counts_statuses():
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
