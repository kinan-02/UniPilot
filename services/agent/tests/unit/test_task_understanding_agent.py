"""Unit tests for the Task Understanding Agent (Phase 3).

All tests use a fake `ReasoningBlock` — no real LLM call is made.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.task_understanding.agent import understand_user_task
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
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


def _result(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        status="completed",
        user_goal="Check graduation progress.",
        normalized_request="What is the student missing to graduate?",
        primary_intent="graduation_progress_check",
        secondary_intents=[],
        task_category="academic_analysis",
        task_complexity="medium",
        recommended_autonomy_level=2,
        suggested_next_layer="deterministic_workflow",
        required_context=["student_profile", "completed_courses"],
        missing_context=[],
        extracted_entities={},
        assumptions=[],
        requires_user_confirmation=False,
        write_risk="none",
        clarifying_questions=[],
        intent_confidence=0.9,
        overall_confidence=0.85,
        decision_summary="Student is asking about graduation progress.",
        warnings=[],
    )
    defaults.update(overrides)
    return defaults


def _completed_output(result: dict[str, Any], **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary="understood",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.9,
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
    base = {"AGENT_TASK_UNDERSTANDING_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# 1. Successful task understanding from fake ReasoningBlock output.
# ---------------------------------------------------------------------------


async def test_successful_task_understanding_from_fake_reasoning_block():
    fake = FakeReasoningBlock(_completed_output(_result()))
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        settings=settings,
        reasoning_block=fake,
    )

    assert len(fake.calls) == 1
    assert isinstance(output, TaskUnderstandingOutput)
    assert output.status == "completed"
    assert output.primary_intent == "graduation_progress_check"
    assert output.source == "llm_reasoning_block"
    assert output.task_category == "academic_analysis"


# ---------------------------------------------------------------------------
# 2 & 3. Hebrew / mixed Hebrew-English message classification.
# ---------------------------------------------------------------------------


async def test_hebrew_user_message_classification():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                user_goal="לבדוק כמה נקודות זכות חסרות לתואר",
                normalized_request="בדיקת התקדמות לתואר",
                decision_summary="הסטודנט שואל על התקדמות לתואר.",
            )
        )
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="כמה נקודות חסרות לי לסיים את התואר?",
        settings=settings,
        reasoning_block=fake,
        locale_hint="he",
    )

    assert output.primary_intent == "graduation_progress_check"
    assert "תואר" in output.user_goal
    task_context = fake.calls[0].task_context
    assert task_context["locale_hint"] == "he"
    assert task_context["user_message"] == "כמה נקודות חסרות לי לסיים את התואר?"


async def test_mixed_hebrew_english_message_classification():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                user_goal="Check if course 234218 is offered next semester",
                normalized_request="Is course 234218 offered next semester?",
                primary_intent="course_question",
                task_category="simple_question",
                required_context=["course_offering"],
            )
        )
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="האם הקורס 234218 offered בסמסטר הבא?",
        deterministic_intent="course_question",
        deterministic_intent_confidence=0.75,
        settings=settings,
        reasoning_block=fake,
    )

    assert output.primary_intent == "course_question"
    assert output.task_category == "simple_question"


# ---------------------------------------------------------------------------
# 4. Multi-intent task (graduation simulation + semester planning).
# ---------------------------------------------------------------------------


async def test_multi_intent_task_produces_secondary_intents():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                user_goal="See if graduation is possible after planning next semester.",
                normalized_request="Simulate graduation progress if the suggested semester plan is taken.",
                primary_intent="graduation_progress_check",
                secondary_intents=["semester_plan_generation"],
                task_category="multi_step_task",
                task_complexity="high",
                recommended_autonomy_level=4,
                suggested_next_layer="planner",
            )
        )
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="Can I graduate if I take these courses next semester?",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.primary_intent == "graduation_progress_check"
    assert output.secondary_intents == ["semester_plan_generation"]
    assert output.task_category == "multi_step_task"
    assert output.recommended_autonomy_level == 4
    assert output.suggested_next_layer == "planner"


# ---------------------------------------------------------------------------
# 5. Transcript import with attachment metadata.
# ---------------------------------------------------------------------------


async def test_transcript_import_with_attachment_metadata():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                user_goal="Import an official transcript.",
                normalized_request="Import and review the uploaded transcript.",
                primary_intent="transcript_import",
                task_category="transcript_processing",
                required_context=["uploaded_file"],
            )
        )
    )
    settings = _settings_enabled()
    attachments = [
        {
            "type": "transcript_pdf",
            "filename": "transcript.pdf",
            "contentType": "application/pdf",
            "parsePreview": {"rows": [{"courseNumber": "234218", "grade": 90}] * 50},
        }
    ]

    output = await understand_user_task(
        user_message="Import my transcript",
        attachment_metadata=attachments,
        settings=settings,
        reasoning_block=fake,
    )

    assert output.primary_intent == "transcript_import"
    assert output.task_category == "transcript_processing"

    sent_attachments = fake.calls[0].task_context["attachment_metadata"]
    assert sent_attachments == [
        {"type": "transcript_pdf", "filename": "transcript.pdf", "contentType": "application/pdf"}
    ]
    # Attachment *contents* (parsed rows) must never reach the reasoning context.
    assert "parsePreview" not in sent_attachments[0]
    assert "rows" not in str(sent_attachments)


# ---------------------------------------------------------------------------
# 6. Explicit save/write request.
# ---------------------------------------------------------------------------


async def test_explicit_write_request_sets_confirmation_and_write_risk():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                user_goal="Save the chosen semester plan.",
                normalized_request="Save the selected semester plan option.",
                primary_intent="semester_plan_generation",
                task_category="write_or_update_request",
                requires_user_confirmation=False,  # LLM under-reported; reconciler must fix it
                write_risk="none",
            )
        )
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="Import this transcript and save it",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.requires_user_confirmation is True
    assert output.write_risk == "explicit"


async def test_non_write_request_does_not_force_confirmation():
    fake = FakeReasoningBlock(_completed_output(_result()))
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.requires_user_confirmation is False
    assert output.write_risk == "none"


# ---------------------------------------------------------------------------
# 7. Missing profile/degree/catalog context.
# ---------------------------------------------------------------------------


async def test_missing_profile_context_is_surfaced():
    fake = FakeReasoningBlock(
        _completed_output(
            _result(
                status="needs_more_context",
                missing_context=["student_profile", "degree_requirements"],
                suggested_next_layer="clarification",
                clarifying_questions=["What is your degree program and catalog year?"],
            )
        )
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.status == "needs_more_context"
    assert "student_profile" in output.missing_context
    assert "degree_requirements" in output.missing_context
    assert output.clarifying_questions


# ---------------------------------------------------------------------------
# 8. Unknown LLM intent rejected, falls back to deterministic intent.
# ---------------------------------------------------------------------------


async def test_unknown_llm_intent_falls_back_to_deterministic_intent():
    fake = FakeReasoningBlock(
        _completed_output(_result(primary_intent="totally_made_up_intent"))
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        settings=settings,
        reasoning_block=fake,
    )

    assert output.primary_intent == "graduation_progress_check"
    assert any("unsupported_primary_intent_replaced" in w for w in output.warnings)


async def test_unknown_llm_intent_falls_back_to_unknown_value_without_deterministic_intent():
    fake = FakeReasoningBlock(_completed_output(_result(primary_intent="not_a_real_intent")))
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="asdkjhasdkjh",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.primary_intent == "unknown_or_unsupported"


async def test_unsupported_secondary_intents_are_dropped_with_warning():
    fake = FakeReasoningBlock(
        _completed_output(_result(secondary_intents=["course_question", "not_a_real_intent"]))
    )
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        settings=settings,
        reasoning_block=fake,
    )

    assert output.secondary_intents == ["course_question"]
    assert any("unsupported_secondary_intent_dropped" in w for w in output.warnings)


# ---------------------------------------------------------------------------
# 9. ReasoningBlock failure returns deterministic fallback.
# ---------------------------------------------------------------------------


async def test_reasoning_block_failure_returns_deterministic_fallback():
    fake = FakeReasoningBlock(_failed_output())
    settings = _settings_enabled()

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        deterministic_entities={"courseNumber": "234218"},
        settings=settings,
        reasoning_block=fake,
    )

    assert output.source == "deterministic_fallback"
    assert output.status == "completed"
    assert output.primary_intent == "graduation_progress_check"
    assert output.extracted_entities == {"courseNumber": "234218"}
    assert "task_understanding_llm_unavailable_or_failed" in output.warnings


# ---------------------------------------------------------------------------
# 10. LLM unavailable (real ChatLLMAdapter, no API key) returns deterministic fallback.
# ---------------------------------------------------------------------------


async def test_llm_unavailable_returns_deterministic_fallback_without_crashing():
    unconfigured_settings = _settings_enabled(**{"OPENAI_API_KEY": None})
    block = ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=unconfigured_settings))

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        settings=unconfigured_settings,
        reasoning_block=block,
    )

    assert output.source == "deterministic_fallback"
    assert output.status == "completed"
    assert output.primary_intent == "graduation_progress_check"


async def test_flag_disabled_returns_deterministic_fallback_without_calling_reasoning_block():
    fake = FakeReasoningBlock()
    settings = Settings(**{"AGENT_TASK_UNDERSTANDING_ENABLED": False})

    output = await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        settings=settings,
        reasoning_block=fake,
    )

    assert fake.calls == []
    assert output.source == "deterministic_fallback"
    assert "task_understanding_disabled" in output.warnings


# ---------------------------------------------------------------------------
# 11. No chain-of-thought / scratchpad fields anywhere.
# ---------------------------------------------------------------------------


def test_no_chain_of_thought_or_scratchpad_fields_in_output_model():
    from app.agent.task_understanding.schemas import TaskUnderstandingInput

    banned = {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
    for model in (TaskUnderstandingInput, TaskUnderstandingOutput):
        field_names = {name.lower() for name in model.model_fields}
        leaked = field_names & banned
        assert not leaked, f"{model.__name__} exposes banned field(s): {leaked}"


# ---------------------------------------------------------------------------
# 12. Context passed to ReasoningBlock is minimal; forbidden large fields absent.
# ---------------------------------------------------------------------------


async def test_reasoning_context_excludes_large_forbidden_fields():
    fake = FakeReasoningBlock(_completed_output(_result()))
    settings = _settings_enabled()

    await understand_user_task(
        user_message="What am I missing to graduate?",
        deterministic_intent="graduation_progress_check",
        deterministic_intent_confidence=0.9,
        existing_entities={"courseNumber": "234218"},
        user_profile_summary={"degreeProgram": "Computer Science", "catalogYear": 2025},
        settings=settings,
        reasoning_block=fake,
    )

    task_context = fake.calls[0].task_context
    forbidden_keys = {
        "full_catalog",
        "catalog",
        "completed_courses",
        "degree_requirements",
        "wiki_context",
        "wiki_snippets",
        "transcript_rows",
        "raw_mongo_document",
    }
    assert not (set(task_context.keys()) & forbidden_keys)
    # Only a compact profile summary is allowed, never a raw Mongo document.
    assert task_context["user_profile_summary"] == {
        "degreeProgram": "Computer Science",
        "catalogYear": 2025,
    }
    # Recent messages are capped, never the full conversation history.
    assert isinstance(task_context["recent_messages"], list)
    assert len(task_context["recent_messages"]) <= 6


async def test_recent_messages_are_capped_to_last_six():
    fake = FakeReasoningBlock(_completed_output(_result()))
    settings = _settings_enabled()
    recent_messages = [{"role": "user", "content": f"message {i}"} for i in range(20)]

    await understand_user_task(
        user_message="What am I missing to graduate?",
        recent_messages=recent_messages,
        settings=settings,
        reasoning_block=fake,
    )

    sent = fake.calls[0].task_context["recent_messages"]
    assert len(sent) == 6
    assert sent[-1]["content"] == "message 19"


async def test_existing_entities_and_assumptions_reach_the_reasoning_context():
    """Conversation-continuity inputs must actually reach the LLM's task_context —
    this was a known gap (the live call site never forwarded them) fixed as part
    of the Layer 1 (request-understanding) redesign.
    """
    fake = FakeReasoningBlock(_completed_output(_result()))
    settings = _settings_enabled()

    await understand_user_task(
        user_message="What am I missing to graduate?",
        existing_entities={"courseNumber": "234218", "trackSlug": "track-computer-science"},
        existing_assumptions=["Student is in the 2025 catalog year."],
        settings=settings,
        reasoning_block=fake,
    )

    task_context = fake.calls[0].task_context
    assert task_context["existing_entities"] == {
        "courseNumber": "234218",
        "trackSlug": "track-computer-science",
    }
    assert task_context["existing_assumptions"] == ["Student is in the 2025 catalog year."]
