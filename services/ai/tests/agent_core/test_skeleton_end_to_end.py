"""The skeleton's actual completion criterion (docs/agent/AGENT_VISION.md skeleton plan).

Drives a hand-built 2-step plan (retrieval -> composition) through every
seam -- Planner -> step-prep -> prompt_builder -> context_builder ->
subagent_builder -> subagent.run (incl. the new tool-loop wrapper) ->
PlanExecutionState -> Monitor -> a second Planner invocation -> the
composition step -- using a fake LLM adapter that returns canned JSON per
call (mirroring `services/agent`'s own `FakeLLMAdapter` pattern).

Deliberately asserts nothing about the composed answer's *content* -- no
role prompt or tool has real domain logic yet; a content assertion would
only test the fake LLM's canned string, not the architecture.
"""

from __future__ import annotations

from app.agent_core.orchestrator.loop import run_plan_to_completion
from app.agent_core.turn_context import TurnContext
from app.agent_core.certainty import CertaintyTag
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.envelope import ToolOutputEnvelope


class _StubbedCourseRegistry:
    """Real descriptors, one stubbed `get_entity` that actually returns a course.

    Until retrieval emitted SELECTORS, this test drove the real
    `build_default_tool_registry()` -- whose `get_entity` needs Mongo, which this
    test does not have, and so returned
    `ok=False, error="entity_not_found: course:234218", data=None` on every run.
    The test stayed green regardless, because the fake LLM's canned round-2
    response simply asserted `facts: {"course_id": "234218", "name": "Some
    Course"}` and nothing verified that any tool had produced them. The
    architecture's "actual completion criterion" was being met by a fabricated
    fact.

    Projection reads the value out of the recorded envelope, so a failed tool now
    surfaces as a failed step -- which is the point. Stubbing the callable keeps
    the descriptor, the input model, the grant check and the audit trail real,
    and makes the DATA exist.
    """

    def __init__(self, inner):
        self._inner = inner

    def get(self, name: str):
        descriptor = self._inner.get(name)
        if name != "get_entity":
            return descriptor

        async def _stub(_payload):
            return ToolOutputEnvelope(
                ok=True,
                data={"course_id": "234218", "name": "Some Course"},
                certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            )

        return descriptor.model_copy(update={"callable": _stub})

    def has(self, name: str) -> bool:
        return self._inner.has(name)

_RESPONSES = [
    # 1. Planner invocation 1 -- one step: retrieval. Flat, matching
    # PLANNER_OUTPUT_SCHEMA directly -- PlannerReasoningBlock (BaseReasoningBlock)
    # calls the adapter directly with no "pass payload" envelope to unwrap,
    # unlike the old ReasoningBlock-based step-prep/subagent calls below.
    {
        "plan_status": "in_progress",
        "next_steps": [
            {
                "step_id": "A",
                "objective": "Fetch the record for course 234218.",
                "depends_on": [],
                "success_criteria": ["course record fetched"],
                "assumptions_to_verify": [],
            }
        ],
        "plan_summary": "Step 1: fetch course record.",
        "clarification_question": None,
    },
    # 1a-b. Planner council: the drafted plan is valid, so the validator runs
    # and the selector picks the critics its signals point at -- here the goal
    # carries a course code (grounding) and the invocation's default confidence
    # is below the strategy threshold (strategy), so TWO critics review it in
    # parallel, not all six. Both find nothing, so the draft stands and no
    # synthesizer call is made -- see planner_council.py / critic_selector.py.
    {"issues": []},
    {"issues": []},
    # 2. Task handler's Specialist Router for step 1 -- a length-1 pipeline
    # (one retrieval specialist), i.e. an atomic step.
    {
        "pipeline": [
            {
                "sub_step_id": "s1",
                "specialist": "retrieval",
                "objective": "Fetch the record for course 234218.",
                "depends_on": [],
                "success_criteria": ["course record fetched"],
                "specific_instructions": ["Use get_entity to fetch the course."],
            }
        ]
    },
    # 3. Step 1 subagent (retrieval), round 1 -- RetrievalReasoningBlock's own
    # per-round schema (status: "ready" | "need_tools"), requests a tool.
    {
        "status": "need_tools",
        "tool_requests": [
            {"tool_name": "get_entity", "purpose": "fetch course 234218", "arguments": {"entity_type": "course", "entity_id": "234218"}}
        ],
    },
    # 4. Step 1 subagent, round 2 -- finalizes with the tool result in hand.
    # One combined decide-and-finalize call, unlike the old generic path's
    # separate "not final" + "final" passes.
    #
    # SELECTORS, not values: the model names where each fact lives in call_1's
    # recorded envelope and `fact_projection` reads it out. `certainty_basis`
    # and `confidence` are absent on purpose -- they come from the tool's own
    # CertaintyTag now, not from anything the model asserts.
    {
        "status": "ready",
        "result": {
            "assumptions": [],
            "facts": [
                {"key": "course_id", "from": "call_1", "path": "data.course_id"},
                {"key": "name", "from": "call_1", "path": "data.name"},
            ],
        },
    },
    # NB: the task handler's success-criteria check is DETERMINISTIC now (no
    # LLM call) -- step 1's non-empty result passes it, so nothing is queued
    # for it. Also no monitor OUTER success-criteria check here. Step 1 is ATOMIC
    # (nested_trace is None), and the task handler already verified it against
    # this step's own success_criteria above -- so the monitor skips the
    # identical re-check (see orchestrator/monitor.py).
    # 5. Planner invocation 2 -- one step: composition, plan complete. Flat,
    # same reason as invocation 1's response above.
    {
        "plan_status": "complete",
        "next_steps": [
            {
                "step_id": "A",
                "objective": "Compose the final answer to the user.",
                "depends_on": ["1a"],
                "success_criteria": ["answer composed"],
                "assumptions_to_verify": [],
            }
        ],
        "plan_summary": "Step 2: compose the final answer.",
        "clarification_question": None,
    },
    # NB: no critic responses here. Invocation 2 is a routine continuation
    # (invocation > 1, the prior step succeeded so no replan flags), which the
    # council's adaptive-depth gate runs as drafter-only -- critics/synth are
    # skipped, so only the one planner draft call above is made.
    # 5a. Task handler's Specialist Router for step 2 -- a length-1 pipeline
    # (one composition specialist), i.e. an atomic step.
    {
        "pipeline": [
            {
                "sub_step_id": "s1",
                "specialist": "composition",
                "objective": "Compose the final answer using step 1's result.",
                "depends_on": ["1a"],
                "success_criteria": ["answer composed"],
                "context_requirements": ["1a"],
            }
        ]
    },
    # 7. Step 2 subagent (composition) -- single-shot.
    {
        "answer_text": "Course 234218 is Some Course."
    },
    # NB: the deterministic success-criteria check passes on step 2's non-empty
    # result with no LLM call, so nothing is queued for it -- and no monitor
    # OUTER check either, step 2 being atomic (see orchestrator/monitor.py).
]


async def test_two_step_plan_holds_together_end_to_end(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(_RESPONSES)
    role_roster = build_default_role_roster()
    tool_registry = _StubbedCourseRegistry(build_default_tool_registry())

    state, final_entry, clarification_question = await run_plan_to_completion(
        ctx=TurnContext(
            plan_id="test-plan-1",
            user_id="test-user-1",
            original_user_message="What course is 234218?",
            llm=adapter,
            tools=tool_registry,
            roles=role_roster,
        ),
        user_goal="What course is 234218?",
    )

    # 1. Exactly 2 entries, correct step_id/role/certainty.basis.
    assert len(state.entries) == 2
    assert [e.step_id for e in state.entries] == ["1a", "2a"]
    assert [e.role for e in state.entries] == ["retrieval", "composition"]
    assert state.entries[0].certainty.basis == "wiki_derived"
    assert state.entries[1].certainty.basis == "llm_interpretation"

    # 3. Step 1's tool_audit_trail shows get_entity was actually invoked with
    #    the fake LLM's requested arguments -- proves the tool loop round-trips.
    step1_trail = state.entries[0].tool_audit_trail
    assert len(step1_trail) == 1
    assert step1_trail[0].tool_name == "get_entity"
    assert step1_trail[0].arguments == {"entity_type": "course", "entity_id": "234218"}

    # 5. The final entry is the composition step, and it's what got returned.
    assert final_entry is not None
    assert final_entry.step_id == "2a"
    assert final_entry.role == "composition"
    assert final_entry.data["answer_text"] == "Course 234218 is Some Course."

    # Every queued response was consumed in order, nothing left over.
    assert adapter._responses == []


async def test_an_empty_composition_step_is_not_returned_as_the_answer(fake_llm_adapter_factory):
    """A composition entry that says nothing is not an answer.

    CAUGHT LIVE (2026-07-16, ise_correctness `offering_pattern`): the composition
    step came back `partial` with `data={}` from task_handler's
    empty-dependency-context guard, the loop returned it because it was the last
    entry and its role was composition, and the student got a blank reply. The
    turn falls through to synthesis instead, which composes over the WHOLE state
    -- in that run a sibling step had the data the answer needed.
    """
    responses = [
        *_RESPONSES[:-1],
        {"answer_text": ""},  # the composition step says nothing
        {"answer_text": "Recovered by composing over the whole state."},  # synthesis fallback
    ]
    adapter = fake_llm_adapter_factory(responses)

    _state, final_entry, _clarification = await run_plan_to_completion(
        ctx=TurnContext(
            plan_id="test-plan-empty-composition",
            user_id="test-user-1",
            original_user_message="What course is 234218?",
            llm=adapter,
            tools=_StubbedCourseRegistry(build_default_tool_registry()),
            roles=build_default_role_roster(),
        ),
        user_goal="What course is 234218?",
    )

    assert final_entry is not None
    assert final_entry.data["answer_text"] == "Recovered by composing over the whole state."


def test_the_no_answer_message_is_real_prose_in_the_students_language():
    """The last-resort text, when even synthesis composes nothing.

    Tested directly on the helpers rather than through the loop: reaching that
    branch end-to-end means driving an empty `answer_text` through the
    composition block's schema-repair loop, and a test that has to predict that
    loop's call count asserts on the repair budget, not on this behaviour. The
    branch above (`_answer_text` gating the early return) is what the
    integration test covers.
    """
    from app.agent_core.orchestrator.loop import _answer_text_from, _no_answer_message

    # The gate itself: these are all "no answer".
    assert _answer_text_from({}) == ""
    assert _answer_text_from({"answer_text": ""}) == ""
    assert _answer_text_from({"answer_text": "   "}) == ""
    assert _answer_text_from(None) == ""
    assert _answer_text_from({"answer_text": "real"}) == "real"

    english = _no_answer_message("What course is 234218?")
    assert "could not determine" in english
    # Actionable, not just apologetic -- the student needs somewhere to go next.
    assert "academic advisor" in english

    hebrew = _no_answer_message("איזה קורס הוא 234218?")
    assert hebrew != english, "a Hebrew student must not be answered in English"
    assert "לא הצלחתי" in hebrew


async def test_step_2_context_slice_is_bounded_to_its_own_dependency(fake_llm_adapter_factory):
    """2. Step 2's dependency_state contains exactly step 1's entry and
    nothing else -- proves bounded slicing, not "some context.\""""
    from app.agent_core.orchestrator.context_builder import build_subagent_context_package
    from app.agent_core.certainty import CertaintyTag
    from app.agent_core.planning.state import PlanExecutionState, StateEntry
    from app.agent_core.subagents.schemas import StepInstructionFields, StepPrepOutput
    from datetime import datetime, timezone

    state = PlanExecutionState(plan_id="p1")
    state.append(
        StateEntry(
            entry_id="s1-0",
            step_id="s1",
            role="retrieval",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={"foo": "bar"},
            certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            produced_at=datetime.now(timezone.utc),
        )
    )
    state.append(
        StateEntry(
            entry_id="unrelated-0",
            step_id="unrelated_step",
            role="interpretation",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={},
            certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            produced_at=datetime.now(timezone.utc),
        )
    )

    role_roster = build_default_role_roster()
    step_prep = StepPrepOutput(
        instruction_fields=StepInstructionFields(goal="compose", description="compose"),
        context_requirements=["s1"],
        output_schema_name="composition_agent_output_v1",
        output_schema={"type": "object"},
    )
    package = build_subagent_context_package(step_prep=step_prep, role=role_roster["composition"], state=state)

    assert [e.step_id for e in package.dependency_state] == ["s1"]

    # 4. Composition's resolved tool_grant is structurally empty.
    assert package.tool_grant == []
