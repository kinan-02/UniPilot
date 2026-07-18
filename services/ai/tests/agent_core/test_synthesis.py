"""Tests for `agent_core.synthesis.synthesis.compose_answer`.

This tests the Orchestrator's terminal synthesis step, confirming it correctly
delegates to the Composition reasoning block (`run_composition_subagent`) with
the full unsliced dependency state, rather than a sliced subset.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.agent_core.certainty import CertaintyTag
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.schemas import SubagentResult
from app.agent_core.synthesis import synthesis as synthesis_module


def _result(*, status: str, warnings: list[str], answer_text: str | None = None) -> SubagentResult:
    return SubagentResult(
        status=status,  # type: ignore[arg-type]
        result={"answer_text": answer_text} if answer_text is not None else None,
        certainty=CertaintyTag(basis="llm_interpretation", confidence=0.5),
        warnings=warnings,
    )


@pytest.mark.asyncio
async def test_compose_answer_passes_the_full_unsliced_state_as_dependency_state(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_context = []

    async def fake_run_composition_subagent(*, context_package, llm_adapter, block_id, **kwargs):
        captured_context.append(context_package)
        return _result(status="succeeded", warnings=[], answer_text="The composed answer.")

    monkeypatch.setattr(synthesis_module, "run_composition_subagent", fake_run_composition_subagent)

    # Build a state with multiple entries to prove they are passed verbatim.
    state = PlanExecutionState(plan_id="p1")
    state.entries.append(
        StateEntry(
            entry_id="e1",
            step_id="1",
            role="retrieval",
            status="succeeded",
            output_schema_name="dummy",
            certainty=CertaintyTag(basis="wiki_derived", confidence=1.0),
            produced_at=datetime.now(timezone.utc)
        )
    )
    state.entries.append(
        StateEntry(
            entry_id="e2",
            step_id="2",
            role="interpretation",
            status="succeeded",
            output_schema_name="dummy",
            certainty=CertaintyTag(basis="llm_interpretation", confidence=0.8),
            produced_at=datetime.now(timezone.utc)
        )
    )

    await synthesis_module.compose_answer(
        state=state,
        user_goal="What courses have I completed?",
        composition_role=build_default_role_roster()["composition"],
        tool_registry=None,
        llm_adapter=None,
        block_id="p1-synthesis",
    )

    assert len(captured_context) == 1
    pkg = captured_context[0]
    # The full unsliced state must be passed down.
    assert len(pkg.dependency_state) == 2
    assert pkg.dependency_state[0].step_id == "1"
    assert pkg.dependency_state[1].step_id == "2"


@pytest.mark.asyncio
async def test_compose_answer_raises_on_a_nonempty_tool_grant() -> None:
    role = build_default_role_roster()["composition"].model_copy(
        update={"tool_grant_ceiling": ("search_knowledge",)}
    )

    with pytest.raises(ValueError, match="zero tool grant"):
        await synthesis_module.compose_answer(
            state=PlanExecutionState(plan_id="p1"),
            user_goal="Does this fail?",
            composition_role=role,
            tool_registry=None,
            llm_adapter=None,
            block_id="p1-synthesis",
        )


@pytest.mark.asyncio
async def test_compose_answer_delegates_to_run_composition_subagent_and_returns_its_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_composition_subagent(*, context_package, llm_adapter, block_id, **kwargs):
        return _result(status="failed", warnings=["something_went_wrong"], answer_text=None)

    monkeypatch.setattr(synthesis_module, "run_composition_subagent", fake_run_composition_subagent)

    result = await synthesis_module.compose_answer(
        state=PlanExecutionState(plan_id="p1"),
        user_goal="What courses have I completed?",
        composition_role=build_default_role_roster()["composition"],
        tool_registry=None,
        llm_adapter=None,
        block_id="p1-synthesis",
    )

    # Returns the exact object the wrapper returned, no manipulation
    assert result.status == "failed"
    assert result.warnings == ["something_went_wrong"]
