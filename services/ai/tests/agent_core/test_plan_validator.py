"""Unit tests for `planning/plan_validator.py` (Phase 0 scaffolding).

`validate_plan_draft` is a pure, deterministic reporter run on a DRAFT batch
(PlanStepDrafts with local labels) BEFORE the critics. It never mutates and
never blocks -- its findings drive critic selection (W2). These tests pin each
finding code to a crafted draft and prove a clean draft yields nothing.
"""

from __future__ import annotations

from app.agent_core.planning.plan_validator import ValidatorReport, validate_plan_draft
from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStepDraft


def _draft(
    step_id: str,
    objective: str = "retrieve the student profile",
    *,
    depends_on: list[str] | None = None,
    success_criteria: list[str] | None = None,
) -> PlanStepDraft:
    return PlanStepDraft(
        step_id=step_id,
        objective=objective,
        depends_on=depends_on or [],
        success_criteria=success_criteria if success_criteria is not None else ["result present"],
    )


def _pi(**kwargs: object) -> PlannerInvocationInput:
    base: dict[str, object] = {"user_goal": "g", "original_user_message": "m"}
    base.update(kwargs)
    return PlannerInvocationInput(**base)  # type: ignore[arg-type]


def test_clean_draft_has_no_findings() -> None:
    drafts = [
        _draft("A", "retrieve student profile"),
        _draft("B", "compute the student gpa", depends_on=["A"]),
    ]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert isinstance(report, ValidatorReport)
    assert report.findings == []
    assert report.codes() == set()


def test_dangling_dependency_flagged() -> None:
    drafts = [_draft("A", depends_on=["Z"])]  # Z is neither a sibling nor a known global id
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_DANGLING" in report.codes()


def test_known_global_dependency_is_not_dangling() -> None:
    drafts = [_draft("A", depends_on=["1a"])]  # 1a is an already-completed prior-invocation step
    report = validate_plan_draft(drafts, known_global_ids={"1a"}, planner_input=_pi())
    assert "F_DANGLING" not in report.codes()


def test_sibling_dependency_is_not_dangling() -> None:
    drafts = [_draft("A"), _draft("B", depends_on=["A"])]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_DANGLING" not in report.codes()


def test_cycle_flagged() -> None:
    drafts = [_draft("A", depends_on=["B"]), _draft("B", depends_on=["A"])]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_CYCLE" in report.codes()


def test_empty_success_criteria_flagged() -> None:
    drafts = [_draft("A", success_criteria=[])]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_EMPTY_CRITERIA" in report.codes()


def test_duplicate_objective_flagged() -> None:
    drafts = [
        _draft("A", "retrieve the student completed courses"),
        _draft("B", "retrieve the student completed courses"),
    ]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_DUP_OBJECTIVE" in report.codes()
    finding = next(f for f in report.findings if f.code == "F_DUP_OBJECTIVE")
    assert set(finding.step_ids) == {"A", "B"}


def test_distinct_objectives_not_flagged_as_duplicate() -> None:
    drafts = [
        _draft("A", "retrieve the student completed courses"),
        _draft("B", "evaluate prerequisite eligibility for algorithms"),
    ]
    report = validate_plan_draft(drafts, known_global_ids=set(), planner_input=_pi())
    assert "F_DUP_OBJECTIVE" not in report.codes()


def test_unaddressed_subask_flagged_when_lexically_disjoint() -> None:
    drafts = [_draft("A", "retrieve student profile")]
    report = validate_plan_draft(
        drafts,
        known_global_ids=set(),
        planner_input=_pi(sub_asks=["simulate dropping quantum mechanics next winter"]),
    )
    assert "F_UNADDRESSED_SUBASK" in report.codes()


def test_addressed_subask_not_flagged() -> None:
    drafts = [_draft("A", "retrieve the student profile and completed courses")]
    report = validate_plan_draft(
        drafts,
        known_global_ids=set(),
        planner_input=_pi(sub_asks=["what courses has the student completed"]),
    )
    assert "F_UNADDRESSED_SUBASK" not in report.codes()


def test_findings_are_advisory_report_never_raises_on_empty() -> None:
    report = validate_plan_draft([], known_global_ids=set(), planner_input=_pi())
    assert report.findings == []
    assert report.codes() == set()
