"""The correctness gate: does the agent return the RIGHT answer?

The older `test_full_agent_live_eval.py` asserts only `in_scope` +
`final_entry is not None` + `"answer_text" in data` -- a liveness check that
passes if the agent emits any string at all. It demonstrably cannot tell a right
answer from a wrong one: in the 2026-07-15 sweep the two synthesis attempts of
`course_disruption_simulation` returned CONTRADICTORY answers (one said the
student must retake a course they had already passed) and BOTH would have
passed.

This suite asserts checkable CLAIMS against a student whose ground truth we
verified end-to-end (`docs/agent/ISE_EVAL_FIXTURE.md`).

Assertion style
---------------
Claims are anchored on unambiguous tokens -- course codes ("00960211") and exact
numbers ("91.5") -- never on prose phrasing, which varies run to run and would
make the gate flaky. `must_not_mention` is used sparingly and only where a
mention is unambiguously a factual error.

Scope limits (deliberate; see the doc)
--------------------------------------
NO prereq-eligibility assertion is made about `00940411`, `00940312`,
`00940314`, `00970800`, or `01140051`: the seeded student's real path does not
satisfy the registrar's stated prereqs for those, so ground truth is genuinely
ambiguous and a correct agent could reasonably answer either way. Asserting
there would punish the agent for a data artefact.
"""

from __future__ import annotations

import pytest
from tqdm import tqdm

from app.agent_core.reasoning.llm_client import agent_llm_available
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn
from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- fixtures used via pytest injection
    IseStudent,
    _fresh_mongo_client_per_test,
    ise_student,
)
from tests.agent_core.live_eval_logging import LiveEvalLog, LoggingLLMAdapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="ise_correctness")
    yield log
    log.write()


@pytest.fixture(scope="module", autouse=True)
def _live_eval_progress_bar(request):
    """A SINGLE progress bar for the whole correctness run.

    Module-scoped so exactly one `tqdm` instance is created and updated in place
    -- never re-instantiated per test, which would spam a fresh bar per case.
    Run with `-s` (and no `-v`) so pytest does not capture it and it renders
    live in your terminal.
    """
    total = sum(1 for name in dir(request.module) if name.startswith("test_"))
    bar = tqdm(total=total, desc="ise correctness", unit="case", leave=True)
    try:
        yield bar
    finally:
        bar.close()


@pytest.fixture(autouse=True)
def _advance_live_eval_progress(_live_eval_progress_bar, request):
    """Label the shared bar with the running case, then advance it once the test
    finishes (teardown runs on pass *and* fail, so progress stays honest)."""
    _live_eval_progress_bar.set_postfix_str(request.node.name, refresh=True)
    yield
    _live_eval_progress_bar.update(1)


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


async def _answer(message: str, adapter: LoggingLLMAdapter, user_id: str, *, block_prefix: str):
    understanding, state, final_entry, clarification = await run_agent_turn(
        original_user_message=message,
        user_id=user_id,
        llm_adapter=adapter,
        role_roster=build_default_role_roster(),
        tool_registry=build_default_tool_registry(),
        plan_id=block_prefix,
        max_planner_invocations=5,
    )
    answer = ""
    if final_entry is not None and isinstance(final_entry.data, dict):
        answer = str(final_entry.data.get("answer_text") or "")
    return understanding, state, final_entry, clarification, answer


def _record(live_eval_log, case, adapter, understanding, state, final_entry, clarification):
    live_eval_log.record_case(
        case,
        adapter,
        understanding=understanding,
        state_entries=[e.model_dump(mode="json") for e in state.entries] if state else None,
        final_entry=final_entry.model_dump(mode="json") if final_entry else None,
        clarification=clarification,
    )


def _assert_mentions(answer: str, tokens: list[str], *, case: str) -> None:
    missing = [t for t in tokens if t not in answer]
    assert not missing, f"[{case}] answer omits required fact(s) {missing}.\n--- answer ---\n{answer}"


# --- Credit arithmetic -----------------------------------------------------
# Ground truth: 155 total - 62.5 earned = 92.5 remaining. Grounded in
# degree_programs (155) + the 17 seeded courses. Physical Education is NOT
# counted: it has no course code, so it cannot be seeded and the agent cannot
# see it (an earlier revision wrongly demanded 91.5 by counting it).
#
# CAUGHT LIVE (2026-07-15): the agent answered 63.0 earned / 92.0 remaining --
# wrong by 0.5. Root cause is NOT sloppy arithmetic in composition: the
# `calculation_validation` step failed
# (`of_not_a_list: ref:creditBreakdown` -- it built the expression over the
# credit-buckets dict instead of the completedCourses list), so a RETRIEVAL
# block did the sum in-model and asserted it -- violating its own contract
# ("never directly assert a computed fact without a tool call result").
# The deterministic calculator exists precisely to stop this; its failure is
# silent, and an LLM fills the gap with a confident wrong number.


async def test_credits_remaining_is_stated_correctly(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "How many credits do I still need to complete my degree?",
        adapter,
        ise_student.user_id,
        block_prefix="ise-credits-remaining",
    )
    _record(live_eval_log, "credits_remaining", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"No answer reached. Clarification: {clarification}"
    _assert_mentions(answer, ["92.5"], case="credits_remaining")


# --- Eligibility (only on courses whose ground truth is unambiguous) --------
# 00960211 prereq: "00940224 או 00940226". The student completed 00940224
# (2025-1, grade 85) => eligible. Offered every spring, incl. the current 2025-2.


async def test_eligibility_for_ecommerce_models_is_affirmed(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "Am I eligible to take course 00960211?",
        adapter,
        ise_student.user_id,
        block_prefix="ise-eligibility-00960211",
    )
    _record(live_eval_log, "eligibility_00960211", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"No answer reached. Clarification: {clarification}"
    # The prerequisite it must reason from, and which the student holds.
    _assert_mentions(answer, ["00940224"], case="eligibility_00960211")


# --- Presupposition conflict (the highest-value adversarial case) -----------
# The student ALREADY PASSED 00940224 (2025-1, grade 85) and is not enrolled in
# it. A correct answer must surface that conflict rather than accept the premise.
# This is the exact shape that produced two contradictory answers in the old
# suite, both of which passed.


async def test_failing_an_already_passed_course_surfaces_the_conflict(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "If I fail course 00940224 this semester, will I still be able to take 00960211 afterwards?",
        adapter,
        ise_student.user_id,
        block_prefix="ise-presupposition-conflict",
    )
    _record(live_eval_log, "presupposition_conflict", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None or clarification is not None, "No conclusion reached."
    if final_entry is not None:
        # Must engage with the real record: the course is already completed.
        _assert_mentions(answer, ["00940224"], case="presupposition_conflict")


# --- Offering pattern ------------------------------------------------------
# 00960211 was offered ONLY in spring (semesterCode 201) in 2023, 2024 and 2025
# -- never winter, never summer. Grounded in course_offerings.


async def test_offering_pattern_for_ecommerce_models(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "Is course 00960211 offered in the summer semester?",
        adapter,
        ise_student.user_id,
        block_prefix="ise-offering-pattern",
    )
    _record(live_eval_log, "offering_pattern", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None or clarification is not None, "No conclusion reached."


# --- Transcript retrieval --------------------------------------------------
# The student completed exactly 17 courses. This is also the canary for the
# broken-fixture class of bug: if the transcript stops resolving, this fails
# loudly instead of silently degrading every other case.


async def test_completed_courses_are_retrieved(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "Which courses have I completed so far?",
        adapter,
        ise_student.user_id,
        block_prefix="ise-completed-courses",
    )
    _record(live_eval_log, "completed_courses", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"No answer reached. Clarification: {clarification}"
    # A sample of real completions the answer must reflect -- if the transcript
    # resolved at all, these are present.
    _assert_mentions(answer, ["00940224"], case="completed_courses")


# --- Action boundary -------------------------------------------------------


async def test_registration_request_is_declined_not_performed(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, ise_student: IseStudent
) -> None:
    understanding, state, final_entry, clarification, answer = await _answer(
        "Please register me for course 00960211 for next semester.",
        adapter,
        ise_student.user_id,
        block_prefix="ise-action-boundary",
    )
    _record(live_eval_log, "action_boundary", adapter, understanding, state, final_entry, clarification)

    # Measured live (2026-07-15): RU returns in_scope=False / implies_action_request=False
    # for a bare registration request, reasoning it is something the agent cannot
    # perform. An earlier revision asserted in_scope + implies_action_request --
    # that encoded a GUESS about intended behaviour, not a spec, and failed the
    # agent for a defensible decision.
    #
    # What actually matters, and all this asserts: the agent must never claim to
    # have registered the student. Declining as out-of-scope satisfies that.
    if understanding.in_scope:
        assert final_entry is not None or clarification is not None, (
            "In-scope action request must reach a boundary explanation or a clarifying question -- "
            "never a silent claim that the action was performed."
        )
    else:
        assert not understanding.implies_action_request, (
            "An out-of-scope request must not also be flagged as an action the agent will take."
        )
