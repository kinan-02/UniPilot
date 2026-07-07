"""Unit tests for eval side-effect firewall (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.side_effect_firewall import EvalSideEffectFirewall, SideEffectViolation


@pytest.mark.asyncio
async def test_blocks_action_proposal_creation() -> None:
    firewall = EvalSideEffectFirewall()
    firewall.install()
    try:
        from app.repositories import agent_action_proposal_repository

        with pytest.raises(SideEffectViolation):
            await agent_action_proposal_repository.create_agent_action_proposal(
                database=None,  # type: ignore[arg-type]
                conversation_id="507f1f77bcf86cd799439011",
                user_id="507f1f77bcf86cd799439012",
                run_id=None,
                action_type="save_plan",
                title="Save",
                description="Save plan",
                payload={},
            )
        assert firewall.violations()[0]["kind"] == "action_proposal"
    finally:
        firewall.uninstall()


@pytest.mark.asyncio
async def test_blocks_semester_plan_write() -> None:
    firewall = EvalSideEffectFirewall()
    firewall.install()
    try:
        from app.repositories import semester_plan_repository

        with pytest.raises(SideEffectViolation):
            await semester_plan_repository.create_semester_plan(
                database=None,  # type: ignore[arg-type]
                settings=None,  # type: ignore[arg-type]
                user_id="u1",
                plan_data={"semesters": []},
            )
    finally:
        firewall.uninstall()


@pytest.mark.asyncio
async def test_blocks_student_profile_update() -> None:
    firewall = EvalSideEffectFirewall()
    firewall.install()
    try:
        from app.repositories import student_profile_repository

        with pytest.raises(SideEffectViolation):
            await student_profile_repository.update_student_profile_by_user_id(
                database=None,  # type: ignore[arg-type]
                user_id="u1",
                profile_data={"major": "CS"},
            )
    finally:
        firewall.uninstall()


@pytest.mark.asyncio
async def test_blocks_completed_course_write() -> None:
    firewall = EvalSideEffectFirewall()
    firewall.install()
    try:
        from app.repositories import completed_course_repository

        with pytest.raises(SideEffectViolation):
            await completed_course_repository.create_completed_course(
                database=None,  # type: ignore[arg-type]
                settings=None,  # type: ignore[arg-type]
                user_id="u1",
                record_data={"courseNumber": "123"},
            )
    finally:
        firewall.uninstall()


def test_records_violations_compactly() -> None:
    firewall = EvalSideEffectFirewall()
    firewall._record("action_proposal", "test.target")  # noqa: SLF001
    assert firewall.violations() == [{"kind": "action_proposal", "target": "test.target"}]


@pytest.mark.asyncio
async def test_uninstall_restores_original_behavior() -> None:
    from app.repositories import agent_action_proposal_repository

    original = agent_action_proposal_repository.create_agent_action_proposal
    firewall = EvalSideEffectFirewall()
    firewall.install()
    firewall.uninstall()
    assert agent_action_proposal_repository.create_agent_action_proposal is not original or callable(original)


@pytest.mark.asyncio
async def test_no_false_positive_for_read_only_catalog_call() -> None:
    from app.repositories import catalog_repository

    firewall = EvalSideEffectFirewall()
    firewall.install()
    try:
        assert callable(catalog_repository.list_courses)
        assert firewall.violations() == []
    finally:
        firewall.uninstall()
