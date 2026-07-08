"""Unit tests for the Phase 6 Supervisor Orchestrator Runtime (`run_supervisor_shadow`).

Uses the real default `CapabilityRegistry` (real, live workflow capability
names) so context compilation exercises the actual Phase 4 contracts. No
real LLM call is ever made -- Phase 6 makes none at all. Custom handlers are
injected via a custom `SubtaskHandlerRegistry` where a test needs to force a
failure (the Phase 6 built-in handlers never fail on their own).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import (
    ExecutionBudget,
    SubtaskExecutionRecord,
    SubtaskResult,
    SupervisorRunInput,
    SupervisorRunOutput,
)
from app.config import Settings

# Explicit, not relied-on-default: an operator's real `.env` may enable real
# handlers ambiently (exactly as this repo's own root `.env` now does for
# the Phase 9/Planner-first-live rollout). None of these tests supply a
# `runtime_context`, so enabling real handlers here would never change
# *execution* -- `_select_handler` still falls back to the safe dry-run
# stand-in -- but it would attach an extra "missing runtime context"
# warning that flips `status` from "completed" to "completed_with_warnings"
# for every test in this file that touches a workflow-typed capability.
_SETTINGS = Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=False)


class _AlwaysFailsHandler:
    """Test double: always returns a failed `SubtaskResult`."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard,
        dry_run: bool,
        runtime_context=None,
    ) -> SubtaskResult:
        self.calls += 1
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="failed",
            error="simulated_failure",
            confidence=0.0,
        )


class _FailsThenSucceedsHandler:
    """Test double: fails `fail_times` times, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard,
        dry_run: bool,
        runtime_context=None,
    ) -> SubtaskResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="failed",
                error="simulated_failure",
                confidence=0.0,
            )
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="completed",
            output_summary={"dryRun": True, "recoveredAfterRetry": True},
        )


def _subtask(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        id="s1",
        title="Check something",
        kind="analyze",
        capability_name="course_question_workflow",
        objective="Answer a course question.",
        depends_on=[],
        required_context_sections=["user_message"],
    )
    defaults.update(overrides)
    return defaults


def _plan(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        status="completed",
        plan_id="plan-1",
        user_goal="Can I take 234218?",
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="course_question",
        subtasks=[_subtask()],
        decision_summary="test plan",
        confidence=0.8,
    )
    defaults.update(overrides)
    return defaults


def _run_input(**overrides: Any) -> SupervisorRunInput:
    defaults: dict[str, Any] = dict(
        user_message="Can I take 234218?",
        planner_output=_plan(),
    )
    defaults.update(overrides)
    return SupervisorRunInput(**defaults)


# ---------------------------------------------------------------------------
# 1. Simple single-subtask plan.
# ---------------------------------------------------------------------------


async def test_runs_simple_single_subtask_plan() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)

    assert isinstance(output, SupervisorRunOutput)
    assert output.status == "completed"
    assert output.completed_subtasks == ["s1"]
    assert output.failed_subtasks == []
    assert output.skipped_subtasks == []


# ---------------------------------------------------------------------------
# 2. Multi-subtask dependency plan runs in correct order.
# ---------------------------------------------------------------------------


async def test_runs_multi_subtask_dependency_plan_in_correct_order() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow", depends_on=[]),
            _subtask(id="b", capability_name="course_question_workflow", depends_on=["a"]),
        ],
    )
    output = await run_supervisor_shadow(input=_run_input(planner_output=plan), settings=_SETTINGS)

    assert output.status == "completed"
    assert output.completed_subtasks == ["a", "b"]
    assert [record.subtask_id for record in output.subtask_records] == ["a", "b"]


# ---------------------------------------------------------------------------
# 3. Dependents skipped when a dependency fails.
# ---------------------------------------------------------------------------


async def test_skips_blocked_dependents_when_dependency_fails() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow", depends_on=[]),
            _subtask(id="b", capability_name="course_question_workflow", depends_on=["a"]),
        ],
    )
    handlers = SubtaskHandlerRegistry(default_handler=_AlwaysFailsHandler())
    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan, budget=ExecutionBudget(max_retries_per_subtask=0)),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    assert "a" in output.failed_subtasks
    assert "b" in output.skipped_subtasks
    assert any("subtask_skipped_blocked_dependency" in w for w in output.warnings)


# ---------------------------------------------------------------------------
# 4. Retries failed subtask according to budget.
# ---------------------------------------------------------------------------


async def test_retries_failed_subtask_and_eventually_succeeds() -> None:
    failing_then_ok = _FailsThenSucceedsHandler(fail_times=1)
    handlers = SubtaskHandlerRegistry(default_handler=failing_then_ok)

    output = await run_supervisor_shadow(
        input=_run_input(budget=ExecutionBudget(max_retries_per_subtask=2, max_total_retries=5)),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    assert output.status == "completed"
    assert output.completed_subtasks == ["s1"]
    assert failing_then_ok.calls == 2
    record = output.subtask_records[0]
    assert record.attempts == 2


async def test_subtask_exhausts_per_subtask_retries_and_is_skipped_not_fatal() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow"),
            _subtask(id="b", capability_name="course_question_workflow"),
        ],
    )
    handlers = SubtaskHandlerRegistry(default_handler=_AlwaysFailsHandler())
    output = await run_supervisor_shadow(
        input=_run_input(
            planner_output=plan, budget=ExecutionBudget(max_retries_per_subtask=1, max_total_retries=10)
        ),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    # Both subtasks fail (independent, no depends_on) but the plan itself
    # keeps going -- a multi-subtask plan's failures don't fail the whole run.
    assert output.status == "completed_with_warnings"
    assert set(output.failed_subtasks) == {"a", "b"}
    for record in output.subtask_records:
        assert record.attempts == 2  # 1 initial + 1 retry


# ---------------------------------------------------------------------------
# 5. Stops when max_subtasks is exceeded.
# ---------------------------------------------------------------------------


async def test_stops_when_max_subtasks_exceeded() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow"),
            _subtask(id="b", capability_name="course_question_workflow"),
            _subtask(id="c", capability_name="requirement_explanation_workflow"),
        ],
    )
    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan, budget=ExecutionBudget(max_subtasks=1)), settings=_SETTINGS
    )

    assert output.status == "budget_exceeded"
    assert output.completed_subtasks == ["a"]
    assert set(output.skipped_subtasks) == {"b", "c"}
    assert any("max_subtasks" in w for w in output.warnings)


# ---------------------------------------------------------------------------
# 6. Stops when max_total_retries is exceeded.
# ---------------------------------------------------------------------------


async def test_stops_when_max_total_retries_exceeded() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow"),
            _subtask(id="b", capability_name="course_question_workflow"),
        ],
    )
    handlers = SubtaskHandlerRegistry(default_handler=_AlwaysFailsHandler())
    output = await run_supervisor_shadow(
        input=_run_input(
            planner_output=plan, budget=ExecutionBudget(max_retries_per_subtask=10, max_total_retries=1)
        ),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    assert output.status == "budget_exceeded"
    assert any("max_total_retries" in w for w in output.warnings)
    # "a" and "b" have no dependency relationship, so they're dispatched in
    # the same concurrent wave and both get a chance to run — unlike the old
    # strictly-sequential runtime, one exhausting the shared retry budget
    # does not prevent its independent sibling from running too.
    assert set(output.failed_subtasks) == {"a", "b"}
    assert output.skipped_subtasks == []


# ---------------------------------------------------------------------------
# 7. Stops when max_runtime_ms is exceeded.
# ---------------------------------------------------------------------------


async def test_stops_when_max_runtime_exceeded() -> None:
    plan = _plan(subtasks=[_subtask(id="a"), _subtask(id="b", capability_name="graduation_progress_workflow")])
    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan, budget=ExecutionBudget(max_runtime_ms=0)), settings=_SETTINGS
    )

    assert output.status == "budget_exceeded"
    assert output.completed_subtasks == []
    assert set(output.skipped_subtasks) == {"a", "b"}
    assert any("max_runtime_ms" in w for w in output.warnings)


# ---------------------------------------------------------------------------
# 8. Returns compact diagnostics only.
# ---------------------------------------------------------------------------


async def test_returns_compact_diagnostics_only() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)

    assert set(output.diagnostics) == {"budget"}
    budget_summary = output.diagnostics["budget"]
    assert set(budget_summary) == {
        "elapsedMs",
        "subtasksStarted",
        "totalRetries",
        "contextPreviewsCompiled",
    }


# ---------------------------------------------------------------------------
# 9-12. Supervisor never touches real workflows/proposals/Mongo/internal APIs.
# ---------------------------------------------------------------------------


def test_supervisor_package_never_writes_to_mongo_or_creates_proposals() -> None:
    """Phase 7 note: `workflow_adapters.py` legitimately imports the real
    `workflows.registry` (to execute reviewed read-only workflows) -- see
    `tests/unit/test_supervisor_shadow_safety.py` for the dedicated,
    more targeted Phase 7 static safety scan (no Mongo writes, no proposal
    creation, no confirm/reject calls, no direct LLM calls) that still
    applies to every file in this package, including `workflow_adapters.py`.
    """
    supervisor_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor"
    assert supervisor_dir.is_dir()
    forbidden_tokens = (
        "create_agent_action_proposal(",
        "internal_api_client",
        ".insert_one(",
        ".update_one(",
        ".delete_one(",
    )
    for path in supervisor_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{path} must not reference {token!r}"


async def test_dry_run_result_never_claims_real_execution() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)
    record = output.subtask_records[0]
    assert record.result_summary is not None
    assert record.result_summary.get("dryRun") is True


# ---------------------------------------------------------------------------
# 13/14. Context compiler usage -- previews only, never raw compiled context.
# ---------------------------------------------------------------------------


async def test_compiles_context_per_subtask() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)
    record = output.subtask_records[0]
    assert record.context_preview is not None
    assert set(record.context_preview) == {
        "includedSections",
        "omittedSections",
        "warnings",
        "estimatedItems",
    }


async def test_stores_only_context_previews_not_raw_compiled_context() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)
    record = output.subtask_records[0]
    assert "context" not in record.context_preview
    assert "context" not in record.model_dump()
    output_dump = output.model_dump()
    assert "context" not in output_dump


# ---------------------------------------------------------------------------
# 15. Blackboard summaries updated.
# ---------------------------------------------------------------------------


async def test_blackboard_summary_reflects_completed_subtasks() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)
    assert output.blackboard_summary["subtaskResultCount"] == 1
    assert "course_question_workflow" in output.blackboard_summary["capabilitiesUsed"]


# ---------------------------------------------------------------------------
# 16/17. Unknown/disabled capability handled safely.
# ---------------------------------------------------------------------------


async def test_handles_unknown_capability_safely() -> None:
    plan = _plan(subtasks=[_subtask(capability_name="totally_made_up_capability")])
    output = await run_supervisor_shadow(input=_run_input(planner_output=plan), settings=_SETTINGS)

    assert output.status == "completed_with_warnings"
    assert output.skipped_subtasks == ["s1"]
    assert any("unsupported_capability" in w for w in output.warnings)


async def test_handles_disabled_capability_safely() -> None:
    # `planner_agent` exists in the default registry but is disabled (Phase 5+ placeholder).
    plan = _plan(subtasks=[_subtask(capability_name="planner_agent")])
    output = await run_supervisor_shadow(input=_run_input(planner_output=plan), settings=_SETTINGS)

    assert output.status == "completed_with_warnings"
    assert output.skipped_subtasks == ["s1"]


# ---------------------------------------------------------------------------
# 18. Fails safely on invalid PlannerOutput.
# ---------------------------------------------------------------------------


async def test_fails_safely_on_invalid_planner_output() -> None:
    output = await run_supervisor_shadow(
        input=_run_input(planner_output={"not": "a valid planner output"})
    )

    assert output.status == "failed"
    assert output.errors
    assert "invalid_planner_output" in output.errors[0]


# ---------------------------------------------------------------------------
# 19. Fails safely on dependency cycle.
# ---------------------------------------------------------------------------


async def test_fails_safely_on_dependency_cycle() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", depends_on=["b"]),
            _subtask(id="b", depends_on=["a"]),
        ],
    )
    output = await run_supervisor_shadow(input=_run_input(planner_output=plan), settings=_SETTINGS)

    assert output.status == "failed"
    assert output.errors
    assert "cycle" in output.errors[0].lower()


# ---------------------------------------------------------------------------
# 20. No chain-of-thought/scratchpad fields anywhere in supervisor models.
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELD_NAMES = {
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
}


def test_no_chain_of_thought_fields_on_supervisor_models() -> None:
    assert not (_FORBIDDEN_FIELD_NAMES & set(SupervisorRunOutput.model_fields))
    assert not (_FORBIDDEN_FIELD_NAMES & set(SubtaskExecutionRecord.model_fields))
    assert not (_FORBIDDEN_FIELD_NAMES & set(SubtaskResult.model_fields))
    assert not (_FORBIDDEN_FIELD_NAMES & set(SupervisorRunInput.model_fields))


async def test_no_chain_of_thought_in_actual_output_dump() -> None:
    output = await run_supervisor_shadow(input=_run_input(), settings=_SETTINGS)
    dumped_text = str(output.model_dump())
    for forbidden in _FORBIDDEN_FIELD_NAMES:
        assert forbidden not in dumped_text


# ---------------------------------------------------------------------------
# 21. Parallel dispatch of independent subtasks (Phase 4 architecture fix).
# ---------------------------------------------------------------------------


class _ConcurrencyTrackingHandler:
    """Test double: records how many calls were in-flight at once via a
    real `await asyncio.sleep(0)` yield point, so overlap is only observed
    if the runtime genuinely dispatches concurrently rather than awaiting
    each subtask to completion before starting the next."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_observed_in_flight = 0

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard,
        dry_run: bool,
        runtime_context=None,
    ) -> SubtaskResult:
        import asyncio

        self.in_flight += 1
        self.max_observed_in_flight = max(self.max_observed_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="completed",
            confidence=1.0,
        )


async def test_independent_subtasks_dispatch_concurrently() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow", depends_on=[]),
            _subtask(id="b", capability_name="course_question_workflow", depends_on=[]),
            _subtask(id="c", capability_name="requirement_explanation_workflow", depends_on=[]),
        ],
    )
    handler = _ConcurrencyTrackingHandler()
    handlers = SubtaskHandlerRegistry(default_handler=handler)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    assert output.status == "completed"
    assert set(output.completed_subtasks) == {"a", "b", "c"}
    # All three have no dependency relationship -- if they were still
    # dispatched sequentially, at most 1 would ever be in-flight at once.
    assert handler.max_observed_in_flight >= 2


async def test_independent_subtasks_run_concurrently_but_dependent_waits() -> None:
    plan = _plan(
        execution_mode="multi_capability_graph",
        subtasks=[
            _subtask(id="a", capability_name="graduation_progress_workflow", depends_on=[]),
            _subtask(id="b", capability_name="course_question_workflow", depends_on=[]),
            _subtask(
                id="c",
                capability_name="requirement_explanation_workflow",
                depends_on=["a", "b"],
            ),
        ],
    )
    handler = _ConcurrencyTrackingHandler()
    handlers = SubtaskHandlerRegistry(default_handler=handler)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        handler_registry=handlers,
        settings=_SETTINGS,
    )

    assert output.status == "completed"
    assert set(output.completed_subtasks) == {"a", "b", "c"}
    # "a"/"b" overlap (same wave); "c" only becomes ready in the next wave,
    # after both its dependencies have completed -- never overlapping them.
    assert handler.max_observed_in_flight == 2


# ---------------------------------------------------------------------------
# Layer 2 -- `real_execution_allowed_capability_names` governance allowlist.
# ---------------------------------------------------------------------------


async def test_real_execution_allowlist_forces_dry_run_for_excluded_capability() -> None:
    """A capability that is otherwise safety-eligible for real execution
    (`can_shadow_execute_capability` would pass) still degrades to the dry-run
    stand-in when `real_execution_allowed_capability_names` is supplied and
    excludes it -- this is a governance check, independent of and additional
    to the existing safety-metadata checks.
    """
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="course_question_workflow")])
    settings = Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        settings=settings,
        real_execution_allowed_capability_names=frozenset(),
    )

    assert output.status in {"completed", "completed_with_warnings"}
    assert "s1" in output.completed_subtasks
    record = next(r for r in output.subtask_records if r.subtask_id == "s1")
    assert "real_shadow_execution_skipped_not_allowlisted" in " ".join(record.warnings)


async def test_real_execution_allowlist_none_preserves_existing_behavior() -> None:
    """`real_execution_allowed_capability_names=None` (the default, used by
    every caller except `run_planner_first_live_turn`) skips the allowlist
    check entirely -- confirms no behavior change for existing callers.
    """
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="course_question_workflow")])
    settings = Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        settings=settings,
        real_execution_allowed_capability_names=None,
    )

    assert output.status in {"completed", "completed_with_warnings"}
    assert "s1" in output.completed_subtasks
    record = next(r for r in output.subtask_records if r.subtask_id == "s1")
    assert "real_shadow_execution_skipped_not_allowlisted" not in " ".join(record.warnings)


# ---------------------------------------------------------------------------
# Layer 3 -- the same allowlist governance also covers `specialist_agent`
# -type capabilities, not just `workflow`-type ones.
# ---------------------------------------------------------------------------


async def test_real_execution_allowlist_forces_dry_run_for_excluded_specialist_agent() -> None:
    """Mirrors `test_real_execution_allowlist_forces_dry_run_for_excluded_capability`
    above, for a `specialist_agent`-type capability -- defense-in-depth
    parity between the two capability types this allowlist now covers."""
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="graduation_progress_agent")])
    settings = Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        settings=settings,
        real_execution_allowed_capability_names=frozenset(),
    )

    assert output.status in {"completed", "completed_with_warnings"}
    assert "s1" in output.completed_subtasks
    record = next(r for r in output.subtask_records if r.subtask_id == "s1")
    assert "real_shadow_execution_skipped_not_allowlisted" in " ".join(record.warnings)


async def test_real_execution_allowlist_none_preserves_existing_behavior_for_specialist_agent() -> None:
    """`None` (the default) skips the allowlist check entirely for
    `specialist_agent`-type capabilities too, reaching the real
    `SpecialistAgentHandler` exactly as it did before Layer 3 -- which,
    with `AGENT_SPECIALIST_AGENTS_ENABLED` left at its own default `False`,
    degrades to its own pre-existing "skipped" fallback (Phase 10 behavior,
    unrelated to this allowlist). The point of this test is only that the
    Layer 3 allowlist warning is never attached when the allowlist is `None`.
    """
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="graduation_progress_agent")])
    settings = Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True)

    output = await run_supervisor_shadow(
        input=_run_input(planner_output=plan),
        settings=settings,
        real_execution_allowed_capability_names=None,
    )

    assert "s1" in output.skipped_subtasks
    record = next(r for r in output.subtask_records if r.subtask_id == "s1")
    assert "real_shadow_execution_skipped_not_allowlisted" not in " ".join(record.warnings)
