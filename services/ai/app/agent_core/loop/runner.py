"""The agent loop -- the reasoning core (AGENT_ARCHITECTURE_V2.md §4, §7).

One thinking-enabled loop. Each turn the model reasons over the working set and
emits ONE JSON object with `tool_calls`; a call is either a data tool (run via
`execute_tool_round`) or a built-in fact-admission/terminal meta-tool. Facts can
only be born in the substrate, so no turn can type an ungrounded number.

The loop is governed against its one failure mode -- wandering (§7): a turn/
wall-clock budget, a no-progress cap (a turn admitting no new fact counts toward
it), and per-request tool-call dedup via a fresh `ToolCallCache`. On exhaustion
it degrades gracefully to an honest conclusion, never silence.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.loop.answer_boundary import completeness_gate, polish_answer, resolve_final
from app.agent_core.loop.arg_refs import resolve_arg_refs
from app.agent_core.loop.constitution import build_constitution, build_tool_catalog
from app.agent_core.loop.course_names import course_display_name
from app.agent_core.loop.fact_admission import apply_compute, apply_select, apply_surface, project_mapped_records
from app.agent_core.loop.front_door import decompose
from app.agent_core.loop.working_set import Fact, Terminal, WorkingSet, render_working_set, summarize_value
from app.agent_core.certainty import ToolInvocationRecord
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError
from app.agent_core.subagents.fact_projection import build_call_handles, describe_call
from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry

# Budgets (§7). Wall-clock is deliberately under the API timeout so the student
# gets our honest conclusion, never a dropped connection.
MAX_TURNS = 12
# 150.0 until the planning eval (2026-07-18) showed both of its exhaustions dying
# at ~194s with SEVEN of twelve turns unused -- they ran out of time, not steps,
# on exactly the multi-step questions the loop exists for. The rationale for
# staying under the caller's timeout is unchanged; what changed is the caller:
# ai_advisor's client timeout went to 300s in 21ad03c, so 150 was leaving half the
# available headroom unused. A turn can overshoot by up to TURN_TIMEOUT_S, so this
# still lands comfortably inside 300.
WALL_CLOCK_S = 240.0
NO_PROGRESS_LIMIT = 3
# How many rejected final answers (grounding backstop or completeness gate) before
# we stop letting the model re-try and force a conclusion. The live eval's
# wanderers spent their whole budget re-rejecting their own drafts (§16 follow-up).
REJECTION_LIMIT = 4
# Attempts at the exhaustion compose. The second exists only for a model that
# returns EMPTY prose -- observed six times in the 2026-07-18 live run, once
# costing a correct grounded answer. An ungrounded compose does not retry.
_FORCED_COMPOSE_ATTEMPTS = 2
# The readability pass (§9.3) is built, guarded, and OFF. It fails closed -- every
# guard discards the rewrite and ships the accepted draft -- so enabling it cannot
# produce a wrong answer. What is unproven is its VALUE: across the 2026-07-18
# live runs it damaged an answer in each one (stripped a certainty hedge, dropped
# the course being discussed twice, duplicated a list, leaked "predicted_pattern
# with confidence 0.95" to a student), every time breaking a rule its own prompt
# stated. Four guards now catch those, but the eval cannot SEE phrasing damage --
# grade_filter_above_90 scored 8/8 while emitting a duplicated list -- so a clean
# scorecard is not evidence the pass is behaving. It also costs ~+1 LLM call per
# answer and ~+20% wall clock. Turn this on once the eval scores readability
# (duplicate phrases, entity retention, vocabulary, hedge presence); until then it
# would be a feature whose regressions only surface when a human reads the output.
POLISH_ENABLED = False
TURN_TIMEOUT_S = 90.0
# Sub-loops (§6) exist for CONTEXT ISOLATION only -- a subtask whose raw material
# would flood the parent's reasoning trace. Depth is capped in code to forbid
# runaway recursion; a sub-loop shares (debits) the parent's turn and wall-clock
# budget, so decomposition can never buy unbounded total work.
MAX_SUBLOOP_DEPTH = 2
# `map` (§19) fans one data tool over a grounded list CONCURRENTLY in code. The cap
# bounds how many concurrent tool calls (and audit records) a single map can fire;
# the ISE completed set is 17, comfortably under. A longer list must be narrowed
# first -- an explicit error, never a silent truncation.
MAX_MAP_FANOUT = 40

_FORCED_COMPOSE_SYSTEM = """You are OUT of tool budget and must answer NOW, using ONLY the grounded
facts already gathered -- no more tools, no invented values. Output ONLY a final_answer JSON:
{"prose": "...", "fact_refs": {"slot": "factKey", ...}}.
Every number, grade, code, semester, or status in the prose MUST be a {slot} filled from fact_refs
(a bare number is rejected). A list-valued fact renders as its comma-separated values.
NAME the specific course code(s) and entities the question is about (a code from the question may
be written directly). Address every sub-ask the facts let you address; for anything the facts do
not cover, say honestly you could not determine it. Answer the student directly and completely."""

# Reasoning params for the demo model (GPT-5-mini): thinking ON, medium effort,
# temperature 1.0 (GPT-5 reasoning models reject temperature != 1).
LOOP_TEMPERATURE = 1.0
REASONING_EFFORT = "medium"
# The front door and the completeness gate are CLASSIFICATION, not reasoning: is
# this in scope, what are the sub-asks, does this draft address them. Together
# they are ~25% of a request's LLM calls (the 1.56 calls-per-turn measured over
# 36 case-runs is the loop's own turns plus these), and at 6.2s per call that is
# real latency spent on work that does not need the reasoning budget the loop
# does. The loop itself stays at REASONING_EFFORT.
MECHANICAL_REASONING_EFFORT = "low"

_META_TOOLS = frozenset(
    {"surface_fact", "surface_facts", "compute", "select", "map", "spawn_subtask", "final_answer", "clarify"}
)


@dataclass
class AgentLoopResult:
    outcome: str  # "answered" | "clarified" | "declined" | "budget_exhausted"
    answer: str
    ungrounded_numbers: list[str]
    sub_asks: list[str]
    facts: dict[str, Fact]
    audit: list[ToolInvocationRecord]
    turns: int
    llm_calls: int
    wall_clock_s: float
    transcript: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LoopBudget:
    """The shared, debitable budget (§6, §7). One instance is created per request
    and passed to every loop -- root and any sub-loop -- so a child's turns and
    wall-clock draw down the SAME counters as the parent. `llm_calls` is a shared
    tally across the whole tree, reported on the root result."""

    deadline: float  # absolute time.monotonic() by which every loop must stop
    turns_remaining: int  # decremented by each turn of any loop in the tree
    llm_calls: int = 0


@dataclass
class _LoopContext:
    """The per-request substrate a loop and its sub-loops all share: one adapter,
    one registry, one cache (so a child's fetches hit the parent's cache and vice
    versa, §6), one constitution, and the shared budget. Only `depth` varies
    between parent and child, so it is passed alongside, not stored here."""

    adapter: ChatLLMAdapter
    registry: ToolRegistry
    cache: ToolCallCache
    system_prompt: str
    budget: LoopBudget
    temperature: float
    reasoning_effort: str


def _split_calls(calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Data-tool requests vs meta-tool calls, preserving each group's order."""
    real_requests: list[dict[str, Any]] = []
    meta_calls: list[dict[str, Any]] = []
    for call in calls:
        if call.get("tool") in _META_TOOLS:
            meta_calls.append(call)
        else:
            real_requests.append({"tool_name": call.get("tool"), "arguments": call.get("arguments") or {}})
    return real_requests, meta_calls


async def _run_data_tools(
    ws: WorkingSet, requests: list[dict[str, Any]], registry: ToolRegistry, cache: ToolCallCache
) -> tuple[int, list[ToolInvocationRecord]]:
    """Run the turn's data-tool calls, refresh the working set's result index,
    and report progress (count of newly-recorded successful results).

    Each call's `{"ref": factKey}` arguments are resolved to grounded values
    first (§17.3); a call with an unresolvable ref is skipped with a repairable
    observation rather than dispatched malformed."""
    resolved_requests: list[dict[str, Any]] = []
    for request in requests:
        args, errors = resolve_arg_refs(request["arguments"], ws.facts)
        if errors:
            for err in errors:
                ws.observe(f"tool '{request['tool_name']}' arg error: {err}")
            continue
        resolved_requests.append({"tool_name": request["tool_name"], "arguments": args})
    if not resolved_requests:
        return 0, []

    before = set(ws.tool_results)
    grant = registry.names()
    # Independent calls the model listed together actually RUN concurrently
    # (§4.1) -- one execute_tool_round per request, gathered. Each starts from the
    # same result base; the shared cache's per-key lock keeps a duplicated key
    # safe (only one real invocation), and gather preserves input order so the
    # merged audit stays deterministic. This is the same concurrency V1's
    # parallel_dispatch already relied on, now recovered without an up-front plan.
    rounds = await asyncio.gather(
        *(
            execute_tool_round(
                tool_requests=[request],
                tool_grant=grant,
                tool_registry=registry,
                tool_results_so_far=ws.tool_results,
                tool_call_cache=cache,
                log_prefix="agent_loop",
            )
            for request in resolved_requests
        )
    )
    merged = dict(ws.tool_results)
    audit: list[ToolInvocationRecord] = []
    for round_results, round_audit in rounds:
        merged.update(round_results)
        audit.extend(round_audit)
    ws.tool_results = merged
    ws.handles = build_call_handles(merged)
    for record in audit:
        ws.observe(f"called {record.tool_name}({record.arguments}) -> ok={record.output_ok}")
    new_ok = sum(
        1
        for key in set(merged) - before
        if isinstance(merged.get(key), dict) and merged[key].get("ok")
    )
    return new_ok, audit


async def _preload_student_state(
    ws: WorkingSet, ctx: _LoopContext
) -> list[ToolInvocationRecord]:
    """Fetch and surface the student's record BEFORE turn 1.

    Measured over 36 live case-runs: turn 1 was `get_entity` 39 times and turn 2
    was `surface_fact` 51 times. Nearly every request opened by fetching the
    profile and transcript and surfacing them -- the same two calls, in the same
    order, to answer any question about a student. That is ~2 of a mean 5.2
    turns spent re-deriving a constant, and at ~6.2s per LLM call it is also two
    extra chances to wander before the real work starts.

    Runs through the ordinary `_run_data_tools` path, so results, handles, audit
    records and cache entries are indistinguishable from a turn the model drove --
    the model can reference `call_1`/`call_2` exactly as it does today, and a
    later duplicate fetch is a cache hit rather than a second record.

    Fails OPEN: a student with no profile, or a registry without `get_entity`
    (sub-loop grants, tests), simply preloads nothing and the loop proceeds as
    before. Preloading is an optimisation, never a precondition.
    """
    if not ctx.registry.has("get_entity"):
        return []
    requests = [
        {"tool_name": "get_entity", "arguments": {"entity_type": "student_profile", "entity_id": ws.user_id}},
        {"tool_name": "get_entity", "arguments": {"entity_type": "completed_courses", "entity_id": ws.user_id}},
    ]
    _, audit = await _run_data_tools(ws, requests, ctx.registry, ctx.cache)

    # Surface only what the model surfaced by hand anyway. Each is skipped
    # silently when its path is absent, so a partial record preloads partially
    # rather than not at all.
    for key, handle, path in (
        ("completed_courses", "call_2", "data.completedCourses"),
        ("track_slug", "call_1", "data.academicPath.trackSlug"),
    ):
        if handle in ws.handles:
            apply_surface(ws, {"key": key, "from": handle, "path": path})

    ws.observe(
        "Your record was loaded before this turn: "
        f"{', '.join(sorted(ws.facts)) or 'nothing available'} "
        f"(raw results in {', '.join(sorted(ws.handles))}). Do NOT re-fetch these; "
        "build on them."
    )
    return audit


def _as_fact_key(value: Any) -> str | None:
    """Resolve `map`'s `over` to a fact-key STRING. Accepts a bare key or the
    system's `{"ref": key}` idiom -- the model generalizes `{"ref": ...}` here from
    tool-args and spawn inputs (a live run did exactly this), so meeting it where it
    is beats rejecting a reasonable form. Anything else -> None, so the caller fails
    closed instead of hashing a dict into a membership test (the live crash)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and set(value) == {"ref"} and isinstance(value.get("ref"), str):
        return value["ref"]
    return None


async def _run_map(
    ws: WorkingSet, call: dict[str, Any], ctx: _LoopContext
) -> tuple[int, list[ToolInvocationRecord]]:
    """Run one `map` (§19): fan a single data tool over every scalar in a grounded
    list fact, CONCURRENTLY in code, and collect the projected results into one new
    grounded list fact of {entity, value} records -- the map half of map-reduce,
    the reduce left to `select`/`compute`.

    This is the right grain for uniform aggregation over data (17 course codes ->
    17 offering-history lookups): ONE model decision, a code-level fan-out over the
    same concurrent-execution + shared-cache path a normal turn's parallel calls
    use, and a grounded result -- not a tree of reasoning sub-loops, each burning
    LLM calls and adding its own variance to make a single deterministic tool call.
    Returns (progress, audit) -- the mapped calls' audit folds into the parent so
    course/source derivation sees them, exactly as `_run_data_tools`."""
    args = call.get("arguments") or {}
    key = args.get("key")
    over = _as_fact_key(args.get("over"))
    tool_name = args.get("tool")
    arg_name = args.get("arg")
    static_args = args.get("args") or {}
    select_path = args.get("select")
    if not isinstance(key, str) or not over or not isinstance(tool_name, str) or not isinstance(arg_name, str):
        ws.observe(
            'map error: needs \'key\' (result fact name), \'over\' (the grounded list fact -- its key as a '
            'string, or {"ref": key}), \'tool\' (a data-tool name), and \'arg\' (the tool argument each item '
            "fills) -- all strings."
        )
        return 0, []
    if not isinstance(static_args, dict):
        ws.observe("map error: 'args' (static arguments applied to every call) must be an object.")
        return 0, []
    if select_path is not None and not isinstance(select_path, str):
        ws.observe("map error: 'select' must be a string path (e.g. 'data.semestersOffered') or omitted.")
        return 0, []
    if over not in ws.facts:
        ws.observe(f"map error: no fact named '{over}' (available: {sorted(ws.facts)})")
        return 0, []
    elements = ws.facts[over].value
    if not isinstance(elements, list) or not elements:
        ws.observe(f"map error: fact '{over}' is not a non-empty list.")
        return 0, []
    if any(isinstance(element, (dict, list)) for element in elements):
        ws.observe(
            f"map error: '{over}' must be a list of SCALARS (e.g. course codes). Use `select` with a "
            "'field' to project a scalar list first."
        )
        return 0, []
    if tool_name in _META_TOOLS or tool_name not in ctx.registry.names():
        ws.observe(f"map error: 'tool' must be one of the DATA tools, not '{tool_name}'.")
        return 0, []
    if len(elements) > MAX_MAP_FANOUT:
        ws.observe(
            f"map error: {len(elements)} items exceeds the fan-out cap ({MAX_MAP_FANOUT}); narrow the list first."
        )
        return 0, []

    requests = [
        {"tool_name": tool_name, "arguments": {**static_args, arg_name: element}} for element in elements
    ]
    grant = ctx.registry.names()
    rounds = await asyncio.gather(
        *(
            execute_tool_round(
                tool_requests=[request],
                tool_grant=grant,
                tool_registry=ctx.registry,
                tool_results_so_far=ws.tool_results,
                tool_call_cache=ctx.cache,
                log_prefix="agent_loop_map",
            )
            for request in requests
        )
    )
    merged = dict(ws.tool_results)
    audit: list[ToolInvocationRecord] = []
    for round_results, round_audit in rounds:
        merged.update(round_results)
        audit.extend(round_audit)
    ws.tool_results = merged
    ws.handles = build_call_handles(merged)
    # Align each element's result envelope by re-deriving the result key exactly as
    # tool_round keys it (`{tool}:{json.dumps(args, sort_keys=True, default=str)}`,
    # tool_round.py) -- deterministic, and robust to duplicate elements.
    envelopes = [
        merged.get(f"{request['tool_name']}:{json.dumps(request['arguments'], sort_keys=True, default=str)}")
        for request in requests
    ]
    records, basis, confidence, errors = project_mapped_records(elements, envelopes, select_path)
    for err in errors:
        ws.observe(f"map '{key}': skipped {err}")
    if not records:
        ws.observe(
            f"map '{key}' produced no records ({len(elements)} call(s), none yielded "
            f"{'path ' + select_path if select_path else 'data'})."
        )
        return 0, audit
    source = f"map({tool_name} over {over}" + (f", select {select_path})" if select_path else ")")
    signature = f"map:{tool_name}:{over}:{select_path}:{json.dumps(static_args, sort_keys=True, default=str)}"
    admitted = ws.admit_derivation(key, Fact(records, source, basis, confidence), signature)
    suffix = "" if admitted else " (already mapped; no new info)"
    ws.observe(
        f"mapped {tool_name} over {len(elements)} item(s) from '{over}' -> '{key}' = "
        f"{summarize_value(records)} (basis: {basis}){suffix}"
    )
    return int(admitted), audit


def _apply_meta_call(ws: WorkingSet, call: dict[str, Any]) -> tuple[Terminal | None, int]:
    """Dispatch one meta-tool. Returns (terminal, progress) -- terminal ends the
    loop; progress is the count of new facts admitted this call."""
    name = call.get("tool")
    args = call.get("arguments") or {}
    if name in ("surface_fact", "surface_facts"):
        return None, apply_surface(ws, args)
    if name == "compute":
        return None, apply_compute(ws, args)
    if name == "select":
        return None, apply_select(ws, args)
    if name == "clarify":
        return Terminal("clarified", str(args.get("question") or ""), []), 0
    if name == "final_answer":
        rendered, ungrounded = resolve_final(ws.question, ws.facts, str(args.get("prose") or ""), args.get("fact_refs") or {})
        if ungrounded:
            ws.observe(f"final_answer REJECTED: numerals {ungrounded} trace to no fact; slot-fill or drop them.")
            call["_rejected_ungrounded"] = ungrounded
            return None, 0
        return Terminal("answered", rendered, ungrounded, args.get("fact_refs") or {}), 0
    return None, 0


async def _process_turn(
    ws: WorkingSet, calls: list[dict[str, Any]], ctx: _LoopContext, depth: int
) -> tuple[Terminal | None, int, list[ToolInvocationRecord]]:
    """Run data-tool calls first (so a same-turn surface can see them), then the
    meta-tools in listed order. `spawn_subtask` runs a child loop (§6); the rest
    are the synchronous fact-admission/terminal meta-tools. Returns (terminal,
    progress, audit)."""
    real_requests, meta_calls = _split_calls(calls)
    progress = 0
    audit: list[ToolInvocationRecord] = []
    if real_requests:
        tool_progress, audit = await _run_data_tools(ws, real_requests, ctx.registry, ctx.cache)
        progress += tool_progress
    for call in meta_calls:
        try:
            if call.get("tool") == "spawn_subtask":
                sub_progress, sub_audit = await _run_subtask(ws, call, ctx, depth)
                progress += sub_progress
                audit.extend(sub_audit)
                continue
            if call.get("tool") == "map":
                map_progress, map_audit = await _run_map(ws, call, ctx)
                progress += map_progress
                audit.extend(map_audit)
                continue
            terminal, meta_progress = _apply_meta_call(ws, call)
        except Exception as exc:  # noqa: BLE001 -- a malformed meta-call must degrade to a
            # repairable observation, never crash the whole request: the same "never
            # raises" contract execute_tool_round holds for data tools (tool_round.py).
            # A live run aborted an entire eval when `map` hashed a `{"ref": ...}` it
            # got for `over`; that specific case is now handled, this is the backstop.
            ws.observe(
                f"'{call.get('tool')}' failed on malformed input ({type(exc).__name__}); "
                "fix the arguments and retry, or use a different step."
            )
            continue
        progress += meta_progress
        if terminal is not None:
            return terminal, progress, audit
    return None, progress, audit


def _readable_value(value: str) -> str:
    """`00940224` -> `Data Structures and Algorithms (00940224)`.

    The floor renders fact values itself rather than going through
    `resolve_final`, so it would otherwise be the one user-visible answer still
    shipping bare codes -- which is exactly what it did ship.
    """
    name = course_display_name(value)
    return f"{name} ({value})" if name else value


def _join_sub_asks(sub_asks: list[str]) -> str:
    """Sub-asks are phrased as questions, so a naive join + '.' rendered '?.'."""
    return "; ".join(s.rstrip(" .?!") for s in sub_asks)


def _punt_message(ws: WorkingSet) -> str:
    """Last-resort honest conclusion when even a forced compose can't ground an
    answer: names the open sub-asks and points to the secretariat, never guesses.

    Here the sub-asks really ARE open -- no fact was grounded at all -- which is
    what separates this from the assembler floor below."""
    parts = ["I wasn't able to fully resolve your question within my working limits."]
    if ws.sub_asks:
        parts.append("Open items: " + _join_sub_asks(ws.sub_asks) + ".")
    parts.append("Please check with your faculty secretariat for a definitive answer.")
    return " ".join(parts)


def _assemble_from_facts(ws: WorkingSet) -> str | None:
    """Deterministic grounded FLOOR (#4): when the model cannot compose an answer
    but the working set holds usable facts, ship those facts -- grounded by
    construction, read straight from the fact values (no model, no fabrication) --
    rather than a bare punt. Skips non-scalar objects (a raw record/dict is not
    answer-usable). Terse, but never empty when there is something grounded to say."""
    lines: list[str] = []
    for key, fact in ws.facts.items():
        value = fact.value
        if isinstance(value, dict):
            continue
        if isinstance(value, list):
            if not value or isinstance(value[0], (dict, list)):
                continue
            rendered = ", ".join(_readable_value(str(item)) for item in value)
        else:
            rendered = _readable_value(str(value))
        lines.append(f"- {key}: {rendered}")
    if not lines:
        return None
    # Framing matters here, because these facts are often the COMPLETE answer.
    # The floor cannot tell -- the gate that decides coverage is an LLM call and
    # the budget is spent -- so it states what it determined and flags the
    # coverage it could not confirm. It must not announce a failure it cannot
    # establish: the live run listed the three correct course codes and then
    # declared that same question "Still open", sending the user to the
    # secretariat for an answer sitting in the line above.
    parts = ["Here is what I determined from your record:"]
    parts.extend(lines)
    if ws.sub_asks:
        parts.append(
            "I ran out of working budget before I could confirm this fully covers: "
            + _join_sub_asks(ws.sub_asks)
            + ". If anything is missing, your faculty secretariat can confirm it."
        )
    return "\n".join(parts)


async def _forced_compose(
    adapter: ChatLLMAdapter, ws: WorkingSet, *, temperature: float, reasoning_effort: str
) -> tuple[str | None, int]:
    """Graceful degradation (§7): compose a final answer from ONLY the facts
    already grounded, returning `(answer, llm_calls_spent)`. The live eval showed
    the loop often HAD the answer's facts (a selected grade, an eligibility
    result) but wandered out of budget before composing -- this recovers those.
    Runs the same grounding backstop, so a compose that slips an ungrounded
    number is rejected (-> floor).

    Retries ONCE, and only on empty prose. In the 2026-07-18 run the model
    returned well-formed but empty responses on six turns, and a single empty
    compose was enough to discard a correct, fully grounded answer. An UNGROUNDED
    compose is not retried: the backstop caught an attempt to fabricate, and
    asking again is just another roll of the same dice.
    """
    if not ws.facts:
        return None, 0
    facts_desc = "\n".join(
        f"  {key} = {summarize_value(fact.value)} (basis: {fact.basis})" for key, fact in ws.facts.items()
    )
    sub_asks = "\n".join(f"  - {s}" for s in ws.sub_asks) or "  (none)"
    user_prompt = (
        f"QUESTION: {ws.question}\n\nSUB-ASKS:\n{sub_asks}\n\n"
        f"GROUNDED FACTS (the ONLY values you may use):\n{facts_desc}\n\n"
        "Emit the final_answer JSON now."
    )
    calls = 0
    for _ in range(_FORCED_COMPOSE_ATTEMPTS):
        calls += 1
        try:
            out = await adapter.complete_json(
                system_prompt=_FORCED_COMPOSE_SYSTEM,
                user_prompt=user_prompt,
                temperature=temperature,
                thinking_enabled=True,
                reasoning_effort=reasoning_effort,
                timeout=TURN_TIMEOUT_S,
            )
        except LLMAdapterError:
            return None, calls
        prose = str(out.get("prose") or "")
        if not prose:
            continue  # said nothing at all -- worth one more ask
        rendered, ungrounded = resolve_final(ws.question, ws.facts, prose, out.get("fact_refs") or {})
        return (rendered if not ungrounded else None), calls
    return None, calls


def _normalize_output_facts(spec: Any) -> list[str]:
    """The fact keys a subtask must return: a list of key names, or a schema dict
    whose keys are the names."""
    if isinstance(spec, dict):
        return [str(k) for k in spec if str(k).strip()]
    if isinstance(spec, list):
        return [str(k) for k in spec if str(k).strip()]
    return []


def _resolve_subtask_inputs(
    inputs: Any, parent_facts: dict[str, Fact]
) -> tuple[dict[str, Fact], list[str]]:
    """Seed a child loop's facts from the parent's -- REFS ONLY. Each input value
    must be {"ref": <a grounded parent fact key>}; a typed literal is rejected, so
    Invariant A holds across the boundary: a child can only start from values the
    parent already grounded, never a number the model typed into the spawn."""
    if not isinstance(inputs, dict):
        return {}, ['"inputs" must be an object mapping child fact keys to {"ref": parentFactKey}']
    seeded: dict[str, Fact] = {}
    errors: list[str] = []
    for key, value in inputs.items():
        if isinstance(value, dict) and set(value.keys()) == {"ref"} and isinstance(value.get("ref"), str):
            src = parent_facts.get(value["ref"])
            if src is None:
                errors.append(f"input '{key}' references unknown fact '{value['ref']}' (available: {sorted(parent_facts)})")
                continue
            seeded[key] = Fact(src.value, f"subtask_input(from {value['ref']})", src.basis, src.confidence)
        else:
            errors.append(f"input '{key}' must be {{\"ref\": <a grounded parent fact key>}}, not a typed literal")
    return seeded, errors


def _child_question(objective: str, output_facts: list[str]) -> str:
    return (
        f"{objective}\n\n"
        f"This is a SUBTASK in an ISOLATED context, with the SAME tools and grounding rules as the main "
        f"loop. Any GROUNDED FACTS shown to you are real, fully-grounded INPUTS -- a fact shown as "
        f"'[list of N values: ...]' or '[list of N records: ...]' HOLDS those items: read or filter them "
        f"with select/compute, and FETCH anything else you need with the data tools (e.g. one call per code). "
        f"Do NOT answer 'I cannot determine' just because a seeded fact is not already the final answer -- "
        f"deriving it from your inputs and tools IS the job. When done, ground the fact(s) named EXACTLY "
        f"{output_facts} (those exact key names) and call final_answer. ONLY those named facts return to the "
        f"parent; everything else you fetch stays contained here."
    )


async def _run_subtask(
    parent_ws: WorkingSet, call: dict[str, Any], ctx: _LoopContext, depth: int
) -> tuple[int, list[ToolInvocationRecord]]:
    """Run one `spawn_subtask` (§6): a child loop with fresh context (only the
    resolved `inputs`), the same substrate + shared budget, at depth+1. Its
    requested `output_facts` are promoted back into the parent as grounded facts
    (value/basis/confidence preserved). Returns (progress, child_audit) -- the
    child's tool audit folds into the parent's so course/source derivation sees it."""
    args = call.get("arguments") or {}
    objective = str(args.get("objective") or "").strip()
    output_facts = _normalize_output_facts(args.get("output_facts") or args.get("output_schema"))
    if not objective or not output_facts:
        parent_ws.observe("spawn_subtask error: needs 'objective' and 'output_facts' (the fact keys to return).")
        return 0, []
    if depth >= MAX_SUBLOOP_DEPTH:
        parent_ws.observe(
            f"spawn_subtask REJECTED: sub-loop depth cap ({MAX_SUBLOOP_DEPTH}) reached -- do this inline as normal turns."
        )
        return 0, []
    seeded, errors = _resolve_subtask_inputs(args.get("inputs") or {}, parent_ws.facts)
    if errors:
        for err in errors:
            parent_ws.observe(f"spawn_subtask input error: {err}")
        return 0, []

    child_ws = WorkingSet(
        question=_child_question(objective, output_facts),
        user_id=parent_ws.user_id,
        language=parent_ws.language,
    )
    child_ws.facts = seeded
    child_ws.sub_asks = [objective]
    child_result = await _drive(child_ws, ctx, depth + 1, run_completeness=False, run_polish=False)
    parent_ws.observe(f"sub-loop [{objective[:60]}] -> {child_result.outcome} in {child_result.turns} turn(s)")

    promoted = 0
    for key in output_facts:
        fact = child_ws.facts.get(key)
        if fact is None:
            parent_ws.observe(f"sub-loop did not produce requested fact '{key}'")
            continue
        signature = f"subtask:{objective}:{key}"
        admitted = parent_ws.admit_derivation(
            key,
            Fact(fact.value, f"spawn_subtask({objective}) -> {fact.source}", fact.basis, fact.confidence),
            signature,
        )
        suffix = "" if admitted else " (already held)"
        parent_ws.observe(f"sub-loop produced '{key}' = {summarize_value(fact.value)} (basis: {fact.basis}){suffix}")
        promoted += int(admitted)
    return promoted, child_result.audit


async def _drive(
    ws: WorkingSet, ctx: _LoopContext, depth: int, *, run_completeness: bool, run_polish: bool
) -> AgentLoopResult:
    """The reasoning loop core (§4, §7), shared by the root loop and every
    sub-loop. Runs turns until a terminal or exhaustion, governed against
    wandering, then degrades gracefully. Termination draws down the SHARED budget
    (`ctx.budget`), so a sub-loop's turns debit the parent's. `run_completeness`
    is off for sub-loops -- their completeness is structural (did they produce the
    requested output facts), checked by the promotion step in `_run_subtask`.

    `run_polish` is off for sub-loops too, and for a different reason: a child's
    answer is not read by a human, it is parsed for the facts it promotes to the
    parent. Rewriting it for readability would spend a call making a machine-read
    string prettier, and give a rewrite the chance to disturb what the parent
    reads."""
    transcript: list[dict[str, Any]] = []
    audit: list[ToolInvocationRecord] = []
    started = time.monotonic()
    no_progress = 0
    answer_rejections = 0
    turn = 0
    while ctx.budget.turns_remaining > 0 and time.monotonic() <= ctx.budget.deadline:
        ctx.budget.turns_remaining -= 1
        turn += 1

        raw_out: list[str] = []
        try:
            ctx.budget.llm_calls += 1
            action = await ctx.adapter.complete_json(
                system_prompt=ctx.system_prompt,
                user_prompt=render_working_set(ws, turn, MAX_TURNS),
                temperature=ctx.temperature,
                thinking_enabled=True,
                reasoning_effort=ctx.reasoning_effort,
                raw_model_text_out=raw_out,
                timeout=TURN_TIMEOUT_S,
            )
        except LLMAdapterError as exc:
            transcript.append({"turn": turn, "error": exc.detail, "raw": (raw_out[-1] if raw_out else None)})
            ws.observe(f"LLM call failed ({exc.code}); emit ONE valid JSON object with tool_calls.")
            continue

        calls = action.get("tool_calls") or []
        transcript.append({"turn": turn, "thought": action.get("thought"), "calls": calls})
        terminal, progress, turn_audit = await _process_turn(ws, calls, ctx, depth)
        audit.extend(turn_audit)
        rejected_this_turn = False
        for call in calls:  # surface any grounding rejection onto the transcript
            if call.get("_rejected_ungrounded"):
                transcript[-1].setdefault("rejected_ungrounded", call["_rejected_ungrounded"])
                rejected_this_turn = True

        if terminal is not None:
            if terminal.kind == "answered" and ws.sub_asks and run_completeness:
                # §9.2 completeness gate: a grounded answer must still ADDRESS
                # every sub-ask -- the structural fix the falsified prompt-level
                # rule could not deliver. Rejection resumes the loop with the
                # named gap (bounded continuation, §9.3).
                ctx.budget.llm_calls += 1
                unaddressed = await completeness_gate(
                    ctx.adapter, ws.question, ws.sub_asks, terminal.text,
                    temperature=ctx.temperature, reasoning_effort=MECHANICAL_REASONING_EFFORT,
                )
                if unaddressed:
                    ws.observe(
                        f"completeness gate REJECTED the answer -- unaddressed sub-asks: {unaddressed}. "
                        "Fetch what's needed to address them, then answer again."
                    )
                    transcript[-1].setdefault("completeness_rejected", unaddressed)
                    answer_rejections += 1
                    if answer_rejections < REJECTION_LIMIT:
                        continue
                    ws.observe(f"answer-rejection limit reached ({REJECTION_LIMIT}); composing from grounded facts.")
                    break
            # Readability pass, LAST: the answer is grounded and complete, and
            # only its phrasing is left. Runs after the completeness gate so a
            # draft that gets rejected is never polished, and its result is
            # re-validated -- a rewrite that fabricates or drops a fact is
            # discarded and this answer ships unchanged.
            answer_text = terminal.text
            if terminal.kind == "answered" and run_polish:
                ctx.budget.llm_calls += 1
                polished = await polish_answer(
                    ctx.adapter, ws.question, ws.facts, terminal.text, terminal.fact_refs,
                    temperature=ctx.temperature, reasoning_effort=ctx.reasoning_effort,
                )
                transcript.append({"turn": turn, "polish": {"applied": polished is not None}})
                answer_text = polished or terminal.text
            return AgentLoopResult(
                terminal.kind, answer_text, terminal.ungrounded, ws.sub_asks, ws.facts,
                audit, turn, ctx.budget.llm_calls, time.monotonic() - started, transcript,
            )

        # Anti-wander (§7): a repeatedly self-rejected final answer means the model
        # is stuck composing, not making progress -- cap it before it burns the
        # whole budget re-rejecting its own drafts.
        if rejected_this_turn:
            answer_rejections += 1
            if answer_rejections >= REJECTION_LIMIT:
                ws.observe(f"answer-rejection limit reached ({REJECTION_LIMIT}); composing from grounded facts.")
                break

        # No-progress governor (§7): a turn that admits no new fact and records no
        # new successful fetch counts toward the cap that forces conclusion. Detect-
        # and-correct (#1): re-orient on a wasted turn rather than only counting, so
        # the model breaks a repeat instead of spinning to exhaustion.
        if progress == 0:
            # An EMPTY action and an unproductive one are different failures, and
            # only one of them is the model's own blind spot: told to "do something
            # DIFFERENT", a model that emitted nothing has nothing to differ from.
            # Six such turns occurred in the 2026-07-18 run.
            if not calls:
                ws.observe(
                    "your last turn returned no tool_calls at all -- nothing ran, and no time is "
                    "left to waste. Emit ONE JSON object with a NON-EMPTY tool_calls array, or "
                    "compose the final_answer now from the facts you already hold."
                )
            else:
                ws.observe(
                    "that turn added NO new information -- do something DIFFERENT next: drill an object "
                    "into a scalar leaf, `select` a field, `compute` over facts you hold, or compose the "
                    "final_answer now from those facts."
                )
        no_progress = no_progress + 1 if progress == 0 else 0
        if no_progress >= NO_PROGRESS_LIMIT:
            ws.observe(f"no-progress limit reached ({NO_PROGRESS_LIMIT} turns); concluding.")
            break

    # Graceful degradation (§7): try one bounded compose from the facts already
    # grounded before punting -- the loop often HAS the answer, just ran out of
    # turns to say it.
    composed: str | None = None
    if ws.facts:
        composed, compose_calls = await _forced_compose(
            ctx.adapter, ws, temperature=ctx.temperature, reasoning_effort=ctx.reasoning_effort
        )
        ctx.budget.llm_calls += compose_calls
        # Without this the compose is invisible: a run that silently dropped a
        # grounded answer read exactly like one that never had facts to compose.
        transcript.append(
            {"turn": turn, "forced_compose": {"attempts": compose_calls, "composed": composed is not None}}
        )
    if composed is not None:
        # §9.2: even the exhaustion answer is checked for completeness -- but here
        # we cannot loop to close a gap (the budget is spent), so we ship the
        # grounded answer and HONESTLY name any sub-ask it could not cover, rather
        # than silently dropping it (the R2 "forced-compose dropped the code" miss).
        if ws.sub_asks and run_completeness:
            ctx.budget.llm_calls += 1
            unaddressed = await completeness_gate(
                ctx.adapter, ws.question, ws.sub_asks, composed,
                temperature=ctx.temperature, reasoning_effort=MECHANICAL_REASONING_EFFORT,
            )
            if unaddressed:
                composed += "\n\nI could not fully address: " + "; ".join(unaddressed) + "."
        return AgentLoopResult(
            "answered", composed, [], ws.sub_asks, ws.facts,
            audit, turn, ctx.budget.llm_calls, time.monotonic() - started, transcript,
        )
    # Deterministic grounded FLOOR (#4): ship the facts we hold rather than a bare
    # punt when the model couldn't compose from them.
    floor = _assemble_from_facts(ws)
    return AgentLoopResult(
        "budget_exhausted", floor if floor is not None else _punt_message(ws), [], ws.sub_asks, ws.facts,
        audit, turn, ctx.budget.llm_calls, time.monotonic() - started, transcript,
    )


async def run_agent_loop(
    question: str,
    user_id: str,
    registry: ToolRegistry,
    *,
    temperature: float = LOOP_TEMPERATURE,
    reasoning_effort: str = REASONING_EFFORT,
) -> AgentLoopResult:
    """The root loop: scope-gate + decompose, then drive at depth 0 with a fresh
    per-request budget and cache (the freshness invariant, §5). Sub-loops reuse
    this same driver through `_run_subtask`, sharing the budget and cache."""
    started = time.monotonic()
    adapter = ChatLLMAdapter()
    ws = WorkingSet(question=question, user_id=user_id)
    cache = ToolCallCache()  # fresh per request -- freshness invariant (§5)
    system_prompt = build_constitution(user_id, build_tool_catalog(registry))
    budget = LoopBudget(deadline=started + WALL_CLOCK_S, turns_remaining=MAX_TURNS)
    ctx = _LoopContext(
        adapter=adapter,
        registry=registry,
        cache=cache,
        system_prompt=system_prompt,
        budget=budget,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )

    budget.llm_calls += 1
    front_door = await decompose(
        adapter,
        question,
        temperature=temperature,
        reasoning_effort=MECHANICAL_REASONING_EFFORT,
        tool_names=frozenset(registry.names()),
    )
    if not front_door.in_scope:
        # §8.1: an out-of-scope question is declined politely BEFORE the loop runs
        # -- no tools, no wandering, no fabricated deflection.
        return AgentLoopResult(
            "declined",
            front_door.decline_reason or "That falls outside what I can help with as your academic advisor.",
            [], [], {}, [], 0, budget.llm_calls, time.monotonic() - started, [],
        )
    ws.sub_asks = front_door.sub_asks
    # AFTER the scope gate on purpose: an out-of-scope question still costs zero
    # tool calls, which is what keeps a decline at 0 turns / 1 call / ~1s.
    preload_audit = await _preload_student_state(ws, ctx)
    if front_door.suggested_tools:
        # A HINT, never a dispatch -- the loop can ignore it, and every name was
        # validated against the registry before it got here.
        ws.observe(
            "these tools look most direct for this question: "
            f"{', '.join(front_door.suggested_tools)} -- prefer a composite that answers it "
            "in one call over assembling primitives, but use your own judgement."
        )
    result = await _drive(ws, ctx, 0, run_completeness=True, run_polish=POLISH_ENABLED)
    # The preloaded fetches belong to this request's audit trail like any other.
    result.audit[:0] = preload_audit
    return result


__all__ = [
    "AgentLoopResult",
    "LoopBudget",
    "run_agent_loop",
    "MAX_TURNS",
    "WALL_CLOCK_S",
    "NO_PROGRESS_LIMIT",
    "MAX_SUBLOOP_DEPTH",
    "MAX_MAP_FANOUT",
]
