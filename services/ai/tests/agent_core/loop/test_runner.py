"""End-to-end tests for the agent loop, scripted with a FAKE adapter (no live
LLM) over a stub tool registry. Proves the loop wiring: decompose -> fetch ->
surface -> compute -> final_answer -> grounding backstop -> completeness gate,
plus the governors (completeness rejection continuation, no-progress cap).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

import app.agent_core.loop.runner as runner
from app.agent_core.loop.runner import run_agent_loop
from app.agent_core.loop.working_set import Fact, WorkingSet
from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry

_COMPLETED = [
    {"courseNumber": "00940224", "creditsEarned": 3.5, "grade": 85},
    {"courseNumber": "00960211", "creditsEarned": 4.0, "grade": 90},
    {"courseNumber": "00110001", "creditsEarned": 2.0, "grade": 70},
]


# -- stub registry ------------------------------------------------------------
class _StubEntityInput(BaseModel):
    entity_type: str = ""
    entity_id: str = ""


async def _stub_get_entity(payload: _StubEntityInput) -> ToolOutputEnvelope:
    return ToolOutputEnvelope(
        ok=True,
        data={"completedCourses": _COMPLETED},
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


def _stub_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDescriptor(
            name="get_entity",
            description="stub fetch",
            input_model=_StubEntityInput,
            output_model=ToolOutputEnvelope,
            side_effect="read",
            callable=_stub_get_entity,
        )
    )
    return registry


# -- fake adapter -------------------------------------------------------------
class _FakeAdapter:
    """Dispatches on the system prompt: decompose / completeness / loop-turn.
    Loop-turn responses are consumed from a queue in order."""

    def __init__(
        self,
        turns: list[dict[str, Any]],
        *,
        sub_asks: list[str],
        completeness: list[dict[str, Any]] | None = None,
        compose: dict[str, Any] | None = None,
        front_door: dict[str, Any] | None = None,
    ) -> None:
        self._turns = list(turns)
        self._sub_asks = sub_asks
        self._completeness = list(completeness or [])
        self._compose = compose
        self._front_door = front_door
        self.gate_calls = 0
        self.compose_calls = 0

    async def complete_json(self, *, system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
        if "triage and decompose" in system_prompt:
            resp: dict[str, Any] = self._front_door if self._front_door is not None else {"sub_asks": self._sub_asks}
        elif "verify whether a DRAFT answer" in system_prompt:
            self.gate_calls += 1
            resp = self._completeness.pop(0) if self._completeness else {"unaddressed": []}
        elif "OUT of tool budget" in system_prompt:
            self.compose_calls += 1
            resp = self._compose or {"prose": "", "fact_refs": {}}
        else:
            resp = self._turns.pop(0)
        raw = kwargs.get("raw_model_text_out")
        if raw is not None:
            raw.append(json.dumps(resp))
        return resp


def _install(monkeypatch, adapter: _FakeAdapter) -> None:
    monkeypatch.setattr(runner, "ChatLLMAdapter", lambda: adapter)


_FETCH = {"tool": "get_entity", "arguments": {"entity_type": "completed_courses", "entity_id": "u1"}}
_SURFACE = {"tool": "surface_fact", "arguments": {"key": "completed", "from": "call_1", "path": "data.completedCourses"}}
_COMPUTE = {"tool": "compute", "arguments": {"key": "earned", "expression": {"op": "sum", "of": {"ref": "completed"}, "field": "creditsEarned"}}}
_ANSWER = {"tool": "final_answer", "arguments": {"prose": "You have earned {earned} credits.", "fact_refs": {"earned": "earned"}}}


async def test_happy_path_fetch_surface_compute_answer(monkeypatch):
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "answer", "tool_calls": [_ANSWER]}],
        sub_asks=["How many credits has the student earned so far?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned so far?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert result.ungrounded_numbers == []
    assert result.facts["earned"].value == 9.5
    assert result.facts["earned"].basis == "computed"


async def test_grounding_backstop_rejects_bare_number_then_recovers(monkeypatch):
    bad_answer = {"tool": "final_answer", "arguments": {"prose": "You have earned 999 credits.", "fact_refs": {}}}
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "bad answer", "tool_calls": [bad_answer]},
               {"thought": "good answer", "tool_calls": [_ANSWER]}],
        sub_asks=["earned?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert any(step.get("rejected_ungrounded") == ["999"] for step in result.transcript)


async def test_completeness_gate_rejection_continues_the_loop(monkeypatch):
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "answer1", "tool_calls": [_ANSWER]},
               {"thought": "answer2", "tool_calls": [_ANSWER]}],
        sub_asks=["earned?"],
        completeness=[{"unaddressed": ["earned?"]}, {"unaddressed": []}],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert adapter.gate_calls == 2
    assert any(step.get("completeness_rejected") for step in result.transcript)


async def test_what_if_chain_threads_state_via_arg_refs(monkeypatch):
    """The §17.3 chain, previously inexpressible: fetch -> surface -> mutate_state
    (altered state) -> surface -> check_eligibility over {"ref": altered} -> answer.
    Proves a grounded object threads into a tool arg without the model typing it."""
    received: dict[str, Any] = {}

    class _MutateInput(BaseModel):
        base_state: dict[str, Any] = {}
        change: dict[str, Any] = {}

    async def _mutate(payload: _MutateInput) -> ToolOutputEnvelope:
        courses = payload.base_state.get("completedCourses", [])
        altered = {"completedCourses": [{**c, "status": "failed"} for c in courses]}
        return ToolOutputEnvelope(ok=True, data={"state": altered}, certainty=CertaintyTag(basis="hypothetical_simulation", confidence=1.0))

    class _EligInput(BaseModel):
        course_id: str = ""
        state: dict[str, Any] = {}
        student_id: str = ""

    async def _elig(payload: _EligInput) -> ToolOutputEnvelope:
        received["state"] = payload.state
        eligible = all(c.get("status") != "failed" for c in payload.state.get("completedCourses", []))
        return ToolOutputEnvelope(ok=True, data={"eligible": eligible}, certainty=CertaintyTag(basis="official_record", confidence=1.0))

    registry = _stub_registry()
    registry.register(ToolDescriptor(name="mutate_state", description="stub", input_model=_MutateInput, output_model=ToolOutputEnvelope, side_effect="compute", callable=_mutate))
    registry.register(ToolDescriptor(name="check_eligibility", description="stub", input_model=_EligInput, output_model=ToolOutputEnvelope, side_effect="read", callable=_elig))

    turns = [
        {"thought": "fetch", "tool_calls": [_FETCH]},
        {"thought": "surface", "tool_calls": [_SURFACE]},
        {"thought": "mutate", "tool_calls": [{"tool": "mutate_state", "arguments": {"base_state": {"completedCourses": {"ref": "completed"}}, "change": {"type": "fail_course", "courseNumber": "00940224", "semester": "2024-1"}}}]},
        {"thought": "surface altered", "tool_calls": [{"tool": "surface_fact", "arguments": {"key": "altered", "from": "call_2", "path": "data.state"}}]},
        {"thought": "eligibility", "tool_calls": [{"tool": "check_eligibility", "arguments": {"course_id": "00960211", "state": {"ref": "altered"}}}]},
        {"thought": "surface eligible", "tool_calls": [{"tool": "surface_fact", "arguments": {"key": "eligible", "from": "call_3", "path": "data.eligible"}}]},
        {"thought": "answer", "tool_calls": [{"tool": "final_answer", "arguments": {"prose": "Eligibility after failing 00940224: {eligible}.", "fact_refs": {"eligible": "eligible"}}}]},
    ]
    adapter = _FakeAdapter(turns=turns, sub_asks=["Would the student still be eligible?"])
    _install(monkeypatch, adapter)

    result = await run_agent_loop("If I fail 00940224, can I take 00960211?", "u1", registry)

    assert result.outcome == "answered"
    # The tool received the RESOLVED altered state (grounded object), not a {"ref": ...}.
    assert received["state"] == {"completedCourses": [{**c, "status": "failed"} for c in _COMPLETED]}
    assert result.facts["eligible"].value is False
    assert result.answer == "Eligibility after failing 00940224: False."


_EMPTY = {"thought": "stuck", "tool_calls": []}


async def test_forced_compose_recovers_answer_from_grounded_facts_on_exhaustion(monkeypatch):
    """The loop had the facts (earned) but wandered out of turns -- the forced
    compose-from-facts recovers a grounded answer instead of punting."""
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               _EMPTY, _EMPTY, _EMPTY, _EMPTY],
        sub_asks=["earned?"],
        compose={"prose": "You have earned {earned} credits.", "fact_refs": {"earned": "earned"}},
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert adapter.compose_calls == 1


async def test_assembler_floor_ships_grounded_facts_when_compose_fails(monkeypatch):
    """#4: on exhaustion, if the model can't compose but scalar facts exist, the
    deterministic floor ships them grounded rather than a bare punt."""
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               _EMPTY, _EMPTY, _EMPTY, _EMPTY],
        sub_asks=["earned?"],
        compose={"prose": "You have earned 999 credits.", "fact_refs": {}},  # ungrounded -> compose fails
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "budget_exhausted"
    assert "9.5" in result.answer  # the grounded 'earned' fact, shipped by the floor
    assert "determine" in result.answer  # the assembler preamble, not the bare punt
    assert result.ungrounded_numbers == []


async def test_punt_when_no_facts_were_grounded_at_all(monkeypatch):
    """With NO grounded facts, the floor has nothing to ship -> the honest punt."""
    noop = {"tool": "surface_fact", "arguments": {"key": "x", "from": "call_9", "path": "nope"}}
    adapter = _FakeAdapter(
        turns=[{"thought": "noop", "tool_calls": [noop]} for _ in range(runner.NO_PROGRESS_LIMIT + 1)],
        sub_asks=["earned?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("q", "u1", _stub_registry())

    assert result.outcome == "budget_exhausted"
    assert "wasn't able to fully resolve" in result.answer


async def test_answer_rejection_cap_forces_conclusion(monkeypatch):
    """The wanderer that MAKES fact-progress but keeps rejecting its own answer --
    no-progress can't catch it (each turn surfaces a new fact), so the rejection
    cap must. Each turn surfaces a fresh key + emits an ungrounded final answer."""
    bad = {"tool": "final_answer", "arguments": {"prose": "The answer is 999.", "fact_refs": {}}}
    turns = [{"thought": "fetch", "tool_calls": [_FETCH]}]
    for i in range(runner.REJECTION_LIMIT + 3):
        surface = {"tool": "surface_fact", "arguments": {"key": f"k{i}", "from": "call_1", "path": "data.completedCourses"}}
        turns.append({"thought": f"progress+reject {i}", "tool_calls": [surface, bad]})
    adapter = _FakeAdapter(turns=turns, sub_asks=["something"])
    _install(monkeypatch, adapter)

    result = await run_agent_loop("a question with no numbers", "u1", _stub_registry())

    assert result.outcome == "budget_exhausted"  # forced compose can't ground -> punt
    assert result.turns == runner.REJECTION_LIMIT + 1  # one fetch turn, then REJECTION_LIMIT reject turns
    assert result.turns < runner.MAX_TURNS  # capped well before the full budget


async def test_no_progress_governor_forces_graceful_conclusion(monkeypatch):
    noop = {"tool": "surface_fact", "arguments": {"key": "x", "from": "call_9", "path": "nope"}}
    adapter = _FakeAdapter(
        turns=[{"thought": "noop", "tool_calls": [noop]} for _ in range(runner.NO_PROGRESS_LIMIT + 2)],
        sub_asks=["unanswerable"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("q", "u1", _stub_registry())

    assert result.outcome == "budget_exhausted"
    assert "wasn't able to fully resolve" in result.answer
    assert result.turns == runner.NO_PROGRESS_LIMIT


async def test_out_of_scope_question_is_declined_before_the_loop_runs(monkeypatch):
    """§8.1: an out-of-scope decompose short-circuits into a polite decline -- no
    turn is ever taken (the turn queue is never consulted)."""
    adapter = _FakeAdapter(
        turns=[_ANSWER],  # present but must never be consumed
        sub_asks=[],
        front_door={"in_scope": False, "decline_reason": "I can only help with your Technion studies."},
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("write me a poem about the sea", "u1", _stub_registry())

    assert result.outcome == "declined"
    assert "Technion studies" in result.answer
    assert result.turns == 0
    assert result.facts == {}


# -- sub-loops / spawn_subtask (§6) -------------------------------------------


def _dummy_ctx() -> runner._LoopContext:
    """A minimal context for unit-testing `_run_subtask` paths that return before
    ever driving a child (validation / depth-cap / bad-input)."""
    return runner._LoopContext(
        adapter=None,
        registry=None,
        cache=None,
        system_prompt="",
        budget=runner.LoopBudget(deadline=0.0, turns_remaining=0),
        temperature=1.0,
        reasoning_effort="medium",
    )


def test_normalize_output_facts_accepts_a_list_or_a_schema_dict():
    assert runner._normalize_output_facts(["a", "b"]) == ["a", "b"]
    assert runner._normalize_output_facts({"a": "desc", "b": "desc"}) == ["a", "b"]
    assert runner._normalize_output_facts(None) == []
    assert runner._normalize_output_facts("nope") == []


def test_resolve_subtask_inputs_is_refs_only():
    parent = {"total": Fact(158.0, "interpret(...)", "llm_interpretation", 0.9)}
    seeded, errors = runner._resolve_subtask_inputs({"t": {"ref": "total"}}, parent)
    assert errors == []
    assert seeded["t"].value == 158.0
    assert seeded["t"].basis == "llm_interpretation"  # basis inherited across the boundary


def test_resolve_subtask_inputs_rejects_a_typed_literal():
    seeded, errors = runner._resolve_subtask_inputs({"t": 158.0}, {})
    assert seeded == {}
    assert any("must be" in e and "ref" in e for e in errors)


def test_resolve_subtask_inputs_rejects_an_unknown_ref():
    seeded, errors = runner._resolve_subtask_inputs({"t": {"ref": "missing"}}, {})
    assert seeded == {}
    assert any("unknown fact 'missing'" in e for e in errors)


async def test_run_subtask_rejects_at_the_depth_cap():
    parent = WorkingSet(question="q", user_id="u1")
    call = {"tool": "spawn_subtask", "arguments": {"objective": "x", "output_facts": ["y"]}}
    progress, audit = await runner._run_subtask(parent, call, _dummy_ctx(), depth=runner.MAX_SUBLOOP_DEPTH)
    assert progress == 0
    assert audit == []
    assert any("depth cap" in o for o in parent.observations)


async def test_run_subtask_rejects_a_literal_input_without_running_a_child():
    parent = WorkingSet(question="q", user_id="u1")
    call = {"tool": "spawn_subtask", "arguments": {"objective": "x", "inputs": {"a": 5}, "output_facts": ["y"]}}
    progress, audit = await runner._run_subtask(parent, call, _dummy_ctx(), depth=0)
    assert progress == 0
    assert audit == []
    assert any("input error" in o for o in parent.observations)


async def test_spawn_subtask_runs_a_child_loop_and_promotes_its_fact(monkeypatch):
    """§6 end-to-end: the parent grounds a fact, spawns a child seeded ONLY with
    that fact (by ref); the child computes a result in its isolated context and
    returns it; the parent answers from the promoted fact. Context isolation with
    grounding preserved -- the child's raw work never floods the parent trace."""
    spawn = {
        "tool": "spawn_subtask",
        "arguments": {
            "objective": "sum the student's earned credits",
            "inputs": {"completed": {"ref": "completed"}},
            "output_facts": ["earned"],
        },
    }
    child_final = {"tool": "final_answer", "arguments": {"prose": "Computed the total.", "fact_refs": {}}}
    adapter = _FakeAdapter(
        turns=[
            {"thought": "fetch", "tool_calls": [_FETCH]},
            {"thought": "surface", "tool_calls": [_SURFACE]},
            {"thought": "spawn", "tool_calls": [spawn]},
            {"thought": "child computes", "tool_calls": [_COMPUTE]},
            {"thought": "child returns", "tool_calls": [child_final]},
            {"thought": "answer", "tool_calls": [_ANSWER]},
        ],
        sub_asks=["How many credits earned?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert result.facts["earned"].value == 9.5  # promoted from the child loop
    assert result.facts["earned"].basis == "computed"


# -- map: fan a tool over a list, code-side + in parallel (§19) ----------------


class _OfferingInput(BaseModel):
    fact_type: str = ""
    entity: str = ""


_OFFERING_COUNTS = {"00940224": 5, "00960211": 7, "00110001": 2}


async def _stub_offering(payload: _OfferingInput) -> ToolOutputEnvelope:
    return ToolOutputEnvelope(
        ok=True,
        data={"entity": payload.entity, "semestersOffered": _OFFERING_COUNTS.get(payload.entity, 0)},
        certainty=CertaintyTag(basis="predicted_pattern", confidence=0.9),
    )


def _offering_registry() -> ToolRegistry:
    registry = _stub_registry()
    registry.register(
        ToolDescriptor(
            name="extract_temporal_pattern",
            description="stub offering history",
            input_model=_OfferingInput,
            output_model=ToolOutputEnvelope,
            side_effect="compute",
            callable=_stub_offering,
        )
    )
    return registry


async def test_map_fans_a_tool_over_a_list_then_argmax_selects_the_winner(monkeypatch):
    """§19 end-to-end -- the `sub_loop_investigation` shape done RIGHT: enumerate the
    completed codes, `map` the offering tool over all of them (one step, in parallel,
    code-side), then a grounded `select ... by max` picks the winner. No child loop
    per item; the winning code is grounded and the predicted basis flows to a hedge."""
    select_codes = {"tool": "select", "arguments": {"key": "codes", "from_fact": "completed", "field": "courseNumber"}}
    map_call = {
        "tool": "map",
        "arguments": {
            "key": "counts",
            "over": "codes",
            "tool": "extract_temporal_pattern",
            "arg": "entity",
            "args": {"fact_type": "course_offering"},
            "select": "data.semestersOffered",
        },
    }
    argmax = {"tool": "select", "arguments": {"key": "winner", "from_fact": "counts", "by": {"max": "value"}, "field": "entity"}}
    answer = {"tool": "final_answer", "arguments": {"prose": "The course offered in the most semesters is {winner}.", "fact_refs": {"winner": "winner"}}}
    adapter = _FakeAdapter(
        turns=[
            {"thought": "fetch", "tool_calls": [_FETCH]},
            {"thought": "surface", "tool_calls": [_SURFACE]},
            {"thought": "enumerate codes", "tool_calls": [select_codes]},
            {"thought": "map offering over codes", "tool_calls": [map_call]},
            {"thought": "argmax", "tool_calls": [argmax]},
            {"thought": "answer", "tool_calls": [answer]},
        ],
        sub_asks=["Which completed course was offered in the most semesters?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("Which of my completed courses was offered in the most semesters?", "u1", _offering_registry())

    assert result.outcome == "answered"
    assert "00960211" in result.answer  # value 7 -- the argmax
    assert "00940224" not in result.answer and "00110001" not in result.answer
    assert result.ungrounded_numbers == []
    # the mapped list is grounded {entity, value} records, in list order...
    assert result.facts["counts"].value == [
        {"entity": "00940224", "value": 5},
        {"entity": "00960211", "value": 7},
        {"entity": "00110001", "value": 2},
    ]
    assert result.facts["counts"].basis == "predicted_pattern"  # a predicted input hedges the aggregate
    assert result.facts["winner"].value == "00960211"
    assert "On certainty" in result.answer  # predicted_pattern -> rendered hedged
    # the mapped tool's calls fold into the audit (one per code)
    assert sum(1 for record in result.audit if record.tool_name == "extract_temporal_pattern") == 3


async def test_map_over_a_missing_fact_is_a_repairable_error_not_a_crash(monkeypatch):
    map_call = {
        "tool": "map",
        "arguments": {"key": "counts", "over": "nope", "tool": "extract_temporal_pattern", "arg": "entity", "select": "data.semestersOffered"},
    }
    adapter = _FakeAdapter(
        turns=[
            {"thought": "map before grounding the list", "tool_calls": [map_call]},
            {"thought": "give up honestly", "tool_calls": [{"tool": "final_answer", "arguments": {"prose": "I could not determine that.", "fact_refs": {}}}]},
        ],
        sub_asks=["which course?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("which?", "u1", _offering_registry())

    assert result.outcome == "answered"  # concluded honestly, no crash
    assert "counts" not in result.facts  # a bad map admits nothing, fails closed
    assert result.ungrounded_numbers == []


def test_as_fact_key_accepts_bare_string_and_ref_wrapper():
    # The live crash: the model wrote over={"ref":"codes"}, generalizing the
    # {"ref": ...} idiom it uses everywhere else. Both forms must resolve to the key.
    assert runner._as_fact_key("codes") == "codes"
    assert runner._as_fact_key({"ref": "codes"}) == "codes"
    assert runner._as_fact_key({"ref": 5}) is None  # ref must be a string
    assert runner._as_fact_key({"foo": "codes"}) is None  # not a ref wrapper
    assert runner._as_fact_key(["codes"]) is None
    assert runner._as_fact_key(None) is None


async def test_map_accepts_ref_wrapper_for_over_the_live_idiom(monkeypatch):
    """Regression for the live crash: `over` given as {"ref":"codes"} must run the
    same as the bare string, not raise `unhashable type: 'dict'`."""
    select_codes = {"tool": "select", "arguments": {"key": "codes", "from_fact": "completed", "field": "courseNumber"}}
    map_call = {
        "tool": "map",
        "arguments": {"key": "counts", "over": {"ref": "codes"}, "tool": "extract_temporal_pattern", "arg": "entity", "args": {"fact_type": "course_offering"}, "select": "data.semestersOffered"},
    }
    argmax = {"tool": "select", "arguments": {"key": "winner", "from_fact": "counts", "by": {"max": "value"}, "field": "entity"}}
    answer = {"tool": "final_answer", "arguments": {"prose": "Most offered: {winner}.", "fact_refs": {"winner": "winner"}}}
    adapter = _FakeAdapter(
        turns=[
            {"thought": "fetch", "tool_calls": [_FETCH]},
            {"thought": "surface", "tool_calls": [_SURFACE]},
            {"thought": "codes", "tool_calls": [select_codes]},
            {"thought": "map via ref", "tool_calls": [map_call]},
            {"thought": "argmax", "tool_calls": [argmax]},
            {"thought": "answer", "tool_calls": [answer]},
        ],
        sub_asks=["Which completed course was offered in the most semesters?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("which completed course offered most?", "u1", _offering_registry())

    assert result.outcome == "answered"
    assert result.facts["counts"].value == [
        {"entity": "00940224", "value": 5},
        {"entity": "00960211", "value": 7},
        {"entity": "00110001", "value": 2},
    ]
    assert result.facts["winner"].value == "00960211"
    assert "00960211" in result.answer


async def test_map_with_malformed_over_fails_closed_without_crashing(monkeypatch):
    """A dict that is NOT a {"ref": key} must not be hashed into a membership test
    (the live TypeError). Fail closed with a repairable observation; the loop
    survives and concludes honestly instead of aborting the whole request."""
    bad_map = {"tool": "map", "arguments": {"key": "counts", "over": {"not": "a ref"}, "tool": "extract_temporal_pattern", "arg": "entity", "select": "data.semestersOffered"}}
    give_up = {"tool": "final_answer", "arguments": {"prose": "I could not determine that.", "fact_refs": {}}}
    adapter = _FakeAdapter(
        turns=[{"thought": "malformed map", "tool_calls": [bad_map]}, {"thought": "conclude", "tool_calls": [give_up]}],
        sub_asks=["which?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("which?", "u1", _offering_registry())

    assert result.outcome == "answered"  # survived the malformed map, no crash
    assert "counts" not in result.facts
    assert result.ungrounded_numbers == []
