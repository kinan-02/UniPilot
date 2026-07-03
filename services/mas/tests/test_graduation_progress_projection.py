"""Unit tests for graduation progress projection."""

from __future__ import annotations

from app.services.graduation_progress_projection import project_graduation_progress_after_plan


class _StubEngine:
    _built = True
    course_catalog = {"00140008": {"general": {"נקודות": "3.5"}}}

    def __init__(self) -> None:
        import networkx as nx

        self.graph = nx.DiGraph()
        self.graph.add_node("00140008", credits="3.5")


def test_project_graduation_progress_reduces_remaining_mandatory() -> None:
    baseline = {
        "completedCredits": 40.0,
        "totalRequiredCredits": 155.0,
        "creditsRemaining": 115.0,
        "completionPercentage": 25.8,
        "remainingMandatoryCourses": [
            {"courseNumber": "00140008"},
            {"courseNumber": "00940139"},
        ],
    }

    projected = project_graduation_progress_after_plan(
        baseline=baseline,
        course_ids=["00140008"],
        engine=_StubEngine(),  # type: ignore[arg-type]
    )

    assert projected["creditsRemaining"] == 111.5
    assert len(projected["remainingMandatoryCourses"]) == 1
    assert projected["remainingMandatoryCourses"][0]["courseNumber"] == "00940139"
    assert projected["projectionMeta"]["mandatorySatisfied"] == ["00140008"]
