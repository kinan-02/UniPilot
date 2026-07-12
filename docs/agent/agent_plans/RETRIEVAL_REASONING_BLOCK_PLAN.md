# Retrieval reasoning block implementation plan

**Status: planned, not yet implemented.** First of five generic-path migrations
(`retrieval` → `interpretation` → `simulation_planning` → `composition` → the
orchestrator's own `synthesis.py::compose_answer()`), tackled one at a time per
explicit instruction. This plan covers **retrieval only**.

## Context

Of the 5 roster roles, only `calculation_validation` has its own dedicated
`BaseReasoningBlock` subclass today (`subagents/calculation_validation_block.py`).
The other 4 — `retrieval`, `interpretation`, `simulation_planning`, `composition`
— plus the orchestrator's terminal `synthesis.py::compose_answer()` all still
dispatch through the old generic path: `subagents/run.py::run_subagent()` builds
a `reasoning/reasoning_block.py::ReasoningBlock`, runs it (an internal 1-3-pass
loop per `role.default_reasoning_params`), and if a pass reports `needs_tool`,
hands off to `subagents/tool_loop.py::run_subagent_tool_loop()` for up to 2 more
outer rounds — each outer round re-invoking the *entire* multi-pass
`ReasoningBlock.run()` again. Worst case today: up to 3 × 2 = 6 LLM calls for one
retrieval step, across two independently-configured, nested loops.

Retrieval is the right one to do first: `docs/agent/AGENT_VISION.md` §6.2 (line
199) explicitly calls it out — *"Retrieval wants a cheap, fast, low-temperature
model with a tight iteration cap — a bounded tool-observation loop"* — a
one-loop shape, not two nested ones. It's also the role with the most
tool-calling surface (3 tools: `get_entity`, `search_knowledge`,
`traverse_relationship`, vs. calculation_validation's 1), so it's a meaningfully
different reference shape from the existing `CalculationValidationReasoningBlock`
(single deterministic tool, zero rounds) — good coverage before templating the
remaining 3 migrations off of it.

A second, concrete win: the roster's `RETRIEVAL_AGENT_V1` contract
(`roles/prompts.py:33-59`) already declares `output_schema_name=
"retrieval_agent_output_v1"` — but no schema is actually registered under that
name, and at runtime `step_prep.py` hardcodes `output_schema={"type": "object"}`
for every role regardless of name (`orchestrator/step_prep.py:109-121` and its
fallback at `:48-64`). So today, retrieval's result is **never actually
schema-validated** — any dict passes. This plan finally makes
`retrieval_agent_output_v1` a real, enforced schema, following the exact
precedent `calculation_validation_block.py` already set: a dedicated block
builds its own `Input` directly and supplies its own real `output_schema`,
bypassing whatever (currently vestigial) schema `context_package` carries.

## Why a dedicated block (recap)

Same extension point as the 3 existing dedicated blocks
(`RequestUnderstandingReasoningBlock`, `ComposeAnswerReasoningBlock`,
`CalculationValidationReasoningBlock`): `BaseReasoningBlock`
(`reasoning_blocks/base.py:87`) requires only `_run_internal(block_input,
telemetry) -> Output`; everything else (`_invoke_llm`, `_validate_schema`,
`_normalize_result`, `_repair_schema`, `_emit_debug_observer`, `_trace`, and
`run()`'s "never raises" safety net) is a shared, composable helper with no
prescribed call order. A block needing a `tool_registry` (like
`CalculationValidationReasoningBlock` does) takes it as its own constructor
kwarg per the base class's own documented extension note
(`base.py:102-106`): *"A future shape that genuinely needs more than one [extra
dependency] ... accepts extras in its own constructor ... the base doesn't
pre-anticipate a shape nothing concrete needs yet."* `RetrievalReasoningBlock`
follows the same pattern.

The key structural difference from `CalculationValidationReasoningBlock`:
calc-validation's tool call is a single, deterministic, pre-validated
expression — zero rounds needed once the tree is structurally valid. Retrieval's
tool calls are genuinely exploratory (an ambiguous search may need a second,
refined query; a `get_entity` call may 404 and need a different id) — so
retrieval needs its own **bounded round loop**, inlined into the block itself
instead of split across `ReasoningBlock`'s internal passes + `tool_loop.py`'s
outer rounds.

## Control flow

One unified loop, `_MAX_ROUNDS = 3` (module constant — matches the roster's
current `max_iterations=3` for retrieval, `roster.py:28`, now a single round
budget instead of two independently-configured nested ones):

```
round = 0
tool_results_so_far = {}      # keyed "tool_name:json(sorted args)" -- see below
tool_audit_trail = []

loop:
  round += 1
  is_final_round = (round == _MAX_ROUNDS)
  call LLM with: objective, task_context, tool_results_so_far so far,
                 available tools (from tool_grant), and -- only on the final
                 round -- an explicit "no more tool calls; finalize with what
                 you have" instruction.
  parse response: {status: "ready" | "need_tools", tool_requests: [...],
                    result: {...} <- only when status == "ready"}

  if status == "need_tools" and not is_final_round:
      for each tool_request:
        - not in tool_grant?        -> audit output_ok=False, skip (never abort the round)
        - not registered?           -> audit output_ok=False, skip
        - descriptor.callable raises? -> audit output_ok=False, skip
        - else: audit output_ok=envelope.ok;
                 if envelope.ok: tool_results_so_far[key] = envelope.data
      continue to next round with the updated tool_results_so_far

  # status == "ready", OR this was the forced-finalize final round
  if result is None:
      -> fail (see "round-budget-exhausted" below)
  normalize + validate result against the real `retrieval_agent_output_v1` schema
  if invalid: run the base class's generic `_repair_schema` (reuse, not a bespoke
              loop -- same choice `RequestUnderstandingReasoningBlock` made,
              since there's no closed structural vocabulary to validate against
              like calc-validation's expression tree)
  if still invalid: fail
  return completed, schema_valid=True, result=normalized, tool_audit_trail, rounds_used
```

Two behaviors carried over verbatim from `tool_loop.py` because they were each
added to fix a real bug, and dropping them would reintroduce it:

1. **Keying by `f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"`**,
   not by tool name alone (`tool_loop.py:56-63` — inline comment cites a real
   "Retrieval convergence failure" this was found from: calling `get_entity`
   twice with different arguments in one step must not clobber the first
   result).
2. **A tool call that's ungranted / unregistered / raises never aborts the
   round** — it's recorded `output_ok=False` in the audit trail and simply
   omitted from `tool_results_so_far`; every other request in the same round
   still executes and still gets fed forward.

Two deliberate simplifications vs. the generic path:

- **Two statuses, not three.** The generic per-pass vocabulary is `ok |
  needs_tool | needs_more_context` (`reasoning/schemas.py:21`). Retrieval drops
  `needs_more_context` as a distinct status: anything retrieval can't pin down
  is itself expressible as a low-confidence, assumption-flagged `result`
  (`facts={}`, `assumptions=["could not determine X"]`), which the
  round-budget-exhaustion path already produces gracefully. No case was found
  in the existing tests or `TOOL_PRIMITIVES_OPEN_GAPS.md` that needs a third,
  separately-handled status for retrieval specifically.
- **No internal-pass vs. outer-round split.** One loop, one budget
  (`_MAX_ROUNDS`), one LLM call per round (decide-and-maybe-finalize combined,
  same shape the generic path's single pass already used) instead of
  `ReasoningBlock`'s 1-3 passes multiplied by `tool_loop.py`'s up-to-2 rounds.

## New module: `app/agent_core/subagents/retrieval_block.py`

Mirrors `calculation_validation_block.py`'s layout:

- `_RETRIEVAL_ROUND_V1` — **one** prompt contract (not draft+repair like
  calc-validation; retrieval's single per-round call already covers
  decide-or-finalize, and schema repair reuses the base class's generic
  `_repair_schema` rather than a bespoke one, same choice
  `RequestUnderstandingReasoningBlock` made). `role_prompt` adapts the existing
  text from `roles/prompts.py::_retrieval_agent_contract()` (same grounding
  block, same "resolve and fetch facts ... never commentary" framing);
  `instructions` add the per-round response shape and the forced-finalize
  framing for the last round.
- `_RETRIEVAL_OUTPUT_SCHEMA_NAME = "retrieval_agent_output_v1"` (this exact
  name already exists in `roles/prompts.py:47` — reused, finally backed by a
  real schema) and `_RETRIEVAL_OUTPUT_SCHEMA`:
  ```json
  {
    "type": "object",
    "properties": {
      "certainty_basis": {"type": "string", "enum": ["official_record", "wiki_derived", "predicted_pattern", "llm_interpretation", "hypothetical_simulation"]},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "source_ref": {"type": ["object", "null"], "properties": {"page": {"type": "string"}, "section": {"type": ["string", "null"]}, "reasoning_path": {"type": ["string", "null"]}}, "required": ["page"]},
      "assumptions": {"type": "array", "items": {"type": "string"}},
      "facts": {"type": "object"}
    },
    "required": ["certainty_basis", "confidence", "facts"]
  }
  ```
  (matches `CertaintyTag`/`SourceRef`, `planning/state.py:17-37`, and the soft
  convention `build_subagent_result` already reads out of a free-form `result`
  dict today — this schema just makes it a real, enforced contract instead of
  an unenforced convention.)
- `_MAX_ROUNDS = 3`.
- `_RetrievalBlockInput(BaseReasoningBlockInput)`: adds `tool_grant:
  list[str]` (no `facts`-by-ref dict like calc-validation needs — retrieval has
  no expression-tree ref lookups, just free-form `task_context`, same
  convention already used).
- `_RetrievalBlockOutput(BaseReasoningBlockOutput)`: adds `tool_audit_trail:
  list[ToolInvocationRecord]`, `rounds_used: int`.
- `class RetrievalReasoningBlock(BaseReasoningBlock)`: constructor takes
  `tool_registry: ToolRegistry` as an extra kwarg, stores as `self._tool_registry`
  (identical shape to `CalculationValidationReasoningBlock.__init__`,
  `calculation_validation_block.py:197-208`). `_run_internal` implements the
  control flow above; tool grant-check / registry-lookup / execute is inlined
  directly (no `tool_loop.py` involvement at all, same as calc-validation) but
  runs a `for` loop over potentially multiple `tool_requests` per round, and
  loops itself up to `_MAX_ROUNDS` (calc-validation never loops — its whole
  point is exactly one deterministic call).
- `_retrieval_failed_output(self, *, reason, tool_audit_trail, rounds_used)` —
  overrides `_failed_output` per `base.py`'s own note that subclasses with
  extra required Output fields must override it (same as both existing
  dedicated blocks already do).
- `async def run_retrieval_subagent(*, context_package, tool_registry,
  llm_adapter, block_id) -> SubagentResult` — same signature shape as
  `run_calculation_validation_subagent` (`calculation_validation_block.py:323`):
  builds `_RetrievalBlockInput` directly from `context_package` (ignoring its
  `output_schema`/`output_schema_name`, using the real
  `_RETRIEVAL_OUTPUT_SCHEMA` instead — same bypass precedent calc-validation
  already established), runs the block, maps `status`: `"completed"` →
  `"succeeded"`, `"partial"` → `"partial"`, else `"failed"`.

## Dispatch integration: `task_handler.py`

One more `if` branch in `_dispatch_single_specialist`
(`orchestrator/task_handler.py:140-146`), same shape as the existing
`calculation_validation` branch:

```python
if role.name == "calculation_validation":
    return await run_calculation_validation_subagent(...)
if role.name == "retrieval":
    return await run_retrieval_subagent(
        context_package=context_package, tool_registry=tool_registry,
        llm_adapter=llm_adapter, block_id=block_id,
    )
return await run_subagent(...)
```

No roster change needed: `roster.py`'s `retrieval` `RoleDefinition` keeps its
existing `prompt_contract_name=RETRIEVAL_AGENT_V1` field, which simply goes
unused for dispatch purposes — the exact same already-accepted state
`calculation_validation`'s roster entry is in today (its
`prompt_contract_name=CALCULATION_VALIDATION_AGENT_V1` is likewise vestigial
post-dispatch-branch). `RoleDefinition.tool_grant_ceiling` is unaffected;
`context_package.tool_grant` (already resolved per-step, possibly narrower than
the ceiling per `AGENT_VISION.md` §7.1) is what actually gets passed through,
same as calc-validation's own wrapper does.

## New contract doc: `docs/agent/RETRIEVAL_OUTPUT_CONTRACT.md`

Follows the same pairing convention `DETERMINISTIC_RULE_CONTRACT.md` already
established for `apply_deterministic_rule` (a `*_PLAN.md` implementation plan
paired with a `*_CONTRACT.md` producer/consumer doc, kept up to date
independently): documents `retrieval_agent_output_v1`'s shape (the schema
above), the fail-closed error vocabulary (`result_missing_on_finalize`,
`schema_validation_failed`), and a worked example. Short — one schema, not a
multi-variant rule table like the deterministic-rule contract.

## Explicitly out of scope for v1

- **`step_prep.py`'s hardcoded `output_schema={"type": "object"}`** — left
  untouched, same as calc-validation's own precedent; the dedicated wrapper
  simply builds its own `Input` with the real schema, bypassing whatever
  `context_package` carries. No demonstrated need to make `step_prep.py`
  role-aware yet.
- **Cross-step tool-call de-duplication** (unrelated, pre-existing gap, out of
  scope per earlier session prioritization).
- **A configurable round budget per call** (e.g. a tighter single-tool grant
  per `AGENT_VISION.md` §7.1's own example) — `_MAX_ROUNDS = 3` is a fixed
  module constant for v1, matching the current roster default; nothing today
  demonstrates a need for per-call tuning.

## Test plan

New `services/ai/tests/agent_core/test_retrieval_block.py`, same convention as
`test_calculation_validation_block.py` (`fake_llm_adapter_factory`, a
`_CountingToolRegistry`-style wrapper around `build_default_tool_registry()`,
everything exercised through the public `run_retrieval_subagent()` entry
point):

- Round-1 `status: "ready"` with no tool calls at all completes immediately
  (the "nothing ambiguous, no forced iteration" case `AGENT_VISION.md` §6.1
  describes).
- One round of tool calls (`get_entity` succeeds) then `status: "ready"` on
  round 2 — happy path.
- **Regression guard**: `get_entity` called twice in the same round with two
  different `entity_id` arguments — both results present and distinct in
  `tool_results_so_far` on the next round (the exact convergence bug
  `tool_loop.py:56-63`'s comment documents).
- A tool request naming a tool not in `tool_grant` is skipped (audited
  `output_ok=False`) without aborting the round — other granted requests in
  the same round still execute.
- A tool call that raises is skipped (audited `output_ok=False`), round
  continues.
- `entity_not_found` / zero-match `search_knowledge` handled as a legitimate,
  `ok=True` fact, not a hard failure — final result reflects it via
  `assumptions`, not a crash.
- Round budget exhausted (`_MAX_ROUNDS` rounds all `need_tools`) → forced
  finalize on the last round; if the model still returns no `result`, fails
  closed with `rounds_used == _MAX_ROUNDS` and a `round_budget_exhausted`-style
  warning.
- Malformed `result` on finalize triggers the base class's generic
  `_repair_schema` and recovers.
- Repair exhausted (still invalid after base repair attempts) fails closed.
- `SubagentResult` shape parity test (same as calc-validation's own final
  test) — confirms `task_handler.py`'s downstream handling needs zero changes.

Extend `test_orchestrator_task_handler.py` with one new test mirroring
`test_dispatch_single_specialist_routes_calculation_validation_role_to_dedicated_block`
for the new `retrieval` branch.

## Rollout / verification plan

1. Implement `retrieval_block.py` + its test file.
2. Wire the `task_handler.py` dispatch branch + its test.
3. Write `docs/agent/RETRIEVAL_OUTPUT_CONTRACT.md`.
4. Run the full `services/ai` regression suite (`pytest services/ai/tests/agent_core/
   -m "not live"`) — confirm zero new failures beyond the pre-existing,
   unrelated `test_get_policy_answer.py` ones already known from this session's
   baseline.
5. Commit in discrete batches (block + tests, then dispatch wiring + its test,
   then docs), matching this session's established convention.
6. Live-eval verification (real LLM, real seeded student) deferred until
   explicitly requested, same policy this session has held throughout for
   calculation_validation.

## Open questions to resolve at implementation time

- **Round-budget-exhaustion behavior** (proposed: forced-finalize on the last
  round, as designed above — never a bare hard-fail purely from running out of
  rounds, since partial facts already gathered are still worth returning at
  lower confidence). Alternative: skip the forced-finalize call and just return
  `"partial"` with whatever facts were gathered, no extra LLM call. Proposed
  default keeps one graceful-degradation call; flag if you'd rather keep it
  simpler/cheaper.
- **Dropping `needs_more_context` as a distinct status** (proposed: yes, per
  the "Two simplifications" section above) — flag if a concrete case needs it
  reinstated.
- **Whether to write `RETRIEVAL_OUTPUT_CONTRACT.md` now or defer it** (proposed:
  write it now, since it's the doc that makes `retrieval_agent_output_v1`
  official — small, one-schema doc, low cost to include).
