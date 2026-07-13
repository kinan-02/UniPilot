"""`get_current_date` -- higher-level composite tool (docs/agent/HIGHER_LEVEL_TOOLS.md).

Pure, zero-argument, zero-LLM-cost: there was previously no tool that could
answer "what is today's date" at all -- a live-eval run found the Planner
repeatedly decomposing "determine the current/next academic semester" into a
"retrieve the current date" sub-step that had no tool to dispatch to, burning
a full doomed nested-planner retry budget (3 rounds, several calls each)
before giving up every time. This does not compute the academic semester
itself -- that mapping lives in the academic-calendar wiki page's own prose
(date ranges per semester), which the agent already correctly extracts via
`interpret_text`/`get_policy_answer` once it actually has today's date to
compare against.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_current_date"

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class GetCurrentDateInput(BaseModel):
    pass


async def run_get_current_date(_payload: GetCurrentDateInput) -> ToolOutputEnvelope:
    today = datetime.now(timezone.utc).date()
    return ToolOutputEnvelope(
        ok=True,
        data={
            "date": today.isoformat(),
            "year": today.year,
            "month": today.month,
            "day": today.day,
            "weekday": _WEEKDAY_NAMES[today.weekday()],
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Returns today's actual current date (ISO 'date', plus year/month/day/weekday). "
    "Takes no arguments. Use this whenever a step needs 'today', 'now', 'the current/next "
    "academic semester', or any other date-relative fact as its starting point -- then compare "
    "it against the academic calendar's own date ranges (via get_entity/get_policy_answer on the "
    "academic calendar wiki page) to determine the current or next semester. No other tool can "
    "determine the current date.",
    input_model=GetCurrentDateInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_current_date,
)
