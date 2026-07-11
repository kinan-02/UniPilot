"""Live confirmation of `docs/agent/TOOL_PRIMITIVES_OPEN_GAPS.md` gaps #1 and
#4, which that doc leaves marked "likely mitigated but unconfirmed" by the
task handler (`orchestrator/task_handler.py`).

Both gaps trace back to the SAME two real `PlanStep`s that originally
surfaced them -- steps 1a/1b of the real Planner output recorded in
`live_eval_logs/full_turn-20260710T191712Z.json` for "What happens if I fail
Data Structures this semester?" (copied here verbatim, not paraphrased):

- Step 1a's objective mixes fetching raw records with a derived
  "academic standing (GPA, probation status)" fact the Retrieval role isn't
  supposed to compute (gap #1).
- Step 1b's objective mixes course-catalog retrieval with "which degree
  requirements it fulfills (mandatory, elective, etc.)" -- a fact that lives
  in wiki prose and needs `interpret_text`, which only the Interpretation
  role is granted (`app/agent_core/roles/roster.py`), not Retrieval (gap #4).

This file calls the REAL classifier (`classify_step`) and REAL nested
Planner (`build_next_plan_steps(prompt_contract_name=NESTED_PLANNER_V1)`)
directly on these two steps -- the same two calls `task_handler.py` itself
would make -- without going through full specialist dispatch (which would
need a seeded MongoDB/wiki matching this exact scenario; out of scope for
what's being checked here, which is the PLANNING-layer decomposition
decision, not tool-execution quality). This mirrors
`test_planning_planner_live_eval.py`'s own scope discipline: real model
calls, hand-built input, no live subagent execution.

`pytest.mark.live`, skipped without `OPENAI_API_KEY` -- same as every other
live-eval file.
"""

from __future__ import annotations

import pytest

from app.agent_core.orchestrator.task_handler_classifier import classify_step
from app.agent_core.planning.planner import NESTED_PLANNER_V1, build_next_plan_steps
from app.agent_core.planning.schemas import PlanGraph, PlanStep, PlannerInvocationInput
from app.agent_core.reasoning.llm_client import agent_llm_available
from tests.agent_core.live_eval_logging import LiveEvalLog, LoggingLLMAdapter
from tests.agent_core.test_turn_live_eval import _run_full_flow

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]

ORIGINAL_MESSAGE = "What happens if I fail Data Structures this semester?"

# Verbatim from live_eval_logs/full_turn-20260710T191712Z.json, case
# "hypothetical_question", plan.next_steps[0] -- the real step that surfaced
# gap #1.
STEP_1A = PlanStep(
    step_id="1a",
    objective=(
        "Retrieve the student's current academic record: completed courses, current enrollment "
        "(including the semester registration for Data Structures), declared program/degree, "
        "academic standing (GPA, probation status), and overall progress towards degree requirements."
    ),
    depends_on=[],
    success_criteria=[
        "The student's full transcript and degree audit information is obtained, showing completed "
        "courses, in-progress courses, GPA, and program requirements."
    ],
    assumptions_to_verify=[
        "The student's identity can be inferred from the session and maps to a valid record in the system.",
        "The student is currently enrolled in Data Structures this semester.",
    ],
)

# Verbatim from the same log/case, plan.next_steps[1] -- the real step that
# surfaced gap #4.
STEP_1B = PlanStep(
    step_id="1b",
    objective=(
        "Look up the course 'Data Structures' in the course catalog: identify its course code, "
        "credit hours, prerequisites, and, crucially, what other courses list it as a prerequisite "
        "(the courses that require it) and which degree requirements it fulfills (mandatory, "
        "elective, etc.)."
    ),
    depends_on=[],
    success_criteria=[
        "A clear mapping is obtained: the course code (e.g., 114234), its credit weight, the list of "
        "downstream courses that have it as a prerequisite, and its role in the curriculum (core/elective)."
    ],
    assumptions_to_verify=[
        "The student refers to the standard Data Structures course (e.g., CS 114234) and not a "
        "different course with a similar name."
    ],
)


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="task_handler_gap_confirmation")
    yield log
    log.write()


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


async def _classify_and_decompose(step: PlanStep, adapter: LoggingLLMAdapter, *, block_prefix: str):
    """Real classifier call, then (only if it comes back non-atomic, which
    is itself the first thing under test) the real nested-planner call --
    same two calls `task_handler.py::run_task_handler` would make for this
    step, minus specialist dispatch. Returns
    `(classifier_output, nested_plan_output, sub_step_roles)` where
    `sub_step_roles` maps each nested sub-step id to its own classifier
    verdict (role assignment only, mirroring `_dispatch_nested_sub_step`)."""
    classifier_output = await classify_step(
        step=step, dependency_context=[], llm_adapter=adapter, block_id=f"{block_prefix}-classifier"
    )
    if classifier_output.atomic:
        return classifier_output, None, {}

    planner_input = PlannerInvocationInput(
        user_goal=step.objective,
        original_user_message=ORIGINAL_MESSAGE,
        sub_asks=[],
        constraints=[],
        open_questions=list(step.assumptions_to_verify),
        implies_action_request=False,
        state_index=[],
        plan_graph_so_far=PlanGraph(),
        monitor_flags=[],
        replan_reason=None,
    )
    nested_plan = await build_next_plan_steps(
        planner_input=planner_input,
        llm_adapter=adapter,
        block_id=f"{block_prefix}-nested-planner",
        invocation=1,
        prompt_contract_name=NESTED_PLANNER_V1,
    )

    sub_step_roles: dict[str, str | None] = {}
    for sub_step in nested_plan.next_steps:
        sub_classification = await classify_step(
            step=sub_step,
            dependency_context=[],
            llm_adapter=adapter,
            block_id=f"{block_prefix}-{sub_step.step_id}-classifier",
        )
        sub_step_roles[sub_step.step_id] = (
            sub_classification.role_if_atomic if sub_classification.atomic else None
        )

    return classifier_output, nested_plan, sub_step_roles


async def test_gap_1_gpa_probation_step_is_not_treated_as_pure_retrieval(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """Gap #1: a Retrieval subagent must never be left to silently compute
    GPA/probation status itself. The task handler's fix is dispatch-time
    decomposition, so the property that actually matters is: does step 1a,
    as originally planned, ever get handed to Retrieval ALONE with no
    separate calculation step? That happens in exactly two ways this test
    treats as a pass: (a) the classifier itself recognizes the compound
    objective as non-atomic, or (b) it's classified atomic but NOT as
    "retrieval" (e.g. routed to a role that can actually compute a derived
    status) -- either way, Retrieval is never left alone with a GPA/
    probation-status success criterion it has no tool to satisfy honestly."""
    classifier_output, nested_plan, sub_step_roles = await _classify_and_decompose(
        STEP_1A, adapter, block_prefix="gap1"
    )
    live_eval_log.record_case(
        "gap_1_gpa_probation",
        adapter,
        classifier_output=classifier_output,
        nested_plan=nested_plan,
        sub_step_roles=sub_step_roles,
    )

    if classifier_output.atomic:
        assert classifier_output.role_if_atomic != "retrieval", (
            "Step 1a's objective mixes raw record retrieval with a derived GPA/probation-status "
            "fact -- Retrieval alone cannot honestly satisfy this success criterion "
            f"(classifier verdict: atomic=True, role={classifier_output.role_if_atomic!r})"
        )
        return

    assert nested_plan is not None and nested_plan.next_steps, (
        "step 1a was classified non-atomic but the nested planner produced no sub-steps at all"
    )
    roles_seen = set(sub_step_roles.values())
    assert "retrieval" in roles_seen or None in roles_seen, (
        f"expected at least a retrieval-shaped fetch sub-step among {sub_step_roles!r}"
    )
    assert roles_seen - {"retrieval"}, (
        "expected at least one sub-step routed to a role OTHER than retrieval (e.g. "
        f"calculation_validation) to own the GPA/probation-status computation -- got only "
        f"{sub_step_roles!r}"
    )


async def test_gap_4_mandatory_elective_step_gets_an_interpretation_capable_path(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """Gap #4: "which degree requirements it fulfills (mandatory, elective,
    etc.)" lives in wiki prose, not a graph edge -- it needs `interpret_text`,
    which only the Interpretation role is granted
    (`app/agent_core/roles/roster.py::build_default_role_roster`). The
    property under test: step 1b, as originally planned, must never be
    handed to Retrieval alone (which has no `interpret_text` grant and would
    have no honest way to satisfy this criterion). Passes if either (a) the
    classifier itself routes the whole step somewhere other than bare
    Retrieval, or (b) it decomposes and at least one sub-step is routed to
    Interpretation."""
    classifier_output, nested_plan, sub_step_roles = await _classify_and_decompose(
        STEP_1B, adapter, block_prefix="gap4"
    )
    live_eval_log.record_case(
        "gap_4_mandatory_elective",
        adapter,
        classifier_output=classifier_output,
        nested_plan=nested_plan,
        sub_step_roles=sub_step_roles,
    )

    if classifier_output.atomic:
        assert classifier_output.role_if_atomic != "retrieval", (
            "Step 1b's objective needs interpret_text (only granted to the Interpretation role) to "
            "resolve mandatory-vs-elective status from prose -- Retrieval alone cannot honestly "
            f"satisfy this success criterion (classifier verdict: role={classifier_output.role_if_atomic!r})"
        )
        return

    assert nested_plan is not None, "step 1b was classified non-atomic but no nested plan was produced"

    if nested_plan.plan_status == "blocked_needs_clarification":
        # Mandatory/elective status is relative to ONE specific degree program
        # (the same course can be mandatory in one program, elective in
        # another) -- this isolated sub-plan has no program in its
        # dependency_context, so honestly asking rather than guessing is the
        # CORRECT fail-closed outcome here, not a failure. See
        # test_gap_4_top_level_plan_wires_requirement_fulfillment_step_to_program_step
        # below for the other half of this fix: the top-level plan should
        # wire this step to depend on whichever step fetches the program, so
        # this clarification need never arises for a real end-to-end run.
        assert nested_plan.clarification_question, "blocked_needs_clarification with no real question to ask"
        return

    assert nested_plan.next_steps, (
        "step 1b was classified non-atomic, not blocked for clarification, but the nested planner "
        "produced no sub-steps at all"
    )
    roles_seen = set(sub_step_roles.values())
    assert "interpretation" in roles_seen, (
        "expected at least one nested sub-step routed to the interpretation role to classify "
        f"mandatory/elective status from prose -- got {sub_step_roles!r}"
    )


async def test_gap_4_top_level_plan_wires_requirement_fulfillment_step_to_program_step(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """The other half of gap #4's fix: the ORIGINAL recorded plan
    (live_eval_logs/full_turn-20260710T191712Z.json) gave step 1b
    (requirement-fulfillment question) `depends_on: []`, even though
    resolving mandatory/elective status genuinely needs the student's
    declared program -- only step 1a fetched that. That missing edge is
    exactly what forced the other test above into a legitimate but avoidable
    clarification block. This test exercises the REAL top-level Planner
    (PLANNER_V1, via a fresh RU + Planner call, not the hand-built steps
    above) on the same original message, and checks the newly-added planner
    instruction actually wires the edge: any step whose objective/
    success_criteria asks about mandatory/elective/degree-requirement status
    must declare a dependency on whichever step fetches the student's
    declared program."""
    understanding, plan = await _run_full_flow(ORIGINAL_MESSAGE, adapter, block_prefix="gap4-depwiring")
    live_eval_log.record_case("gap_4_dependency_wiring", adapter, understanding=understanding, plan=plan)

    def _mentions_requirement_fulfillment(step: PlanStep) -> bool:
        text = f"{step.objective} {' '.join(step.success_criteria)}".lower()
        return "mandatory" in text or "elective" in text or "degree requirement" in text

    def _mentions_program(step: PlanStep) -> bool:
        text = f"{step.objective} {' '.join(step.success_criteria)}".lower()
        return "program" in text or "degree audit" in text or "declared program" in text

    requirement_steps = [step for step in plan.next_steps if _mentions_requirement_fulfillment(step)]
    assert requirement_steps, (
        "expected at least one step asking about mandatory/elective/degree-requirement status in "
        f"this plan -- got objectives: {[step.objective for step in plan.next_steps]}"
    )
    program_steps = [step for step in plan.next_steps if _mentions_program(step)]
    assert program_steps, (
        "expected at least one step fetching the student's declared program in this plan -- got "
        f"objectives: {[step.objective for step in plan.next_steps]}"
    )
    program_step_ids = {step.step_id for step in program_steps}
    for step in requirement_steps:
        assert set(step.depends_on) & program_step_ids, (
            f"step {step.step_id!r} ({step.objective!r}) asks about requirement-fulfillment status "
            f"but does not depend on any program-fetching step {program_step_ids!r} -- "
            f"depends_on={step.depends_on!r}"
        )
