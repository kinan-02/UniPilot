"""Unit tests for the ReasoningBlock-backed preference extractor (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.llm_preference_extractor import extract_planning_preferences
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(result: dict[str, Any] | None, **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary="extracted",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.85,
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _settings_with_key(**overrides: Any) -> Settings:
    base = {"OPENAI_API_KEY": "sk-test", "AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


async def test_extracts_avoid_days_and_credit_limit_from_fake_result():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "maxCredits": 16,
                "avoidDays": ["Friday"],
                "planningObjective": None,
                "targetSemester": "next",
                "targetSemesterCode": None,
                "modificationType": None,
                "replaceCourseNumber": None,
                "addCourseNumber": None,
            }
        )
    )
    settings = _settings_with_key()

    merged = await extract_planning_preferences(
        "Plan next semester max 16 credits no Friday",
        settings=settings,
        reasoning_block=fake,
    )

    assert len(fake.calls) == 1
    assert merged["maxCredits"] == 16
    assert merged["avoidDays"] == ["Friday"]
    assert merged["targetSemester"] == "next"


async def test_never_overwrites_existing_regex_resolved_entities():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "maxCredits": 20,  # should be ignored; regex already found 14
                "avoidDays": ["Monday"],
                "planningObjective": None,
                "targetSemester": None,
                "targetSemesterCode": None,
                "modificationType": None,
                "replaceCourseNumber": None,
                "addCourseNumber": None,
            }
        )
    )
    settings = _settings_with_key()

    merged = await extract_planning_preferences(
        "avoid Monday too",
        existing_entities={"maxCredits": 14, "avoidDays": ["Friday"]},
        settings=settings,
        reasoning_block=fake,
    )

    assert merged["maxCredits"] == 14  # not overwritten
    assert merged["avoidDays"] == ["Friday", "Monday"]  # merged, not replaced


async def test_falls_back_to_existing_entities_when_reasoning_block_fails():
    fake = FakeReasoningBlock(
        ReasoningBlockOutput(
            status="failed",
            result=None,
            decision_summary="llm unavailable",
            confidence=0.0,
            schema_valid=False,
            iterations_used=0,
            repair_attempts_used=0,
            warnings=["llm_adapter_error: llm_unavailable"],
        )
    )
    settings = _settings_with_key()
    existing = {"maxCredits": 18}

    merged = await extract_planning_preferences(
        "surprise me", existing_entities=existing, settings=settings, reasoning_block=fake
    )

    assert merged == existing


async def test_does_not_invent_preferences_on_low_confidence_empty_result():
    """A low-confidence/empty structured result should not fabricate preferences."""
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "maxCredits": None,
                "avoidDays": [],
                "planningObjective": None,
                "targetSemester": None,
                "targetSemesterCode": None,
                "modificationType": None,
                "replaceCourseNumber": None,
                "addCourseNumber": None,
            },
            confidence=0.2,
        )
    )
    settings = _settings_with_key()

    merged = await extract_planning_preferences(
        "hmm not sure", settings=settings, reasoning_block=fake
    )

    assert merged == {}


async def test_does_not_call_reasoning_block_when_flag_disabled():
    fake = FakeReasoningBlock()
    settings = _settings_with_key(AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED=False)

    merged = await extract_planning_preferences(
        "Plan next semester max 16 credits", settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert merged == {}


async def test_missing_llm_configuration_falls_back_without_crashing():
    settings = _settings_with_key(**{"OPENAI_API_KEY": None})

    merged = await extract_planning_preferences(
        "Plan next semester max 16 credits", settings=settings
    )

    assert merged == {}
