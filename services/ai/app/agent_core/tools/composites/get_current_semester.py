"""`get_current_semester` -- higher-level composite tool
(docs/agent/HIGHER_LEVEL_TOOLS.md). Bundles `get_current_date` with two
`interpret_text` reads of the academic calendar wiki page (one for the
current semester, one for the next) into one call.

A live-eval run found a real, recurring gap this closes: "the current/next
academic semester" is a common date-relative fact, but nothing could
actually compute it -- `apply_deterministic_rule` has no date-range-
containment rule type (its 4 rule types are sum/count/field-comparison/
expression, none of them date-aware), and the calendar's own date ranges
live only in wiki prose, not a structured field. A nested planner tried
this via a `calculation_validation` step twice, failed its success-check
both times, then gave up (`blocked_needs_clarification`) without ever
reaching a real answer.

Semester date ranges shift every academic year, so they are never
hardcoded here -- always read fresh via `interpret_text` from the same
wiki page a human advisor would check, so this tool can never drift from
what the calendar actually says.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.composites.get_current_date import GetCurrentDateInput, run_get_current_date
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.primitives.interpret_text import InterpretTextInput, run_interpret_text
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_current_semester"

# Verified against the real wiki (concepts/academic-calendar.md) --
# checked directly, not assumed, same discipline every other composite's
# hardcoded slug/entity_type reference follows.
_ACADEMIC_CALENDAR_SLUG = "academic-calendar"


class GetCurrentSemesterInput(BaseModel):
    pass


async def run_get_current_semester(_payload: GetCurrentSemesterInput) -> ToolOutputEnvelope:
    date_result = await run_get_current_date(GetCurrentDateInput())
    today = str(date_result.data["date"])

    # Two separate, narrowly-scoped interpret_text calls rather than one
    # question asking for both -- a live-eval run found callers routinely
    # scoping a step's success_criteria to expect "current AND next
    # semester as distinct values"; a single free-text answer covering
    # both doesn't reliably parse into two clean fields, so a genuinely
    # correct tool call still failed its success-check and triggered a
    # wasted re-plan, twice. Two clean fields costs one extra LLM call
    # here but is far cheaper than that failure loop.
    current_result = await run_interpret_text(
        InterpretTextInput(
            source=_ACADEMIC_CALENDAR_SLUG,
            question=(
                f"Today's date is {today}. Based on the semester date ranges in this "
                "calendar, which academic semester (e.g. 'Winter 2025/2026') is currently "
                "active today? If today falls between semesters (no semester is currently "
                "active), answer exactly 'none'. Answer with a single semester name and "
                "academic year, nothing else."
            ),
        )
    )
    next_result = await run_interpret_text(
        InterpretTextInput(
            source=_ACADEMIC_CALENDAR_SLUG,
            question=(
                f"Today's date is {today}. Based on the semester date ranges in this "
                "calendar, which academic semester (e.g. 'Winter 2025/2026') is the NEXT "
                "one to start after today (the very next semester whose start date is "
                "after today, even if a semester is currently active)? Answer with a "
                "single semester name and academic year, nothing else."
            ),
        )
    )

    if not current_result.ok and not next_result.ok:
        return ToolOutputEnvelope(
            ok=False,
            data=None,
            error=f"could_not_determine_semester: {current_result.error or next_result.error}",
        )

    certainty = next_result.certainty if next_result.ok else current_result.certainty
    return ToolOutputEnvelope(
        ok=True,
        data={
            "today": today,
            "currentSemester": current_result.data["answer"] if current_result.ok else None,
            "nextSemester": next_result.data["answer"] if next_result.ok else None,
        },
        certainty=certainty,
    )


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Determine BOTH the current academic semester (null if today falls between "
    "semesters) and the next one to start (e.g. 'Winter 2025/2026'), as two distinct fields "
    "(currentSemester, nextSemester), from today's actual date plus the academic calendar "
    "wiki page's own date ranges, in one call. Use this whenever a step needs 'the current "
    "semester' or 'next semester' as a concrete fact -- no other tool can compute this: "
    "apply_deterministic_rule has no date-range rule type, and the calendar's date ranges "
    "change every academic year so they are never hardcoded, always read fresh from the wiki.",
    input_model=GetCurrentSemesterInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_current_semester,
)
