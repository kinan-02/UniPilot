"""Unit tests for the Planner Agent (Phase 5).

All tests use a fake `ReasoningBlock` or the deterministic fallback path —
no real LLM call is made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.planner.agent import build_execution_plan
from app.agent.planner.diagnostics import run_planner_dry_run
from app.agent.planner.legacy_mapping import build_legacy_workflow_plan_summary
from app.agent.planner.schemas import PlannerOutput
from app.agent.reasoning.prompt_registry import PLANNER_AGENT_V1
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings


class FakeReasoningBlock:
    """Duck-typed stand-in for `ReasoningBlock` — records the input it was called with."""

    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _subtask_result(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        id="check_progress",
        title="Check current graduation progress",
        kind="analyze",
        capability_name="graduation_progress_workflow",
        objective="Determine remaining requirements toward graduation.",
        depends_on=[],
        required_context_sections=["user_message", "profile_summary"],
        success_criteria=["Progress figures come from the deterministic graduation engine."],
        validation_requirements=["Cross-check against agent_context_pack_summary."],
        requires_user_confirmation=False,
        risk_level="low",
    )
    defaults.update(overrides)
    return defaults


def _plan_result(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        status="completed",
        plan_id="plan-abc123",
        user_goal="Check graduation progress.",
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="graduation_progress_check",
        subtasks=[_subtask_result()],
        required_context=["profile_summary"],
        missing_context=[],
        assumptions=[],
        requires_user_confirmation=False,
        write_risk="none",
        clarification_questions=[],
        validation_strategy=["Preserve deterministic workflow output."],
        fallback_workflow_name="graduation_progress_workflow",
        decision_summary="Single-capability plan reusing the existing deterministic workflow.",
        warnings=[],
        confidence=0.85,
    )
    defaults.update(overrides)
    return defaults


def _completed_output(result: dict[str, Any], **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary="planned",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.85,
        schema_valid=True,
        iterations_used=3,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _failed_output(**overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="failed",
        result=None,
        decision_summary="llm unavailable",
        confidence=0.0,
        schema_valid=False,
        iterations_used=0,
        repair_attempts_used=0,
        warnings=["llm_adapter_error: llm_unavailable"],
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _settings_enabled(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


def _settings_disabled(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": False}
    base.update(overrides)
    return Settings(**base)


_LEGACY_PLAN = build_legacy_workflow_plan_summary(
    workflow_name="graduation_progress_workflow",
    read_only=True,
    requires_confirmation=False,
    primary_intent="graduation_progress_check",
)

_TASK_UNDERSTANDING = {
    "status": "completed",
    "primaryIntent": "graduation_progress_check",
    "suggestedNextLayer": "planner",
}


# ---------------------------------------------------------------------------
# 1. Successful plan from fake ReasoningBlock output.
# ---------------------------------------------------------------------------


async def test_successful_plan_from_fake_reasoning_block() -> None:
    fake = FakeReasoningBlock(_completed_output(_plan_result()))
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        deterministic_intent="graduation_progress_check",
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert len(fake.calls) == 1
    assert isinstance(plan, PlannerOutput)
    assert plan.status == "completed"
    assert plan.source == "llm_reasoning_block"
    assert plan.execution_mode == "single_capability"
    assert plan.subtasks[0].capability_name == "graduation_progress_workflow"


# ---------------------------------------------------------------------------
# 2. Planner uses prompt_contract_name="planner_agent_v1".
# ---------------------------------------------------------------------------


async def test_planner_uses_planner_agent_v1_contract() -> None:
    fake = FakeReasoningBlock(_completed_output(_plan_result()))
    settings = _settings_enabled()

    await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        settings=settings,
        reasoning_block=fake,
    )

    assert fake.calls[0].prompt_contract_name == PLANNER_AGENT_V1
    assert fake.calls[0].risk_level == "high"


# ---------------------------------------------------------------------------
# 3. Planner receives a compact capability registry summary.
# ---------------------------------------------------------------------------


async def test_planner_receives_compact_capability_registry_summary() -> None:
    fake = FakeReasoningBlock(_completed_output(_plan_result()))
    settings = _settings_enabled()
    registry = build_default_capability_registry()

    await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        capability_registry=registry,
        settings=settings,
        reasoning_block=fake,
    )

    summary = fake.calls[0].task_context["capability_registry_summary"]
    assert isinstance(summary, list) and summary
    names = {entry["name"] for entry in summary}
    # Only enabled capabilities are summarized -- disabled Phase 5+ placeholders
    # (besides the already-live task_understanding_agent) must not appear.
    assert "graduation_progress_workflow" in names
    assert "planner_agent" not in names
    for entry in summary:
        assert set(entry) == {"name", "type", "description", "supported_intents", "write_scope", "risk_level"}


# ---------------------------------------------------------------------------
# 4. Planner includes TaskUnderstandingOutput.
# ---------------------------------------------------------------------------


async def test_planner_includes_task_understanding_in_context() -> None:
    fake = FakeReasoningBlock(_completed_output(_plan_result()))
    settings = _settings_enabled()

    await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        settings=settings,
        reasoning_block=fake,
    )

    assert fake.calls[0].task_context["task_understanding"] == _TASK_UNDERSTANDING


# ---------------------------------------------------------------------------
# 5. Falls back to deterministic legacy plan when the flag is disabled.
# ---------------------------------------------------------------------------


async def test_falls_back_to_deterministic_plan_when_disabled() -> None:
    settings = _settings_disabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        deterministic_intent="graduation_progress_check",
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
    )

    assert plan.source == "deterministic_fallback"
    assert plan.execution_mode == "deterministic_workflow"
    assert plan.fallback_workflow_name == "graduation_progress_workflow"
    assert plan.subtasks[0].capability_name == "graduation_progress_workflow"
    assert "planner_disabled" in plan.warnings


# ---------------------------------------------------------------------------
# 6. Falls back when ReasoningBlock itself fails.
# ---------------------------------------------------------------------------


async def test_falls_back_when_reasoning_block_fails() -> None:
    fake = FakeReasoningBlock(_failed_output())
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        deterministic_intent="graduation_progress_check",
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.source == "deterministic_fallback"
    assert "planner_llm_unavailable_or_failed" in plan.warnings


# ---------------------------------------------------------------------------
# 7. Unknown capability from the LLM is rejected.
# ---------------------------------------------------------------------------


async def test_unknown_capability_subtask_is_rejected_but_plan_survives() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(
                subtasks=[
                    _subtask_result(id="good", capability_name="graduation_progress_workflow"),
                    _subtask_result(id="bad", capability_name="a_capability_that_does_not_exist"),
                ]
            )
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.source == "llm_reasoning_block"
    assert [s.id for s in plan.subtasks] == ["good"]
    assert any("unknown_capability_dropped" in w for w in plan.warnings)


async def test_plan_where_every_subtask_is_invalid_falls_back() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(subtasks=[_subtask_result(capability_name="not_a_real_capability")])
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.source == "deterministic_fallback"
    assert "planner_plan_unusable_after_normalization" in plan.warnings


# ---------------------------------------------------------------------------
# 8. Disabled placeholder capability behavior is deterministic.
# ---------------------------------------------------------------------------


async def test_disabled_placeholder_capability_is_rejected_deterministically() -> None:
    def _make_fake() -> FakeReasoningBlock:
        return FakeReasoningBlock(
            _completed_output(
                _plan_result(
                    subtasks=[
                        _subtask_result(id="good", capability_name="graduation_progress_workflow"),
                        # `planner_agent` itself exists in the default registry but is disabled.
                        _subtask_result(id="future", capability_name="planner_agent"),
                    ]
                )
            )
        )

    settings = _settings_enabled()
    plan_a = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=_make_fake(),
    )
    plan_b = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=_make_fake(),
    )

    for plan in (plan_a, plan_b):
        assert [s.id for s in plan.subtasks] == ["good"]
        assert any("disabled_capability_dropped" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# 9. Invalid dependency is rejected (plan survives with the edge stripped).
# ---------------------------------------------------------------------------


async def test_invalid_dependency_is_stripped_not_fatal() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(subtasks=[_subtask_result(depends_on=["does_not_exist"])])
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.source == "llm_reasoning_block"
    assert plan.subtasks[0].depends_on == []
    assert any("invalid_dependency_dropped" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# 10. Dependency cycle causes a fallback.
# ---------------------------------------------------------------------------


async def test_dependency_cycle_falls_back_to_deterministic_plan() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(
                execution_mode="multi_capability_graph",
                subtasks=[
                    _subtask_result(
                        id="a", capability_name="graduation_progress_workflow", depends_on=["b"]
                    ),
                    _subtask_result(
                        id="b", capability_name="course_question_workflow", depends_on=["a"]
                    ),
                ],
            )
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.source == "deterministic_fallback"
    assert "planner_plan_unusable_after_normalization" in plan.warnings


# ---------------------------------------------------------------------------
# 11. Explicit write/save/import subtask requires user confirmation.
# ---------------------------------------------------------------------------


async def test_explicit_write_subtask_requires_confirmation() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(
                primary_intent="semester_plan_generation",
                subtasks=[
                    _subtask_result(
                        id="save_plan",
                        kind="propose_action",
                        capability_name="semester_planning_workflow",
                        requires_user_confirmation=False,
                        risk_level="low",
                    )
                ],
                requires_user_confirmation=False,
                write_risk="none",
            )
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="Please save my semester plan",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.requires_user_confirmation is True
    assert plan.write_risk == "explicit"
    assert plan.subtasks[0].requires_user_confirmation is True


# ---------------------------------------------------------------------------
# 12. Missing context is preserved.
# ---------------------------------------------------------------------------


async def test_missing_context_is_preserved() -> None:
    fake = FakeReasoningBlock(
        _completed_output(
            _plan_result(
                status="needs_more_context",
                missing_context=["student_profile", "degree_requirements"],
            )
        )
    )
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert plan.status == "needs_more_context"
    assert "student_profile" in plan.missing_context
    assert "degree_requirements" in plan.missing_context


# ---------------------------------------------------------------------------
# 13. Confidence is clamped/validated.
# ---------------------------------------------------------------------------


async def test_confidence_is_clamped_to_valid_range() -> None:
    fake = FakeReasoningBlock(_completed_output(_plan_result(confidence=5.0)))
    settings = _settings_enabled()

    plan = await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
        reasoning_block=fake,
    )

    assert 0.0 <= plan.confidence <= 1.0
    assert plan.confidence == 1.0


# ---------------------------------------------------------------------------
# 14. No chain-of-thought/scratchpad fields exist on the models.
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELD_NAMES = {
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
}


def test_no_chain_of_thought_fields_on_planner_models() -> None:
    from app.agent.planner.schemas import PlannerOutput as _PlannerOutput
    from app.agent.planner.schemas import PlannerSubtask as _PlannerSubtask

    assert not (_FORBIDDEN_FIELD_NAMES & set(_PlannerOutput.model_fields))
    assert not (_FORBIDDEN_FIELD_NAMES & set(_PlannerSubtask.model_fields))


def test_no_chain_of_thought_keys_in_planner_json_schemas() -> None:
    from app.agent.reasoning.task_schemas import PLANNER_OUTPUT_SCHEMA, PLANNER_SUBTASK_SCHEMA

    assert not (_FORBIDDEN_FIELD_NAMES & set(PLANNER_OUTPUT_SCHEMA["properties"]))
    assert not (_FORBIDDEN_FIELD_NAMES & set(PLANNER_SUBTASK_SCHEMA["properties"]))


# ---------------------------------------------------------------------------
# 15/16. Context compiler preview is generated per subtask (via diagnostics),
# and raw compiled context is never included.
# ---------------------------------------------------------------------------


async def test_context_compiler_preview_generated_without_raw_context() -> None:
    settings = _settings_enabled()

    summary = await run_planner_dry_run(
        user_message="What am I missing to graduate?",
        task_understanding_summary=_TASK_UNDERSTANDING,
        deterministic_intent="graduation_progress_check",
        deterministic_entities={},
        legacy_workflow_plan=_LEGACY_PLAN,
        settings=settings,
    )

    assert summary is not None
    previews = summary["contextPreviews"]
    assert previews, "expected at least one context preview for the fallback plan's subtask"
    preview = previews[0]
    assert set(preview) == {
        "subtaskId",
        "capabilityName",
        "includedSections",
        "omittedSections",
        "warnings",
        "estimatedItems",
    }
    assert "context" not in preview
    # No raw compiled context payload anywhere in the diagnostic summary.
    assert "context" not in summary


def test_planner_diagnostics_off_returns_none() -> None:
    import asyncio

    settings = _settings_disabled()
    result = asyncio.run(
        run_planner_dry_run(
            user_message="What am I missing to graduate?",
            task_understanding_summary=_TASK_UNDERSTANDING,
            deterministic_intent="graduation_progress_check",
            deterministic_entities={},
            settings=settings,
        )
    )
    assert result is None


# ---------------------------------------------------------------------------
# 17. Planner never executes a tool or workflow (static import/text check).
# ---------------------------------------------------------------------------


def test_planner_package_never_imports_or_calls_the_workflow_registry() -> None:
    planner_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "planner"
    assert planner_dir.is_dir()
    for path in planner_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "workflows.registry" not in text, f"{path} must not import the workflow registry"
        assert "get_workflow(" not in text, f"{path} must not call get_workflow(...)"
        assert ".run(database" not in text, f"{path} must not execute a workflow's .run(...)"


async def test_planner_never_calls_chat_llm_adapter_directly() -> None:
    """`build_execution_plan` must construct `ChatLLMAdapter` only to hand to `ReasoningBlock`."""
    fake = FakeReasoningBlock(_completed_output(_plan_result()))
    settings = _settings_enabled()

    await build_execution_plan(
        user_message="What am I missing to graduate?",
        task_understanding=_TASK_UNDERSTANDING,
        settings=settings,
        reasoning_block=fake,
    )

    # The fake block was used -- a real ChatLLMAdapter/ReasoningBlock was never
    # constructed or invoked for this call.
    assert len(fake.calls) == 1
