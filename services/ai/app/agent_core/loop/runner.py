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

import time
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.loop.answer_boundary import completeness_gate, resolve_final
from app.agent_core.loop.arg_refs import resolve_arg_refs
from app.agent_core.loop.constitution import build_constitution, build_tool_catalog
from app.agent_core.loop.fact_admission import apply_compute, apply_select, apply_surface
from app.agent_core.loop.front_door import decompose
from app.agent_core.loop.working_set import Fact, Terminal, WorkingSet, render_working_set, summarize_value
from app.agent_core.planning.state import ToolInvocationRecord
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError
from app.agent_core.subagents.fact_projection import build_call_handles, describe_call
from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry

# Budgets (§7). Wall-clock is deliberately under the API timeout so the student
# gets our honest conclusion, never a dropped connection.
MAX_TURNS = 12
WALL_CLOCK_S = 150.0
NO_PROGRESS_LIMIT = 3
# How many rejected final answers (grounding backstop or completeness gate) before
# we stop letting the model re-try and force a conclusion. The live eval's
# wanderers spent their whole budget re-rejecting their own drafts (§16 follow-up).
REJECTION_LIMIT = 4
TURN_TIMEOUT_S = 90.0

_FORCED_COMPOSE_SYSTEM = """You are OUT of tool budget and must answer NOW, using ONLY the grounded
facts already gathered -- no more tools, no invented values. Output ONLY a final_answer JSON:
{"prose": "...", "fact_refs": {"slot": "factKey", ...}}.
Every number, grade, code, semester, or status in the prose MUST be a {slot} filled from fact_refs
(a bare number is rejected). A list-valued fact renders as its comma-separated values.
Address every sub-ask the facts let you address; for anything the facts do not cover, say honestly
you could not determine it. Answer the student directly and completely from what you have."""

# Reasoning params for the demo model (GPT-5-mini): thinking ON, medium effort,
# temperature 1.0 (GPT-5 reasoning models reject temperature != 1).
LOOP_TEMPERATURE = 1.0
REASONING_EFFORT = "medium"

_META_TOOLS = frozenset({"surface_fact", "surface_facts", "compute", "select", "final_answer", "clarify"})


@dataclass
class AgentLoopResult:
    outcome: str  # "answered" | "clarified" | "budget_exhausted"
    answer: str
    ungrounded_numbers: list[str]
    sub_asks: list[str]
    facts: dict[str, Fact]
    audit: list[ToolInvocationRecord]
    turns: int
    llm_calls: int
    wall_clock_s: float
    transcript: list[dict[str, Any]] = field(default_factory=list)


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
    merged, audit = await execute_tool_round(
        tool_requests=resolved_requests,
        tool_grant=registry.names(),
        tool_registry=registry,
        tool_results_so_far=ws.tool_results,
        tool_call_cache=cache,
        log_prefix="agent_loop",
    )
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
        return Terminal("answered", rendered, ungrounded), 0
    return None, 0


async def _process_turn(
    ws: WorkingSet, calls: list[dict[str, Any]], registry: ToolRegistry, cache: ToolCallCache
) -> tuple[Terminal | None, int, list[ToolInvocationRecord]]:
    """Run data-tool calls first (so a same-turn surface can see them), then the
    meta-tools in listed order. Returns (terminal, progress, audit)."""
    real_requests, meta_calls = _split_calls(calls)
    progress = 0
    audit: list[ToolInvocationRecord] = []
    if real_requests:
        tool_progress, audit = await _run_data_tools(ws, real_requests, registry, cache)
        progress += tool_progress
    for call in meta_calls:
        terminal, meta_progress = _apply_meta_call(ws, call)
        progress += meta_progress
        if terminal is not None:
            return terminal, progress, audit
    return None, progress, audit


def _punt_message(ws: WorkingSet) -> str:
    """Last-resort honest conclusion when even a forced compose can't ground an
    answer: names the open sub-asks and points to the secretariat, never guesses."""
    parts = ["I wasn't able to fully resolve your question within my working limits."]
    if ws.sub_asks:
        parts.append("Open items: " + "; ".join(ws.sub_asks) + ".")
    parts.append("Please check with your faculty secretariat for a definitive answer.")
    return " ".join(parts)


async def _forced_compose(
    adapter: ChatLLMAdapter, ws: WorkingSet, *, temperature: float, reasoning_effort: str
) -> str | None:
    """Graceful degradation (§7), one bounded LLM call: compose a final answer
    from ONLY the facts already grounded. The live eval showed the loop often
    HAD the answer's facts (a selected grade, an eligibility result) but wandered
    out of budget before composing -- this recovers those. Runs the same grounding
    backstop, so a compose that slips an ungrounded number is rejected (-> punt)."""
    if not ws.facts:
        return None
    facts_desc = "\n".join(
        f"  {key} = {summarize_value(fact.value)} (basis: {fact.basis})" for key, fact in ws.facts.items()
    )
    sub_asks = "\n".join(f"  - {s}" for s in ws.sub_asks) or "  (none)"
    user_prompt = (
        f"QUESTION: {ws.question}\n\nSUB-ASKS:\n{sub_asks}\n\n"
        f"GROUNDED FACTS (the ONLY values you may use):\n{facts_desc}\n\n"
        "Emit the final_answer JSON now."
    )
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
        return None
    prose = str(out.get("prose") or "")
    rendered, ungrounded = resolve_final(ws.question, ws.facts, prose, out.get("fact_refs") or {})
    if prose and not ungrounded:
        return rendered
    return None


async def run_agent_loop(
    question: str,
    user_id: str,
    registry: ToolRegistry,
    *,
    temperature: float = LOOP_TEMPERATURE,
    reasoning_effort: str = REASONING_EFFORT,
) -> AgentLoopResult:
    adapter = ChatLLMAdapter()
    ws = WorkingSet(question=question, user_id=user_id)
    cache = ToolCallCache()  # fresh per request -- freshness invariant (§5)
    system_prompt = build_constitution(user_id, build_tool_catalog(registry))
    transcript: list[dict[str, Any]] = []
    audit: list[ToolInvocationRecord] = []
    started = time.monotonic()
    llm_calls = 1

    front_door = await decompose(adapter, question, temperature=temperature, reasoning_effort=reasoning_effort)
    ws.sub_asks = front_door.sub_asks

    no_progress = 0
    answer_rejections = 0
    turn = 0
    for turn in range(1, MAX_TURNS + 1):
        if time.monotonic() - started > WALL_CLOCK_S:
            break

        raw_out: list[str] = []
        try:
            llm_calls += 1
            action = await adapter.complete_json(
                system_prompt=system_prompt,
                user_prompt=render_working_set(ws, turn, MAX_TURNS),
                temperature=temperature,
                thinking_enabled=True,
                reasoning_effort=reasoning_effort,
                raw_model_text_out=raw_out,
                timeout=TURN_TIMEOUT_S,
            )
        except LLMAdapterError as exc:
            transcript.append({"turn": turn, "error": exc.detail, "raw": (raw_out[-1] if raw_out else None)})
            ws.observe(f"LLM call failed ({exc.code}); emit ONE valid JSON object with tool_calls.")
            continue

        calls = action.get("tool_calls") or []
        transcript.append({"turn": turn, "thought": action.get("thought"), "calls": calls})
        terminal, progress, turn_audit = await _process_turn(ws, calls, registry, cache)
        audit.extend(turn_audit)
        rejected_this_turn = False
        for call in calls:  # surface any grounding rejection onto the transcript
            if call.get("_rejected_ungrounded"):
                transcript[-1].setdefault("rejected_ungrounded", call["_rejected_ungrounded"])
                rejected_this_turn = True

        if terminal is not None:
            if terminal.kind == "answered" and ws.sub_asks:
                # §9.2 completeness gate: a grounded answer must still ADDRESS
                # every sub-ask -- the structural fix the falsified prompt-level
                # rule could not deliver. Rejection resumes the loop with the
                # named gap (bounded continuation, §9.3).
                llm_calls += 1
                unaddressed = await completeness_gate(
                    adapter, question, ws.sub_asks, terminal.text,
                    temperature=temperature, reasoning_effort=reasoning_effort,
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
            return AgentLoopResult(
                terminal.kind, terminal.text, terminal.ungrounded, ws.sub_asks, ws.facts,
                audit, turn, llm_calls, time.monotonic() - started, transcript,
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
        # new successful fetch counts toward the cap that forces conclusion.
        no_progress = no_progress + 1 if progress == 0 else 0
        if no_progress >= NO_PROGRESS_LIMIT:
            ws.observe(f"no-progress limit reached ({NO_PROGRESS_LIMIT} turns); concluding.")
            break

    # Graceful degradation (§7): try one bounded compose from the facts already
    # grounded before punting -- the loop often HAS the answer, just ran out of
    # turns to say it.
    composed: str | None = None
    if ws.facts:
        llm_calls += 1
        composed = await _forced_compose(adapter, ws, temperature=temperature, reasoning_effort=reasoning_effort)
    if composed is not None:
        return AgentLoopResult(
            "answered", composed, [], ws.sub_asks, ws.facts,
            audit, turn, llm_calls, time.monotonic() - started, transcript,
        )
    return AgentLoopResult(
        "budget_exhausted", _punt_message(ws), [], ws.sub_asks, ws.facts,
        audit, turn, llm_calls, time.monotonic() - started, transcript,
    )


__all__ = ["AgentLoopResult", "run_agent_loop", "MAX_TURNS", "WALL_CLOCK_S", "NO_PROGRESS_LIMIT"]
