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
from app.agent_core.response_language import ENGLISH, detect_message_language
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


def _assert_does_not_mention(answer: str, tokens: list[str], *, case: str, why: str) -> None:
    """Fail if the answer states something unambiguously false.

    Only for tokens that cannot appear in a correct answer -- see the
    `must_not_mention` note in the module docstring.
    """
    present = [t for t in tokens if t in answer]
    assert not present, f"[{case}] answer states {present}, which is wrong: {why}\n--- answer ---\n{answer}"


def _assert_answered_in_english(answer: str, *, case: str) -> None:
    """Every question in this suite is asked in ENGLISH, so every answer must be.

    CAUGHT LIVE (2026-07-16): three of six cases answered a plain English
    question entirely in Hebrew, and the suite passed all three -- every
    assertion here anchors on course codes, which are language-neutral, so the
    gate was structurally blind to it.

    Deliberately the SAME detector the agent uses to choose the language
    (`response_language.detect_message_language`), not a second implementation:
    a gate that measures language differently from the code under test would
    disagree with it at the edges and blame the agent for the discrepancy.

    Tolerant by construction -- it counts word majority, so a correct English
    answer quoting a Hebrew course name ("00960211 -- מודלים למסחר אלקטרוני")
    passes. Verified against all ten real answers from the 2026-07-16 runs: it
    flags exactly the three that flipped to Hebrew and passes the rest.
    """
    assert detect_message_language(answer) == ENGLISH, (
        f"[{case}] the question was English; the answer is predominantly Hebrew."
        f"\n--- answer ---\n{answer}"
    )


def _student_record_fetches(state) -> list:
    """Every `get_entity(entity_type='completed_courses')` the turn actually made."""
    if state is None:
        return []
    return [
        record
        for entry in state.entries
        for record in (entry.tool_audit_trail or [])
        if record.tool_name == "get_entity"
        and (record.arguments or {}).get("entity_type") == "completed_courses"
    ]


def _assert_consulted_the_student_record(state, *, case: str) -> None:
    """Assert on what the turn DID, not on how the answer reads.

    CAUGHT LIVE (2026-07-16), and the reason this helper exists at all:
    `presupposition_conflict` asked "if I fail 00940224...", and Request
    Understanding reduced it to one sub-ask -- "determine if 00960211 has
    00940224 as a prerequisite" -- dropping the student entirely. The turn never
    fetched the transcript, never noticed the course was already passed with an
    85, and answered a catalog question nobody asked. It PASSED, because the only
    assertion was that "00940224" appears in the answer, which it does in any
    answer about that course.

    A prose assertion cannot fix that. "You already passed it" and "yes, it is a
    prerequisite" share their every anchorable token, and the run answered in
    Hebrew besides. But the trace is unambiguous and language-neutral: an agent
    that never read the student's record cannot have checked a claim about the
    student's record, whatever its prose implies. So gate the execution, not the
    wording -- the same instinct as `subagents/fact_projection.py` reading a
    value out of the recorded tool envelope rather than asking a model.

    NECESSARY, NOT SUFFICIENT -- and the 2026-07-16 run proved the difference.
    This gate passed on the turn that told the student to retake a course they
    had passed with an 85: step 1b DID fetch the transcript, so the audit trail
    is satisfied. The record was then dropped before it reached the answer (the
    Planner left 1b out of composition's dependencies, so no "85.0" and no
    "2025-1" appear anywhere in composition's 10,281-char prompt).

    Reading the record is a precondition for engaging with it, not evidence of
    it. Callers must pair this with an assertion about what actually reached the
    student. Ancestry -- "the step that fetched it fed the answer" -- would be
    the honest structural check, but `StateEntry` records no `depends_on`, so it
    is not computable from `state` alone today.
    """
    assert _student_record_fetches(state), (
        f"[{case}] the turn never fetched the student's completed courses, so it cannot have "
        "engaged with their real record. A question whose premise is about the student's own "
        "status must be checked against that status, not answered from the catalog alone."
    )


def _assert_answered(answer: str, *, case: str) -> None:
    """Fail on an empty answer.

    CAUGHT LIVE (2026-07-16): `offering_pattern` returned a `final_entry` with
    `status=partial`, `composition_empty_dependency_context`, and an answer of
    ZERO characters -- and passed, because the case only checked that a
    `final_entry` existed. That is exactly the liveness check this suite's
    docstring faults `test_full_agent_live_eval.py` for ("passes if the agent
    emits any string at all"), only weaker: it passed on no string at all.
    A student staring at an empty reply is a total failure of the turn, so no
    case may assert its way around one.
    """
    assert answer.strip(), (
        f"[{case}] the agent produced an EMPTY answer -- the turn reached a final entry but said nothing."
    )


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
    _assert_answered_in_english(answer, case="credits_remaining")
    _assert_mentions(answer, ["92.5"], case="credits_remaining")
    # 62.5 earned is verified against the live catalog (the 17 seeded courses sum
    # to it, and degree_programs.totalCredits is 155.0). 63.5/63.0 are the values
    # the in-model sum has drifted to; 91.5/92.0 are what they imply for the
    # remainder. Any of them means the fabricated total won again.
    _assert_does_not_mention(
        answer,
        ["63.5", "63.0", "91.5", "92.0"],
        case="credits_remaining",
        why="the student has earned 62.5 of 155.0 credits, leaving 92.5",
    )


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
    _assert_answered_in_english(answer, case="eligibility_00960211")
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
    # The premise ("if I fail 00940224 this semester") is false: it was passed in
    # 2025-1 with an 85. Surfacing that REQUIRES having looked -- so this is
    # asserted on the trace, before anything about the prose. Measured live on
    # 2026-07-16: the turn never looked, and the token assertion below passed
    # anyway on an answer that never mentioned the student at all.
    _assert_consulted_the_student_record(state, case="presupposition_conflict")
    if final_entry is not None:
        _assert_answered(answer, case="presupposition_conflict")
        _assert_answered_in_english(answer, case="presupposition_conflict")
        # Must engage with the real record: the course is already completed.
        _assert_mentions(answer, ["00940224"], case="presupposition_conflict")
        # ...and must SAY SO. The two assertions above both passed on the
        # 2026-07-16 run that told this student to retake a course they had
        # passed with an 85: the trace gate is satisfied by step 1b fetching the
        # record, and "00940224" appears in any answer about that course.
        #
        # Fetching is necessary, not sufficient. That run fetched the pass and
        # then dropped it -- the Planner left step 1b out of composition's
        # dependencies, so the grade never entered the answer's context at all
        # (no "85.0", no "2025-1" anywhere in its 10,281-char prompt). The gate
        # has to test what reached the student, not what the turn touched.
        #
        # The grade is the one anchor that survives translation: "you already
        # passed it" and "you are not enrolled" share every prose token worth
        # matching, but only a turn that actually read the transcript can say
        # 85. Asserted here because the injected presupposition sub-ask now
        # demands the status "with the grade and semester" -- so an answer
        # without it did not do what it was asked.
        _assert_mentions(answer, ["85"], case="presupposition_conflict")


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
    if final_entry is not None:
        _assert_answered(answer, case="offering_pattern")
        _assert_answered_in_english(answer, case="offering_pattern")
        # The course asked about, and the only token safe to demand: this suite
        # anchors on codes and exact numbers, never prose. "Not offered in
        # summer" and "offered in summer" share every keyword worth grepping
        # ("summer", "00960211"), so a token assertion CANNOT tell the right
        # answer from its opposite here. Rather than fake rigor with a
        # phrase match that would be flaky in both directions, this case gates
        # what it can actually check -- a real, non-empty, on-topic answer --
        # and the offering ground truth (spring-only, 2023-2025) stays
        # documented above for a human reading the log.
        _assert_mentions(answer, ["00960211"], case="offering_pattern")


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
    _assert_answered(answer, case="completed_courses")
    _assert_answered_in_english(answer, case="completed_courses")
    # It cannot list the transcript without having fetched the transcript.
    _assert_consulted_the_student_record(state, case="completed_courses")
    # A sample of real completions the answer must reflect -- if the transcript
    # resolved at all, these are present.
    _assert_mentions(answer, ["00940224"], case="completed_courses")
    # CAUGHT LIVE (2026-07-16): this case answered "17 courses, totaling 63.5
    # credits earned" while `credits_remaining` -- same student, same run --
    # answered 62.5. Two cases contradicting each other on the SAME fact is the
    # exact failure this suite exists to catch, and it passed, because the case
    # asserted only a course code and never looked at the total.
    #
    # No total is REQUIRED here: "which courses have I completed" is honestly
    # answerable as a bare list, and demanding a sum would fail a correct answer
    # for not volunteering one (the trap this file's docstring warns about). But
    # a total that IS stated must be the real one. The listed values are what the
    # in-model sum has actually drifted to across live runs (63.0 on 2026-07-15,
    # 63.5 on 2026-07-16) -- deliberately a canary for that known drift, not an
    # exhaustive enumeration of every wrong number.
    _assert_does_not_mention(
        answer,
        ["63.5", "63.0"],
        case="completed_courses",
        why="the 17 completed courses total 62.5 credits earned -- and `credits_remaining` says 62.5",
    )


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
        # Same hole as `offering_pattern` had: a boundary explanation that
        # explains nothing is not a boundary explanation.
        if final_entry is not None:
            _assert_answered(answer, case="action_boundary")
            _assert_answered_in_english(answer, case="action_boundary")
    else:
        assert not understanding.implies_action_request, (
            "An out-of-scope request must not also be flagged as an action the agent will take."
        )
