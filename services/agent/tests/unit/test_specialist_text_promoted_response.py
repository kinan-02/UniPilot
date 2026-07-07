"""Unit tests for `app.agent.specialists.text_promotion.build_text_promoted_response` (Phase 14)."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.specialists.text_promotion import build_text_promoted_response


def _live_response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="You have 40 credits remaining.",
        blocks=[StructuredBlock(type="GraduationStatusBlock", data={"creditsRemaining": 40.0})],
        warnings=["Some data may be outdated."],
        suggested_prompts=["What courses should I take next?"],
        proposed_actions=[],
        assumptions=["Using latest completed-course data on file."],
        used_sources=["degree_requirements:r1"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


# ---------------------------------------------------------------------------
# 1. Only text changes.
# ---------------------------------------------------------------------------


def test_only_text_changes() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="A better explanation of your progress.")

    assert promoted.text == "A better explanation of your progress."
    assert promoted.text != live.text


# ---------------------------------------------------------------------------
# 2. Blocks unchanged.
# ---------------------------------------------------------------------------


def test_blocks_unchanged() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.blocks == live.blocks
    assert [b.model_dump() for b in promoted.blocks] == [b.model_dump() for b in live.blocks]


# ---------------------------------------------------------------------------
# 3. Warnings unchanged.
# ---------------------------------------------------------------------------


def test_warnings_unchanged() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.warnings == live.warnings


# ---------------------------------------------------------------------------
# 4. Sources unchanged.
# ---------------------------------------------------------------------------


def test_sources_unchanged() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.used_sources == live.used_sources


# ---------------------------------------------------------------------------
# 5. proposed_actions unchanged.
# ---------------------------------------------------------------------------


def test_proposed_actions_unchanged_when_empty() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.proposed_actions == []
    assert promoted.proposed_actions == live.proposed_actions


def test_proposed_actions_unchanged_when_populated() -> None:
    """Defense-in-depth: even if a caller passed a live response with
    proposed actions (should never happen -- the gate blocks on
    `live_response_has_proposed_actions`), construction itself never
    strips or alters them -- it copies exactly."""
    action = ProposedAction(
        id="a1", action_type="save_semester_plan", label="Save plan", payload={}, requires_confirmation=True
    )
    live = _live_response(proposed_actions=[action])
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.proposed_actions == [action]


# ---------------------------------------------------------------------------
# Other fields (assumptions, message_id, run_id, conversation_id) unchanged.
# ---------------------------------------------------------------------------


def test_other_fields_unchanged() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted.conversation_id == live.conversation_id
    assert promoted.message_id == live.message_id
    assert promoted.run_id == live.run_id
    assert promoted.assumptions == live.assumptions
    assert promoted.suggested_prompts == live.suggested_prompts


# ---------------------------------------------------------------------------
# 6. Original live response is not mutated.
# ---------------------------------------------------------------------------


def test_original_live_response_not_mutated() -> None:
    live = _live_response()
    original_text = live.text

    build_text_promoted_response(live_response=live, answer_text="A completely different answer.")

    assert live.text == original_text


def test_returned_response_is_a_distinct_object() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert promoted is not live


# ---------------------------------------------------------------------------
# 7. Malformed live response fails safely.
# ---------------------------------------------------------------------------


def test_malformed_live_response_fails_safely() -> None:
    malformed = {"text": "not a real AgentResponse"}

    result = build_text_promoted_response(live_response=malformed, answer_text="New text")  # type: ignore[arg-type]

    # Never raises -- degrades to returning the malformed input unchanged
    # rather than fabricating a fake AgentResponse.
    assert result is malformed


def test_none_live_response_fails_safely() -> None:
    result = build_text_promoted_response(live_response=None, answer_text="New text")  # type: ignore[arg-type]
    assert result is None


def test_returned_response_type_is_agent_response_for_valid_input() -> None:
    live = _live_response()
    promoted = build_text_promoted_response(live_response=live, answer_text="New text")

    assert isinstance(promoted, AgentResponse)
