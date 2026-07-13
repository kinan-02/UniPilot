"""Unit tests for `get_current_date` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Pure, zero-argument, zero-external-dependency -- previously there was no
tool that could answer "what is today's date" at all, which a live-eval run
found causing a doomed nested-planner sub-plan (retrieve current date -> no
tool exists -> exhaust retry budget) every time a request needed the
current/next academic semester.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.tools.composites.get_current_date import GetCurrentDateInput, run_get_current_date


async def test_returns_todays_actual_date():
    result = await run_get_current_date(GetCurrentDateInput())

    assert result.ok is True
    today = datetime.now(timezone.utc).date()
    assert result.data["date"] == today.isoformat()
    assert result.data["year"] == today.year
    assert result.data["month"] == today.month
    assert result.data["day"] == today.day
    assert result.data["weekday"] == today.strftime("%A")


async def test_returns_high_confidence_official_record_certainty():
    result = await run_get_current_date(GetCurrentDateInput())

    assert result.certainty is not None
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_takes_no_arguments():
    # Regression guard: the input model must stay a valid zero-field
    # schema (a tool with a non-empty required-field schema here would
    # force the LLM to invent arguments it doesn't have).
    schema = GetCurrentDateInput.model_json_schema()
    assert schema.get("required", []) == []
