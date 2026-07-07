"""Unit tests for the Phase 8 post-context shadow compare runner
(`supervisor/post_context_runner.py`).

Uses fake database/`AgentContextPack` stand-ins and, where real execution
matters, relies on `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` staying off (or
targeting capabilities that are refused/deferred before any real workflow
lookup happens) so no real Mongo/workflow/LLM dependency is required.

`run_post_context_shadow_compare` returns a `PostContextShadowCompareOutcome`
(or `None`) as of Phase 9 (it used to return a bare `dict | None` in Phase
8) — `_run` below returns that outcome object directly; tests that only
care about the Phase 8 validation metadata read `.validation_metadata`.
"""

from __future__ import annotations

import pytest

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.supervisor import post_context_runner as post_context_runner_module
from app.agent.supervisor.post_context_runner import (
    PostContextShadowCompareOutcome,
    run_post_context_shadow_compare,
)
from app.agent.supervisor.schemas import SupervisorRuntimeContext
from app.config import Settings


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="conv-1",
        message_id="",
        run_id="run-1",
        text="You still need 12 credits.",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={})],
        warnings=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _plan(capability_name: str = "graduation_progress_workflow") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-post-context-1",
        "user_goal": "What am I missing to graduate?",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": "check_progress",
                "title": "Check graduation progress",
                "kind": "analyze",
                "capability_name": capability_name,
                "objective": "Determine remaining requirements toward graduation.",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


_OFF_SETTINGS = Settings(
    OPENAI_API_KEY=None,
    AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED=False,
    AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=False,
)
_ON_SETTINGS = Settings(
    OPENAI_API_KEY=None,
    AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED=True,
    AGENT_SUPERVISOR_VALIDATION_ENABLED=True,
    # Explicit, not relied-on-default: this settings object is specifically
    # for the *without* real handlers/promotion case (see
    # `_ON_WITH_REAL_HANDLERS_SETTINGS` below) -- the fake
    # `agent_context_pack`/`database` placeholders `_run` constructs below
    # only stay safe to use when real execution never actually touches
    # them, which requires this explicitly off regardless of what an
    # operator's ambient `.env` sets it to.
    AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=False,
    AGENT_SUPERVISOR_PROMOTION_ENABLED=False,
    # Also explicit: `run_post_context_shadow_compare` independently checks
    # synthesis-text-promotion regardless of supervisor promotion (Phase 22)
    # -- an operator's real `.env` may have this on (as this repo's own root
    # `.env` does, post-Phase-9), which would otherwise silently populate
    # `promoted_response` here too.
    AGENT_SYNTHESIS_ENABLED=False,
    AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False,
)
_ON_WITH_REAL_HANDLERS_SETTINGS = Settings(
    OPENAI_API_KEY=None,
    AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED=True,
    AGENT_SUPERVISOR_VALIDATION_ENABLED=True,
    AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True,
    AGENT_SUPERVISOR_PROMOTION_ENABLED=False,
    AGENT_SYNTHESIS_ENABLED=False,
    AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False,
)


_UNSET = object()


async def _run(
    *,
    settings: Settings,
    live_response: AgentResponse | None = _UNSET,
    planner_output: dict | None = _UNSET,
    agent_context_pack: object | None = "fake-context-pack",
    database: object | None = "fake-database",
    live_workflow_name: str = "graduation_progress_workflow",
) -> PostContextShadowCompareOutcome | None:
    return await run_post_context_shadow_compare(
        database=database,
        agent_context_pack=agent_context_pack,
        user_message="What am I missing to graduate?",
        user_id="user-1",
        conversation_id="conv-1",
        run_id="run-1",
        live_workflow_name=live_workflow_name,
        live_response=_response() if live_response is _UNSET else live_response,
        planner_output=_plan() if planner_output is _UNSET else planner_output,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# 1. Runner does nothing when flag disabled.
# ---------------------------------------------------------------------------


async def test_runner_does_nothing_when_flag_disabled(monkeypatch) -> None:
    called = False

    async def _boom(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("run_supervisor_shadow must not be called when the flag is off")

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _boom)

    result = await _run(settings=_OFF_SETTINGS)

    assert result is None
    assert called is False


# ---------------------------------------------------------------------------
# 2. Runner runs shadow compare when flag enabled and context is available.
# ---------------------------------------------------------------------------


async def test_runner_runs_shadow_compare_when_enabled() -> None:
    outcome = await _run(settings=_ON_SETTINGS)

    assert outcome is not None
    metadata = outcome.validation_metadata
    assert metadata is not None
    assert metadata["liveWorkflowName"] == "graduation_progress_workflow"
    assert metadata["shadowStatus"] in ("completed", "completed_with_warnings")
    assert "status" in metadata and "safeToPromote" in metadata
    # Promotion wasn't configured for this settings object -- no promotion
    # metadata and no candidate response.
    assert outcome.promotion_metadata is None
    assert outcome.promoted_response is None


async def test_runner_returns_none_without_planner_output() -> None:
    result = await _run(settings=_ON_SETTINGS, planner_output=None)
    assert result is None


async def test_runner_returns_none_without_live_response() -> None:
    result = await _run(settings=_ON_SETTINGS, live_response=None)
    assert result is None


# ---------------------------------------------------------------------------
# 3. Runner passes a `SupervisorRuntimeContext` with allow_side_effects=False.
# ---------------------------------------------------------------------------


async def test_runner_passes_runtime_context_with_no_side_effects(monkeypatch) -> None:
    captured: dict[str, object] = {}
    original = post_context_runner_module.run_supervisor_shadow

    async def _capture(*, input, handler_registry=None, runtime_context=None, settings=None):
        captured["runtime_context"] = runtime_context
        return await original(
            input=input, handler_registry=handler_registry, runtime_context=runtime_context, settings=settings
        )

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _capture)

    await _run(settings=_ON_SETTINGS)

    runtime_context = captured["runtime_context"]
    assert isinstance(runtime_context, SupervisorRuntimeContext)
    assert runtime_context.allow_side_effects is False
    assert runtime_context.shadow_execution is True


# ---------------------------------------------------------------------------
# 4. Runner never emits SSE (it is a plain awaited value-returning call).
# ---------------------------------------------------------------------------


async def test_runner_never_emits_stream_events() -> None:
    result = await _run(settings=_ON_SETTINGS)

    assert result is None or isinstance(result, PostContextShadowCompareOutcome)


# ---------------------------------------------------------------------------
# 5. Runner never mutates the `AgentResponse` passed in.
# ---------------------------------------------------------------------------


async def test_runner_never_mutates_live_response() -> None:
    live = _response()
    before = live.model_dump()

    await _run(settings=_ON_SETTINGS, live_response=live)

    assert live.model_dump() == before


# ---------------------------------------------------------------------------
# 6. Runner stores compact diagnostics only.
# ---------------------------------------------------------------------------


async def test_runner_stores_compact_diagnostics_only() -> None:
    long_text = "sensitive baseline answer text " * 200
    live = _response(text=long_text)

    outcome = await _run(settings=_ON_SETTINGS, live_response=live)

    assert outcome is not None
    result_text = str(outcome.validation_metadata)
    assert long_text not in result_text
    for forbidden in (
        "raw_context",
        "compiled_context",
        "chain_of_thought",
        "scratchpad",
        "proposed_action_payload",
        "raw_pdf_bytes",
    ):
        assert forbidden not in result_text


# ---------------------------------------------------------------------------
# 7. Runner handles supervisor failure without raising.
# ---------------------------------------------------------------------------


async def test_runner_handles_supervisor_failure_without_raising(monkeypatch) -> None:
    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _boom)

    result = await _run(settings=_ON_SETTINGS)

    assert result is None


# ---------------------------------------------------------------------------
# 8. Runner skips unsafe proposal workflow execution (does not duplicate a proposal).
# ---------------------------------------------------------------------------


async def test_runner_skips_unsafe_proposal_workflow() -> None:
    outcome = await _run(
        settings=_ON_WITH_REAL_HANDLERS_SETTINGS,
        planner_output=_plan("semester_planning_workflow"),
        live_workflow_name="semester_planning_workflow",
    )

    assert outcome is not None
    metadata = outcome.validation_metadata
    # No shadow-executed real workflow output and no proposed actions leaked
    # through -- the capability was refused before any real workflow ran.
    assert metadata["shadowProposedActionCount"] == 0
    assert metadata["status"] in ("passed", "passed_with_warnings")
    # semester_planning_workflow is never promotion-eligible.
    assert outcome.promoted_response is None


# ---------------------------------------------------------------------------
# 9. Runner does not run real handlers if `AgentContextPack` is missing.
# ---------------------------------------------------------------------------


async def test_runner_does_not_run_real_handlers_without_context_pack(monkeypatch) -> None:
    captured: dict[str, object] = {}
    original = post_context_runner_module.run_supervisor_shadow

    async def _capture(*, input, handler_registry=None, runtime_context=None, settings=None):
        captured["runtime_context"] = runtime_context
        return await original(
            input=input, handler_registry=handler_registry, runtime_context=runtime_context, settings=settings
        )

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _capture)

    outcome = await _run(settings=_ON_WITH_REAL_HANDLERS_SETTINGS, agent_context_pack=None)

    assert captured["runtime_context"].agent_context_pack is None
    assert outcome is not None
    # Falls back to the safe dry-run handler -- never a real shadow execution.
    assert outcome.validation_metadata["shadowBlockCount"] == 0
    assert outcome.promoted_response is None


# ---------------------------------------------------------------------------
# 10. Runner does not call an LLM directly (general_academic_workflow is
#     excluded from real execution by default even with real handlers on).
# ---------------------------------------------------------------------------


async def test_runner_never_triggers_llm_for_general_academic_workflow() -> None:
    outcome = await _run(
        settings=_ON_WITH_REAL_HANDLERS_SETTINGS,
        planner_output=_plan("general_academic_workflow"),
        live_workflow_name="general_academic_workflow",
    )

    assert outcome is not None
    metadata = outcome.validation_metadata
    # A real execution would have produced `shadowExecuted=True` blocks;
    # the operationally-expensive gate keeps this a dry-run instead.
    assert metadata["shadowBlockCount"] == 0
    assert metadata["status"] in ("passed", "passed_with_warnings")
    # general_academic_workflow is never promotion-eligible either way.
    assert outcome.promoted_response is None


def test_post_context_runner_module_makes_no_direct_llm_calls() -> None:
    import pathlib

    module_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "agent"
        / "supervisor"
        / "post_context_runner.py"
    )
    text = module_path.read_text(encoding="utf-8")
    for forbidden in ("ChatLLMAdapter(", "llm.ainvoke(", "llm.invoke(", "ChatOpenAI(", "build_chat_llm("):
        assert forbidden not in text
