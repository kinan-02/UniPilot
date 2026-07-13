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
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry

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
    # 1a-c. Planner council: the drafted plan (above) is valid and non-empty,
    # so its three critics (coverage, grounding, criteria) each review it in
    # parallel. All find nothing, so the draft stands and no synthesizer call
    # is made -- see planner_council.py.
    {"issues": []},
    {"issues": []},
    {"issues": []},
    # 2. Task handler's merged classify_and_prep for step 1 -- atomic, retrieval role + prep details.
    {
        "atomic": True,
        "role_if_atomic": "retrieval",
        "goal": "Fetch course record",
        "description": "Fetch the record for course 234218.",
        "specific_instructions": ["Use get_entity to fetch the course."],
        "tone_language_notes": "",
        "context_requirements": [],
        "tool_grant_override": None,
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
    {
        "status": "ready",
        "result": {
            "certainty_basis": "wiki_derived",
            "confidence": 0.9,
            "assumptions": [],
            "facts": {"course_id": "234218", "name": "Some Course"},
        },
    },
    # 4a. Task handler's success-criteria check for step 1 -- met.
    {"criteria_met": True, "unmet_criteria": []},
    # 4b. Monitor's own OUTER success-criteria check for step 1 (against the
    # original top-level step's own success_criteria, separate from the task
    # handler's internal check above) -- met.
    {"criteria_met": True, "unmet_criteria": []},
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
    # 5a. Task handler's merged classify_and_prep for step 2 -- atomic, composition role + prep details.
    {
        "atomic": True,
        "role_if_atomic": "composition",
        "goal": "Compose final answer",
        "description": "Compose the final answer using step 1's result.",
        "specific_instructions": [],
        "tone_language_notes": "",
        "context_requirements": ["1a"],
        "tool_grant_override": None,
    },
    # 7. Step 2 subagent (composition) -- single-shot.
    {
        "answer_text": "Course 234218 is Some Course."
    },
    # 8a. Task handler's success-criteria check for step 2 -- met.
    {"criteria_met": True, "unmet_criteria": []},
    # 8b. Monitor's own OUTER success-criteria check for step 2 -- met.
    {"criteria_met": True, "unmet_criteria": []},
]


async def test_two_step_plan_holds_together_end_to_end(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(_RESPONSES)
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    state, final_entry, clarification_question = await run_plan_to_completion(
        user_goal="What course is 234218?",
        original_user_message="What course is 234218?",
        user_id="test-user-1",
        llm_adapter=adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id="test-plan-1",
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


async def test_step_2_context_slice_is_bounded_to_its_own_dependency(fake_llm_adapter_factory):
    """2. Step 2's dependency_state contains exactly step 1's entry and
    nothing else -- proves bounded slicing, not "some context.\""""
    from app.agent_core.orchestrator.context_builder import build_subagent_context_package
    from app.agent_core.planning.state import CertaintyTag, PlanExecutionState, StateEntry
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
