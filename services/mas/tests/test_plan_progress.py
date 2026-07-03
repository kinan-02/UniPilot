"""Unit tests for graduation-progress-aware plan progress scoring."""

from __future__ import annotations

from app.services.plan_progress import evaluate_degree_progress


class _StubEngine:
    _built = True
    course_catalog = {
        "00140008": {"general": {"נקודות": "3.5"}},
        "00940139": {"general": {"נקודות": "3.5"}},
    }

    def __init__(self) -> None:
        import networkx as nx

        self.graph = nx.DiGraph()
        for course_id in self.course_catalog:
            self.graph.add_node(course_id, credits="3.5")

    def evaluate_eligibility(self, node_id: str, completed_courses: list[str]) -> tuple[bool, list[str]]:
        if node_id in completed_courses:
            return True, []
        return False, ["00140008"] if node_id == "00940139" else []

    def get_course(self, course_id: str) -> dict:
        return {"credits": 3.5}


def test_evaluate_degree_progress_uses_graduation_baseline() -> None:
    graduation_progress = {
        "creditsRemaining": 40.0,
        "remainingMandatoryCourses": [
            {"courseNumber": "00140008"},
            {"courseNumber": "00940139"},
        ],
    }
    score, unlock_count, critiques, references = evaluate_degree_progress(
        engine=_StubEngine(),  # type: ignore[arg-type]
        course_ids=["00140008"],
        completed_courses=[],
        user_context={"graduation_progress": graduation_progress},
    )

    assert unlock_count >= 0
    assert score > 0.2
    assert any(ref.startswith("progress:satisfies_mandatory=") for ref in references)
    assert "progress:source=graduation_progress_api" in references
    assert not any(critique.get("type") == "no_mandatory_progress" for critique in critiques)


def test_evaluate_degree_progress_flags_missing_mandatory() -> None:
    graduation_progress = {
        "creditsRemaining": 40.0,
        "remainingMandatoryCourses": [{"courseNumber": "00940139"}],
    }
    _score, _unlock, critiques, references = evaluate_degree_progress(
        engine=_StubEngine(),  # type: ignore[arg-type]
        course_ids=["00140008"],
        completed_courses=[],
        user_context={"graduation_progress": graduation_progress},
    )

    assert any(critique.get("type") == "no_mandatory_progress" for critique in critiques)
    assert "progress:source=graduation_progress_api" in references
