"""Unit tests for synthesis text promoted response builder (Phase 22)."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.synthesis.response_builder import build_synthesis_text_promoted_response


def _live(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Live text",
        blocks=[StructuredBlock(type="GraduationStatusBlock", data={"creditsRemaining": 40.0})],
        warnings=["warn"],
        suggested_prompts=["next?"],
        proposed_actions=[],
        assumptions=["assumption"],
        used_sources=["source"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def test_only_text_changes() -> None:
    live = _live()
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text="Synthesis text")
    assert promoted.text == "Synthesis text"
    assert live.text == "Live text"


def test_blocks_unchanged() -> None:
    live = _live()
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text="New")
    assert promoted.blocks == live.blocks


def test_warnings_unchanged() -> None:
    live = _live()
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text="New")
    assert promoted.warnings == live.warnings


def test_sources_unchanged() -> None:
    live = _live()
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text="New")
    assert promoted.used_sources == live.used_sources


def test_proposed_actions_unchanged() -> None:
    action = ProposedAction(id="a1", action_type="x", label="t", payload={})
    live = _live(proposed_actions=[action])
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text="New")
    assert promoted.proposed_actions == live.proposed_actions


def test_original_live_response_not_mutated() -> None:
    live = _live()
    build_synthesis_text_promoted_response(live_response=live, candidate_text="Changed")
    assert live.text == "Live text"


def test_malformed_response_returns_unchanged() -> None:
    result = build_synthesis_text_promoted_response(live_response="bad", candidate_text="New")  # type: ignore[arg-type]
    assert result == "bad"
