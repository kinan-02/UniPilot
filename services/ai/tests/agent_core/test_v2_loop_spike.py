"""THROWAWAY validation spike for AGENT_ARCHITECTURE_V2 §14.

NOT a permanent test. This exists to answer the one empirical question the whole
V2 redesign rests on, before we delete thousands of lines to build it:

    Does GPT-5-mini (the demo model), given THINKING ON, a LEAN constitution, and
    tool-attached grounding rules -- in a single reasoning loop with the data in
    hand -- (a) follow the fetch/compute/interpret contracts, (b) ground every
    number rather than typing it, and (c) finish inside a turn budget?

It reuses the REAL substrate unchanged (`get_entity` et al., `project_facts`,
`expression_tree`) so the test is fair: the only new thing is the ~1 loop that
replaces the V1 org chart (Planner/Router/TaskHandler/Monitor/5 role blocks).

PROTOCOL (v2 of the spike): ONE uniform channel. Every turn the model emits
`{"thought": ..., "tool_calls": [...]}`. The callable "tools" are the real
substrate tools PLUS four meta-tools -- `surface_fact`, `compute`,
`final_answer`, `clarify` -- so the model never has to distinguish a "tool"
from an "action" (the v1 spike split them and the model conflated the two,
wasting turns). Facts enter ONLY via `surface_fact` (a selector into a recorded
tool envelope) or `compute` (an expression over refs); there is no syntax in
which the model can type a number into a fact. `final_answer` slot-fills
numbers/codes from fact refs, and a deterministic backstop rejects any bare
numeral in the prose that traces to no fact.

Run (needs the dev Mongo up + OPENAI creds in the root .env, same as the
ise_correctness eval):

    cd services/ai && python -m pytest tests/agent_core/test_v2_loop_spike.py -s -m live -o addopts=""

The transcript it prints IS the deliverable -- read what the model actually did.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError
from app.agent_core.reasoning.llm_client import agent_llm_available
from app.agent_core.subagents.fact_projection import (
    available_paths,
    build_call_handles,
    describe_call,
    project_facts,
)
from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.primitives.expression_tree import (
    ExpressionNode,
    evaluate_expression,
    validate_expression_tree,
)
from app.agent_core.tools.registry import ToolRegistry
from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- pytest fixture injection
    IseStudent,
    _fresh_mongo_client_per_test,
    ise_student,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]

_MAX_TURNS = 12
_WALL_CLOCK_S = 150.0
_REASONING_EFFORT = "medium"
_TEMPERATURE = 1.0  # GPT-5 reasoning models reject temperature != 1
_NUM = re.compile(r"\d+(?:\.\d+)?")
_META_TOOLS = frozenset({"surface_fact", "surface_facts", "compute", "select", "final_answer", "clarify"})
_LOG_DIR = Path("/private/tmp/claude-501/-Users-tymoribrahim-Desktop-UniPilot/"
                "5c6a7dbc-d28f-441c-ae9f-d244b9efd3f0/scratchpad")


# --------------------------------------------------------------------------- #
# Working set                                                                  #
# --------------------------------------------------------------------------- #
@dataclass
class Fact:
    value: Any
    source: str
    basis: str
    confidence: float


@dataclass
class WorkingSet:
    question: str
    user_id: str
    sub_asks: list[str] = field(default_factory=list)
    facts: dict[str, Fact] = field(default_factory=dict)
    tool_results: dict[str, Any] = field(default_factory=dict)
    handles: dict[str, str] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)


@dataclass
class Terminal:
    kind: str      # "answered" | "clarified"
    text: str
    ungrounded: list[str]


# --------------------------------------------------------------------------- #
# Constitution (system prompt) -- deliberately short (V2 §4.3, tier 1)          #
# --------------------------------------------------------------------------- #
def _constitution(user_id: str, tool_catalog: str) -> str:
    return f"""You are UniPilot, an academic advisor for Technion students. You answer by
REASONING IN A LOOP with the data in hand -- never by guessing.

THE GROUNDING LAW (absolute):
You may NEVER write a number, credit total, grade, course code, semester, or status
into an answer out of your own head. Every such fact must be one of:
  - FETCHED     -- read out of a tool result by a path (surface_fact).
  - COMPUTED    -- arithmetic over already-fetched facts (compute).
  - INTERPRETED -- read from cited authoritative text (interpret_text).
If you cannot ground a fact, SAY SO honestly ("I could not determine X"). A wrong or
made-up number is far worse than an admitted gap.

HOW YOU WORK:
Each turn, output EXACTLY ONE JSON object and nothing else:
  {{"thought": "brief reasoning", "tool_calls": [ {{"tool": "<name>", "arguments": {{...}}}}, ... ]}}
You may list several calls in one turn. They run in order; a fetch you request this
turn is not visible until next turn, so surface/compute against it on a later turn.

There is ONE kind of call. Alongside the data tools below, four built-in tools turn
raw results into grounded facts and end the turn -- use these, never invent others:

  - surface_fact: promote a value from a recorded tool result into a named fact.
      {{"tool":"surface_fact","arguments":{{"key":"completed","from":"call_1","path":"data.completedCourses"}}}}
      (or surface several: {{"tool":"surface_fact","arguments":{{"selectors":[{{"key":..,"from":..,"path":..}}]}}}})
      The value is READ from the result by its path -- you never type it.

  - compute: derive a new fact by arithmetic over EXISTING facts (leaves are refs to fact keys).
      {{"tool":"compute","arguments":{{"key":"earned","expression":{{"op":"sum","of":{{"ref":"completed"}},"field":"creditsEarned"}}}}}}
      Operators: sum/count/average (need "of": a list-valued ref, plus "field"); add/subtract/
      multiply/divide (need "left"/"right"); compare (need "left"/"right"/"comparator").
      A leaf is {{"ref":"factKey"}} or {{"const": <a literal you were explicitly given, NEVER a
      total you worked out>}}. An all-const expression is rejected.

  - select: pull the record(s) matching a field value out of a LIST-valued fact, or one field of it.
      {{"tool":"select","arguments":{{"key":"status_x","from_fact":"completed_courses","where":{{"courseNumber":"00940224"}},"field":"grade"}}}}
      This is how you answer "the student's status/grade on course X": filter their completed-courses
      list by courseNumber and read the grade. Omit "field" to get the whole matching record. NO MATCH
      (empty result) is itself a grounded answer -- the course is not in that list. The selected value
      is grounded (read from the list), so you can slot it straight into a final answer.

  - final_answer (ends the turn): numbers/codes MUST be slots filled from fact refs.
      {{"tool":"final_answer","arguments":{{"prose":"You still need {{gap}} credits.","fact_refs":{{"gap":"gap"}}}}}}
      Each {{slot}} is replaced by code with the fact's value. A bare number typed in prose
      that did not come from a slot is REJECTED and you must retry.

  - clarify (ends the turn): {{"tool":"clarify","arguments":{{"question":"..."}}}}  -- only if genuinely blocked.

The student's user_id is: {user_id}
(use it as entity_id for student_profile / completed_courses / semester_plan).

DATA TOOLS:
{tool_catalog}
"""


# Tool-attached usage notes (V2 §4.3): the hard-won specifics that make a tool
# callable, surfaced at the point of use instead of buried in a role prompt. The
# v2 spike proved this is load-bearing -- without the interpret_text note the
# model passed a call handle as `source` (wrong), failed 3x, and laundered a
# `const` total instead of grounding it.
_TOOL_NOTES: dict[str, str] = {
    "get_entity": (
        "entity_type is one of: student_profile / completed_courses / semester_plan "
        "(entity_id = the user_id); course / track / program / minor / faculty / wiki_page "
        "(entity_id = a course CODE or a wiki SLUG). There is NO 'degree' entity_type."
    ),
    "interpret_text": (
        "source MUST be a wiki SLUG (e.g. the track slug 'track-information-systems-engineering'), "
        "NOT a call handle and NOT raw text -- it fetches that page itself and reads the answer from "
        "its prose. This is how you GROUND a number stated only in text (e.g. total credits required "
        "to complete a track). When the answer is a number, the result has a TYPED numeric field at "
        "data.numericValue -- surface THAT (not data.answer, which is prose) to compute with it."
    ),
    "get_track_requirements": "track_slug = the track slug from the student's profile (programSlug/trackSlug).",
}


def _tool_catalog(registry: ToolRegistry) -> str:
    lines: list[str] = []
    for name in registry.names():
        descriptor = registry.get(name)
        fields = ", ".join(descriptor.input_model.model_fields.keys())
        one_line = " ".join(descriptor.description.split())[:150]
        lines.append(f"- {name}({fields}) [{descriptor.side_effect}]: {one_line}")
        if name in _TOOL_NOTES:
            lines.append(f"    NOTE: {_TOOL_NOTES[name]}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Working-set rendering (the only uncached tier) -- V2 §5                       #
# --------------------------------------------------------------------------- #
def _summarize_value(value: Any) -> str:
    if isinstance(value, list):
        sample = value[0] if value else None
        keys = sorted(sample.keys()) if isinstance(sample, dict) else None
        tail = f", record keys: {keys}" if keys else ""
        return f"[list of {len(value)} items{tail}]"
    if isinstance(value, dict):
        return f"{{dict with keys: {sorted(value.keys())}}}"
    return json.dumps(value, ensure_ascii=False, default=str)


def _render_working_set(ws: WorkingSet, turn: int) -> str:
    if ws.facts:
        fact_lines = "\n".join(
            f"  {k} = {_summarize_value(f.value)}  (source: {f.source}; basis: {f.basis}; conf: {f.confidence})"
            for k, f in ws.facts.items()
        )
    else:
        fact_lines = "  (none yet)"

    if ws.handles:
        idx_lines = []
        for handle, result_key in ws.handles.items():
            envelope = ws.tool_results.get(result_key, {})
            if envelope.get("ok"):
                idx_lines.append(f"  {handle} = {describe_call(result_key)}  ok=True\n     paths: {available_paths(envelope)}")
            else:
                idx_lines.append(f"  {handle} = {describe_call(result_key)}  ok=False error={envelope.get('error')}")
        idx = "\n".join(idx_lines)
    else:
        idx = "  (no tool calls yet)"

    obs = "\n".join(f"  - {o}" for o in ws.observations[-8:]) or "  (none)"
    sub_asks = "\n".join(f"  - {s}" for s in ws.sub_asks) or "  (none)"

    return (
        f"QUESTION: {ws.question}\n"
        f"USER_ID: {ws.user_id}\n\n"
        f"SUB-ASKS -- your final answer MUST address every one of these:\n{sub_asks}\n\n"
        f"GROUNDED FACTS:\n{fact_lines}\n\n"
        f"TOOL RESULTS INDEX:\n{idx}\n\n"
        f"OBSERVATIONS (recent):\n{obs}\n\n"
        f"BUDGET: turn {turn}/{_MAX_TURNS}. Emit one JSON object with tool_calls."
    )


# --------------------------------------------------------------------------- #
# Meta-tool handlers                                                           #
# --------------------------------------------------------------------------- #
def _basis_by_handle(ws: WorkingSet) -> dict[str, str]:
    out = {}
    for handle, key in ws.handles.items():
        certainty = (ws.tool_results.get(key) or {}).get("certainty") or {}
        out[handle] = certainty.get("basis", "unknown")
    return out


def _do_surface(ws: WorkingSet, args: dict[str, Any]) -> None:
    selectors = args.get("selectors")
    if selectors is None:  # single-selector shorthand
        selectors = [{"key": args.get("key"), "from": args.get("from"), "path": args.get("path")}]
    outcome = project_facts(selectors, ws.tool_results, ws.handles)
    basis_by_handle = _basis_by_handle(ws)
    selector_basis = {s.get("key"): basis_by_handle.get(s.get("from"), "unknown") for s in selectors}
    for key, fact in outcome.facts.items():
        ws.facts[key] = Fact(fact["value"], fact["source"], selector_basis.get(key, "unknown"), fact["confidence"])
        ws.observations.append(f"surfaced fact '{key}' = {_summarize_value(fact['value'])}")
    for err in outcome.errors:
        ws.observations.append(f"surface_fact error: {err}")


_ARITHMETIC_OPS = frozenset({"add", "subtract", "multiply", "divide"})


def _numeric_const_operands(node: ExpressionNode) -> list[Any]:
    """Numeric `const` leaves used as an operand of binary arithmetic.

    The v2 spike caught the const-laundering seam: the model typed `{"const": 155}`
    for the degree total and subtracted the grounded earned credits, shipping a
    number whose provenance was the model's own head. Tightens §4.2 -- an
    arithmetic operand that produces an answer number must be a REF to a grounded
    fact (fetched/computed/interpreted), never a literal the model wrote down.
    A genuinely user-given literal is a separate, later concern; neither eval
    case needs one, so blocking numeric consts outright is safe and decisive here.
    """
    found: list[Any] = []
    if node.op in _ARITHMETIC_OPS:
        for child in (node.left, node.right):
            if child is not None and child.const is not None and isinstance(child.const, (int, float)) and not isinstance(child.const, bool):
                found.append(child.const)
    for child in (node.of, node.left, node.right):
        if child is not None:
            found.extend(_numeric_const_operands(child))
    return found


def _do_compute(ws: WorkingSet, args: dict[str, Any]) -> None:
    key = args.get("key")
    raw_expr = args.get("expression")
    if not key or raw_expr is None:
        ws.observations.append("compute error: missing 'key' or 'expression'")
        return
    try:
        node = ExpressionNode(**raw_expr)
    except Exception as exc:  # noqa: BLE001
        ws.observations.append(f"compute error: malformed expression: {exc}")
        return
    laundered = _numeric_const_operands(node)
    if laundered:
        ws.observations.append(
            f"compute '{key}' REJECTED: arithmetic operand(s) {laundered} are typed literals, not grounded facts. "
            f"A number like this must be FETCHED or INTERPRETED first (e.g. interpret_text on the track wiki slug "
            f"for total required credits), surfaced as a fact, then referenced with a ref -- never typed as a const."
        )
        return
    facts_values = {k: f.value for k, f in ws.facts.items()}
    errors = validate_expression_tree(node, facts=facts_values)
    if errors:
        ws.observations.append(f"compute '{key}' rejected: {errors}")
        return
    value, trace, eval_errors = evaluate_expression(node, facts_values)
    if eval_errors:
        ws.observations.append(f"compute '{key}' failed: {eval_errors}")
        return
    refs_used = {k for k in ws.facts if f'"{k}"' in json.dumps(raw_expr)}
    confidence = min((ws.facts[r].confidence for r in refs_used), default=1.0)
    ws.facts[key] = Fact(value, f"compute({'; '.join(trace)})", "computed", confidence)
    ws.observations.append(f"computed '{key}' = {value}  [{'; '.join(trace)}]")


def _do_select(ws: WorkingSet, args: dict[str, Any]) -> None:
    """Filter a list-valued fact by a field match and read a record or one field.

    The capability the presupposition case needed and the substrate lacked: a
    selector can only walk a path, `expression_tree` can only aggregate -- neither
    can pull "the record where courseNumber == X" out of a list and read its grade.
    Deterministic operation over an already-grounded fact, so the result inherits
    that fact's basis/confidence (still grounded, still Computed under Invariant A);
    an empty match is a real, grounded answer ("not in that list"), not a failure.
    """
    key = args.get("key")
    from_fact = args.get("from_fact")
    where = args.get("where") or {}
    field = args.get("field")
    if not key or not from_fact:
        ws.observations.append("select error: missing 'key' or 'from_fact'")
        return
    if from_fact not in ws.facts:
        ws.observations.append(f"select error: no fact named '{from_fact}' (available: {sorted(ws.facts)})")
        return
    source = ws.facts[from_fact]
    if not isinstance(source.value, list):
        ws.observations.append(f"select error: fact '{from_fact}' is not a list (it is {type(source.value).__name__})")
        return
    matched = [
        r for r in source.value
        if isinstance(r, dict) and all(str(r.get(k)) == str(v) for k, v in where.items())
    ]
    if field is not None:
        picked = [r.get(field) for r in matched]
        value: Any = picked[0] if len(picked) == 1 else picked
    else:
        value = matched[0] if len(matched) == 1 else matched
    label = f"select({from_fact} where {where}" + (f").{field}" if field else ")")
    ws.facts[key] = Fact(value, label, source.basis, source.confidence)
    ws.observations.append(f"selected '{key}' = {_summarize_value(value)} ({len(matched)} match(es))")


def _resolve_final(ws: WorkingSet, args: dict[str, Any]) -> tuple[str, list[str]]:
    """Slot-fill the prose from fact refs, then run the deterministic backstop.

    Returns (rendered_prose, ungrounded_tokens): any numeral in the final prose
    that traces to no slotted fact and did not come from the student's question.
    """
    prose = str(args.get("prose") or "")
    fact_refs = args.get("fact_refs") or {}
    slotted_values: list[str] = []
    unresolved: list[str] = []

    def _sub(match: re.Match) -> str:
        slot = match.group(1)
        ref = fact_refs.get(slot)
        if ref in ws.facts:
            value = ws.facts[ref].value
            if isinstance(value, (dict, list)):
                # A slot must render a SCALAR; binding a whole record/list dumps
                # raw JSON into the prose. Flag it so the answer is rejected and
                # the model `select`s the specific field instead.
                unresolved.append(f"{slot}->non-scalar {type(value).__name__} (select a field)")
                return match.group(0)
            rendered = str(value)
            slotted_values.append(rendered)
            return rendered
        # A slot bound to no fact is a grounding failure, not text: leave the
        # {slot} visible and flag it, so a broken answer (a compute that never
        # produced its fact) is rejected instead of shipping the ref's key name
        # as prose. §4.2 -- every slot must bind to a fact.
        unresolved.append(f"{slot}->{ref}")
        return match.group(0)

    rendered = re.sub(r"\{(\w+)\}", _sub, prose)
    allowed = set()
    for sv in slotted_values:
        allowed.update(_NUM.findall(sv))
    allowed.update(_NUM.findall(ws.question))  # echoing a code from the question is fine
    problems = [tok for tok in _NUM.findall(rendered) if tok not in allowed]
    problems += [f"unresolved_slot:{u}" for u in unresolved]
    return rendered, problems


# --------------------------------------------------------------------------- #
# The loop                                                                     #
# --------------------------------------------------------------------------- #
@dataclass
class SpikeResult:
    case: str
    outcome: str            # "answered" | "clarified" | "budget_exhausted"
    answer: str
    ungrounded_numbers: list[str]
    turns: int
    llm_calls: int
    wall_clock_s: float
    transcript: list[dict[str, Any]]
    sub_asks: list[str] = field(default_factory=list)


async def _process_turn(ws: WorkingSet, calls: list[dict[str, Any]], registry: ToolRegistry) -> Terminal | None:
    """Run all real-tool calls first (so a same-turn surface can see them), then
    the meta-tools in listed order. Returns a Terminal if the turn ends the loop."""
    real_requests = []
    meta_calls = []
    for call in calls:
        name = call.get("tool")
        if name in _META_TOOLS:
            meta_calls.append(call)
        else:
            real_requests.append({"tool_name": name, "arguments": call.get("arguments") or {}})

    if real_requests:
        merged, audit = await execute_tool_round(
            tool_requests=real_requests,
            tool_grant=registry.names(),
            tool_registry=registry,
            tool_results_so_far=ws.tool_results,
            log_prefix="spike",
        )
        ws.tool_results = merged
        ws.handles = build_call_handles(merged)
        for record in audit:
            ws.observations.append(f"called {record.tool_name}({record.arguments}) -> ok={record.output_ok}")

    for call in meta_calls:
        name = call.get("tool")
        args = call.get("arguments") or {}
        if name in ("surface_fact", "surface_facts"):
            _do_surface(ws, args)
        elif name == "compute":
            _do_compute(ws, args)
        elif name == "select":
            _do_select(ws, args)
        elif name == "clarify":
            return Terminal("clarified", str(args.get("question") or ""), [])
        elif name == "final_answer":
            rendered, ungrounded = _resolve_final(ws, args)
            if ungrounded:
                ws.observations.append(
                    f"final_answer REJECTED: numerals {ungrounded} trace to no fact; slot-fill or drop them."
                )
                call["_rejected_ungrounded"] = ungrounded
                continue
            return Terminal("answered", rendered, ungrounded)
    return None


# --------------------------------------------------------------------------- #
# §8 decomposition + §9 completeness gate -- the structural completeness fix    #
# --------------------------------------------------------------------------- #
_DECOMPOSER_SYSTEM = """You break a Technion student's question into the concrete sub-questions that
must ALL be answered for the reply to be complete and correct. Output ONLY JSON:
{"sub_asks": ["...", "..."]}.

Rules:
- Sub-asks are what the ANSWER must contain to be complete and honest -- NOT intermediate
  calculation steps. "How many credits remain?" is ONE sub-ask (the remaining number); the
  earned-so-far total used to compute it is not its own sub-ask.
- Each sub-ask is a SPECIFIC, checkable question, never an abstraction.
- PRESUPPOSITIONS (critical): if the question takes something about the student for
  granted -- "if I fail X", "when I retake Y", "after I finish Z", "since I'm in year N"
  -- emit a concrete sub-ask that VERIFIES that premise against the student's record,
  phrased as a direct lookup: e.g. "What is the student's current status and grade on
  course X?" -- NOT "verify the premise". A false premise (e.g. X is already passed) would
  make the answer misleading, so the answer MUST surface the real status -- this sub-ask is
  mandatory whenever a premise about the student is present.
- Keep it minimal -- only the sub-asks the answer genuinely must address. A simple factual
  question may have exactly one."""

_COMPLETENESS_SYSTEM = """You verify whether a DRAFT answer addresses every required sub-question.
Output ONLY JSON: {"unaddressed": ["<verbatim sub-ask>", ...]} -- list each sub-ask the
draft does NOT substantively address; empty list if all are addressed.

A sub-ask is "addressed" only if the draft states the relevant fact. "I could not determine
it" counts as addressed ONLY for genuinely external/unknowable facts -- NEVER for a sub-ask
about the student's OWN record (their status/grade on a course, their completed courses),
because that data is always in the record and must be looked up. For a status sub-ask, the
draft must actually REFLECT the status (e.g. that the course is already completed, with the
grade) -- merely NAMING the course, or claiming it could not be determined, does NOT count."""


async def _decompose(adapter: ChatLLMAdapter, question: str) -> list[str]:
    """§8: the question -> concrete sub-asks, presuppositions made explicit."""
    try:
        out = await adapter.complete_json(
            system_prompt=_DECOMPOSER_SYSTEM,
            user_prompt=json.dumps({"question": question}, ensure_ascii=False),
            temperature=_TEMPERATURE, thinking_enabled=True, reasoning_effort=_REASONING_EFFORT, timeout=60.0,
        )
    except LLMAdapterError:
        return [question]  # fail open: a decomposer failure must not block the turn
    subs = out.get("sub_asks")
    if isinstance(subs, list):
        cleaned = [str(s).strip() for s in subs if str(s).strip()]
        if cleaned:
            return cleaned
    return [question]


async def _completeness_gate(adapter: ChatLLMAdapter, question: str, sub_asks: list[str], answer: str) -> list[str]:
    """§9: the sub-asks the draft answer leaves unaddressed (empty = complete).

    Fails OPEN -- a gate-call failure returns "complete" rather than trapping the
    student behind a broken checker; the turn budget still bounds continuations.
    """
    try:
        out = await adapter.complete_json(
            system_prompt=_COMPLETENESS_SYSTEM,
            user_prompt=json.dumps(
                {"question": question, "sub_asks": sub_asks, "draft_answer": answer}, ensure_ascii=False
            ),
            temperature=_TEMPERATURE, thinking_enabled=True, reasoning_effort=_REASONING_EFFORT, timeout=60.0,
        )
    except LLMAdapterError:
        return []
    unaddressed = out.get("unaddressed")
    if isinstance(unaddressed, list):
        return [str(s).strip() for s in unaddressed if str(s).strip()]
    return []


async def _run_spike(case: str, question: str, user_id: str, registry: ToolRegistry) -> SpikeResult:
    adapter = ChatLLMAdapter()
    ws = WorkingSet(question=question, user_id=user_id)
    system_prompt = _constitution(user_id, _tool_catalog(registry))
    transcript: list[dict[str, Any]] = []
    started = time.monotonic()
    llm_calls = 1
    ws.sub_asks = await _decompose(adapter, question)

    for turn in range(1, _MAX_TURNS + 1):
        if time.monotonic() - started > _WALL_CLOCK_S:
            break
        user_prompt = _render_working_set(ws, turn)
        raw_out: list[str] = []
        try:
            llm_calls += 1
            action = await adapter.complete_json(
                system_prompt=system_prompt, user_prompt=user_prompt, temperature=_TEMPERATURE,
                thinking_enabled=True, reasoning_effort=_REASONING_EFFORT, raw_model_text_out=raw_out, timeout=90.0,
            )
        except LLMAdapterError as exc:
            transcript.append({"turn": turn, "error": exc.detail, "raw": (raw_out[-1] if raw_out else None)})
            ws.observations.append(f"LLM call failed ({exc.code}); emit ONE valid JSON object with tool_calls.")
            continue

        calls = action.get("tool_calls") or []
        transcript.append({"turn": turn, "thought": action.get("thought"), "calls": calls})
        terminal = await _process_turn(ws, calls, registry)
        for call in calls:  # surface any rejection back onto the transcript
            if call.get("_rejected_ungrounded"):
                transcript[-1].setdefault("rejected_ungrounded", call["_rejected_ungrounded"])
        if terminal is not None:
            # §9 completeness gate: a grounded answer must still ADDRESS every
            # sub-ask. This is what turns "the model should check the premise"
            # into "the model cannot ship without it" -- the structural fix the
            # prompt-level rule (falsified earlier) could not deliver.
            if terminal.kind == "answered" and ws.sub_asks:
                llm_calls += 1
                unaddressed = await _completeness_gate(adapter, question, ws.sub_asks, terminal.text)
                if unaddressed:
                    ws.observations.append(
                        f"completeness gate REJECTED the answer -- unaddressed sub-asks: {unaddressed}. "
                        "Fetch what's needed to address them, then answer again."
                    )
                    transcript[-1].setdefault("completeness_rejected", unaddressed)
                    continue
            return SpikeResult(case, terminal.kind, terminal.text, terminal.ungrounded, turn, llm_calls,
                               time.monotonic() - started, transcript, sub_asks=ws.sub_asks)

    return SpikeResult(case, "budget_exhausted", "", [], _MAX_TURNS, llm_calls,
                       time.monotonic() - started, transcript, sub_asks=ws.sub_asks)


def _report(result: SpikeResult) -> None:
    print(f"\n{'=' * 78}\nSPIKE CASE: {result.case}\n{'=' * 78}")
    print("  SUB-ASKS (decomposed):")
    for s in result.sub_asks:
        print(f"    - {s}")
    print()
    for step in result.transcript:
        if "error" in step:
            print(f"  turn {step['turn']}: LLM ERROR {step['error']}")
            continue
        print(f"  turn {step['turn']}: {step.get('thought')}")
        for call in step["calls"]:
            payload = json.dumps(call.get("arguments") or {}, ensure_ascii=False, default=str)
            print(f"           -> {call.get('tool')}({payload[:300]})")
        if step.get("rejected_ungrounded"):
            print(f"           >>> REJECTED ungrounded numerals: {step['rejected_ungrounded']}")
        if step.get("completeness_rejected"):
            print(f"           >>> COMPLETENESS GATE rejected -- unaddressed: {step['completeness_rejected']}")
    print(f"\n  OUTCOME:   {result.outcome}")
    print(f"  ANSWER:    {result.answer}")
    print(f"  UNGROUNDED IN FINAL PROSE: {result.ungrounded_numbers or 'none'}")
    print(f"  turns={result.turns}  llm_calls={result.llm_calls}  wall_clock={result.wall_clock_s:.1f}s")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = _LOG_DIR / f"v2_spike_{result.case}.json"
    out.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
    print(f"  transcript written to {out}")


# --------------------------------------------------------------------------- #
# The two decisive cases (V2 §14)                                              #
# --------------------------------------------------------------------------- #
async def test_spike_credits_remaining(ise_student: IseStudent) -> None:
    result = await _run_spike(
        "credits_remaining",
        "How many credits do I still need to complete my degree?",
        ise_student.user_id,
        build_default_tool_registry(),
    )
    _report(result)
    assert result.outcome in ("answered", "clarified"), f"loop did not conclude: {result.outcome}"
    assert not result.ungrounded_numbers, (
        f"GROUNDING VIOLATION: final answer typed numerals {result.ungrounded_numbers} "
        f"that trace to no fetched/computed fact.\n{result.answer}"
    )


async def test_spike_presupposition_conflict(ise_student: IseStudent) -> None:
    result = await _run_spike(
        "presupposition_conflict",
        "If I fail course 00940224 this semester, will I still be able to take 00960211 afterwards?",
        ise_student.user_id,
        build_default_tool_registry(),
    )
    _report(result)
    assert result.outcome in ("answered", "clarified"), f"loop did not conclude: {result.outcome}"
    assert not result.ungrounded_numbers, (
        f"GROUNDING VIOLATION: final answer typed numerals {result.ungrounded_numbers} "
        f"that trace to no fetched/computed fact.\n{result.answer}"
    )
