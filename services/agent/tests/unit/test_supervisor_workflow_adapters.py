"""Unit tests for the Phase 7 `ReadOnlyWorkflowAdapterHandler`.

Uses fake workflows (matching `app.agent.workflows.base.AgentWorkflow`'s
shape) rather than the real Mongo-backed workflows, so no database fixture
is needed to exercise the adapter itself.
"""

from __future__ import annotations

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.schemas import AgentResponse, ProposedAction, StreamEvent, StructuredBlock
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SupervisorRuntimeContext
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler


class _FakeReadOnlyWorkflow:
    """Matches `AgentWorkflow`'s shape: yields StreamEvents, then an AgentResponse."""

    name = "graduation_progress_workflow"

    def __init__(self, response: AgentResponse, *, events: list[StreamEvent] | None = None) -> None:
        self._response = response
        self._events = events or []
        self.run_calls: list[dict] = []

    async def run(self, database, *, context, user_message):
        self.run_calls.append({"database": database, "context": context, "user_message": user_message})
        for event in self._events:
            yield event
        yield self._response


class _RaisingWorkflow:
    name = "graduation_progress_workflow"

    async def run(self, database, *, context, user_message):
        yield StreamEvent(type="agent.step.started", label="doomed")
        raise RuntimeError("workflow_exploded")


class _NoResponseWorkflow:
    """A buggy workflow that never yields an `AgentResponse`."""

    name = "graduation_progress_workflow"

    async def run(self, database, *, context, user_message):
        yield StreamEvent(type="agent.step.started", label="never finishes")


def _subtask(**overrides) -> PlannerSubtask:
    defaults = dict(
        id="s1",
        title="Check graduation progress",
        kind="analyze",
        capability_name="graduation_progress_workflow",
        objective="test",
    )
    defaults.update(overrides)
    return PlannerSubtask(**defaults)


def _compiled_context() -> CompiledContext:
    return CompiledContext(
        capability_name="graduation_progress_workflow",
        objective="test",
        context={"user_message": "hi"},
        included_sections=["user_message"],
    )


def _runtime_context(**overrides) -> SupervisorRuntimeContext:
    defaults = dict(database=object(), agent_context_pack=object(), user_message="What am I missing?")
    defaults.update(overrides)
    return SupervisorRuntimeContext(**defaults)


def _blackboard() -> SupervisorBlackboard:
    return SupervisorBlackboard(original_user_message="What am I missing?")


def _agent_response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="conv-1",
        message_id="",
        run_id="run-1",
        text="You still need 12 credits of electives.",
        blocks=[
            StructuredBlock(type="RequirementSummaryBlock", data={"creditsRemaining": 12}),
            StructuredBlock(type="SourceSummaryBlock", data={"provenance": []}),
        ],
        warnings=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _adapter_for(workflow) -> ReadOnlyWorkflowAdapterHandler:
    return ReadOnlyWorkflowAdapterHandler(workflow_lookup=lambda name: workflow)


# ---------------------------------------------------------------------------
# 1/2. Executes fake read-only workflow, collects response without emitting SSE.
# ---------------------------------------------------------------------------


async def test_adapter_executes_fake_read_only_workflow() -> None:
    response = _agent_response()
    workflow = _FakeReadOnlyWorkflow(
        response, events=[StreamEvent(type="agent.step.started", label="Matching requirements")]
    )
    handler = _adapter_for(workflow)

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "completed"
    assert len(workflow.run_calls) == 1
    # The adapter has no SSE emission surface at all -- there is nothing to
    # assert "was not emitted to", but confirm the call args were passed
    # through untouched (database/context/user_message), proving no event
    # stream side channel was introduced.
    call = workflow.run_calls[0]
    assert call["user_message"] == "What am I missing?"


# ---------------------------------------------------------------------------
# 3. Summarizes response compactly.
# ---------------------------------------------------------------------------


async def test_adapter_summarizes_response_compactly() -> None:
    long_text = "x" * 5000
    response = _agent_response(text=long_text)
    handler = _adapter_for(_FakeReadOnlyWorkflow(response))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    summary = result.output_summary
    assert summary["shadowExecuted"] is True
    assert summary["workflowName"] == "graduation_progress_workflow"
    assert len(summary["textPreview"]) < len(long_text)
    assert summary["blockCount"] == 2
    assert summary["blockTypes"] == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert summary["sourceCount"] == 1
    assert summary["proposedActionCount"] == 0
    assert summary["hasProposedActions"] is False


# ---------------------------------------------------------------------------
# 4. Rejects response with proposed actions.
# ---------------------------------------------------------------------------


async def test_adapter_rejects_response_with_proposed_actions() -> None:
    response = _agent_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save plan")
        ]
    )
    handler = _adapter_for(_FakeReadOnlyWorkflow(response))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "failed"
    assert result.confidence == 0.0
    assert any("unsafe_workflow_output_discarded" in w for w in result.warnings)
    assert result.output_summary["shadowExecuted"] is False


# ---------------------------------------------------------------------------
# 4b. Post-Phase-9: `allow_single_proposed_action` tolerates exactly one
# proposed action, still rejects two or more.
# ---------------------------------------------------------------------------


async def test_adapter_still_rejects_proposed_actions_by_default_regardless_of_flag_absence() -> None:
    """Sanity: omitting the new constructor param preserves exact prior behavior."""
    response = _agent_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save plan")
        ]
    )
    handler = ReadOnlyWorkflowAdapterHandler(workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "failed"


async def test_adapter_tolerates_single_proposed_action_when_opted_in() -> None:
    response = _agent_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save plan")
        ]
    )
    handler = ReadOnlyWorkflowAdapterHandler(
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response), allow_single_proposed_action=True
    )

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "completed"
    assert result.output_summary["hasProposedActions"] is True
    assert result.output_summary["proposedActionCount"] == 1


async def test_adapter_still_rejects_two_proposed_actions_even_when_opted_in() -> None:
    response = _agent_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save plan"),
            ProposedAction(id="a2", action_type="save_semester_plan", label="Save 2", title="Save plan 2"),
        ]
    )
    handler = ReadOnlyWorkflowAdapterHandler(
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response), allow_single_proposed_action=True
    )

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "failed"
    assert result.output_summary["reason"] == "unexpected_multiple_proposed_actions"


async def test_adapter_tolerating_proposed_actions_still_populates_candidate_sink() -> None:
    response = _agent_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save plan")
        ]
    )
    sink: dict = {}
    handler = ReadOnlyWorkflowAdapterHandler(
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
        allow_single_proposed_action=True,
        candidate_sink=sink,
    )

    await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert sink["graduation_progress_workflow"] is response


# ---------------------------------------------------------------------------
# 5. Returns failed/skipped safely when workflow raises or produces nothing.
# ---------------------------------------------------------------------------


async def test_adapter_returns_failed_when_workflow_raises() -> None:
    handler = _adapter_for(_RaisingWorkflow())

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "failed"
    assert result.error == "workflow_exploded"


async def test_adapter_returns_skipped_when_workflow_produces_no_response() -> None:
    handler = _adapter_for(_NoResponseWorkflow())

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "skipped"
    assert result.output_summary["shadowExecuted"] is False


async def test_adapter_returns_skipped_when_capability_has_no_workflow() -> None:
    handler = ReadOnlyWorkflowAdapterHandler(workflow_lookup=lambda name: None)

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert result.status == "skipped"
    assert any("workflow_adapter_no_workflow_for" in w for w in result.warnings)


async def test_adapter_returns_skipped_when_runtime_context_missing() -> None:
    handler = _adapter_for(_FakeReadOnlyWorkflow(_agent_response()))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=None,
    )

    assert result.status == "skipped"
    assert result.output_summary["shadowExecuted"] is False
    assert "real_shadow_execution_requires_runtime_context" in result.warnings


# ---------------------------------------------------------------------------
# 6/7. Never writes to Mongo, never creates an action proposal.
# ---------------------------------------------------------------------------


async def test_adapter_never_calls_database_methods_directly() -> None:
    """The adapter passes the database handle straight to the (fake) workflow
    and never calls any method on it itself."""

    class _TrackedDatabase:
        def __getattr__(self, name):  # pragma: no cover - triggers only on misuse
            raise AssertionError(f"adapter must not call database.{name} directly")

    response = _agent_response()
    handler = _adapter_for(_FakeReadOnlyWorkflow(response))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(database=_TrackedDatabase()),
    )

    assert result.status == "completed"


async def test_adapter_produces_no_proposed_actions_on_the_blackboard() -> None:
    response = _agent_response()
    handler = _adapter_for(_FakeReadOnlyWorkflow(response))
    board = _blackboard()

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=board,
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    board.add_subtask_result(result)

    assert board.proposed_action_summaries == []


# ---------------------------------------------------------------------------
# 8. Does not expose raw blocks/large text.
# ---------------------------------------------------------------------------


async def test_adapter_output_summary_never_contains_raw_blocks_or_full_text() -> None:
    long_text = "credits remaining detail " * 200
    response = _agent_response(
        text=long_text,
        blocks=[StructuredBlock(type="RequirementBucketBlock", data={"huge": ["x"] * 500})],
    )
    handler = _adapter_for(_FakeReadOnlyWorkflow(response))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    summary_text = str(result.output_summary)
    assert long_text not in summary_text
    assert "huge" not in summary_text
    assert '"data"' not in summary_text


# ---------------------------------------------------------------------------
# 9. shadowExecuted=true only when actually executed.
# ---------------------------------------------------------------------------


async def test_shadow_executed_true_only_on_real_success() -> None:
    ok_result = await _adapter_for(_FakeReadOnlyWorkflow(_agent_response())).run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    assert ok_result.output_summary["shadowExecuted"] is True

    missing_context_result = await _adapter_for(_FakeReadOnlyWorkflow(_agent_response())).run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=None,
    )
    assert missing_context_result.output_summary["shadowExecuted"] is False

    no_workflow_result = await ReadOnlyWorkflowAdapterHandler(workflow_lookup=lambda name: None).run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    assert no_workflow_result.output_summary["shadowExecuted"] is False


# ---------------------------------------------------------------------------
# 10. candidate_sink collision handling for duplicate capability names.
# ---------------------------------------------------------------------------


async def test_candidate_sink_populated_normally_for_a_single_subtask() -> None:
    response = _agent_response()
    sink: dict = {}
    handler = ReadOnlyWorkflowAdapterHandler(
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response), candidate_sink=sink
    )

    await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert sink["graduation_progress_workflow"] is response


async def test_candidate_sink_collision_discards_ambiguous_candidate() -> None:
    """Two subtasks for the same capability name must never let the sink
    nondeterministically keep whichever finished first/last -- both should
    be discarded so promotion is safely skipped rather than comparing
    against an arbitrary candidate."""
    sink: dict = {}
    handler = ReadOnlyWorkflowAdapterHandler(
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(_agent_response()), candidate_sink=sink
    )

    await handler.run(
        subtask=_subtask(id="s1"),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    assert "graduation_progress_workflow" in sink

    await handler.run(
        subtask=_subtask(id="s2"),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    assert "graduation_progress_workflow" not in sink

    # A third subtask for the same capability must not resurrect the entry.
    await handler.run(
        subtask=_subtask(id="s3"),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )
    assert "graduation_progress_workflow" not in sink
