# Interpretation reasoning block implementation plan

**Status: implemented** -- full unit test suite green (43 new/extended tests
across `test_tool_round.py`, `test_interpretation_block.py`, and the
dispatch-routing test in `test_orchestrator_task_handler.py`), zero new
regressions in the full `services/ai` suite. Live-eval verification is still
outstanding. Second of five generic-path migrations (`retrieval` ✅
implemented → `interpretation` ✅ implemented → **`simulation_planning`** →
`composition` → the orchestrator's own `synthesis.py::compose_answer()`),
tackled one at a time per explicit instruction. This plan covers
**interpretation only**.

## Context

`retrieval` is done (`subagents/retrieval_block.py`,
`docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md`) — a bounded,
inlined tool-observation loop replacing `ReasoningBlock`+`tool_loop.py` for
that role. `interpretation` is next: same generic-path problem, but a
meaningfully different shape, because its one real tool
(`interpret_text`) is **itself already a dedicated `BaseReasoningBlock`**
(`tools/primitives/interpret_text.py::InterpretTextReasoningBlock`) — an LLM
call nested one level down. Confirmed mechanically: when
`InterpretationReasoningBlock` calls `interpret_text` through the tool
registry the same way `RetrievalReasoningBlock` calls `get_entity`, the call
`await descriptor.callable(tool_input)` is opaque — it happens to construct
and run a second, independent `BaseReasoningBlock` underneath, but the outer
block only ever sees a `ToolOutputEnvelope` back. No special-casing needed for
that nesting; it already works exactly like any other tool call.

The roster (`roles/roster.py:32-40`):
```python
"interpretation": RoleDefinition(
    name="interpretation",
    prompt_contract_name=INTERPRETATION_AGENT_V1,
    tool_grant_ceiling=("interpret_text", "get_entity", "search_knowledge"),
    default_reasoning_params=RoleReasoningDefaults(
        risk_level="medium", min_iterations=2, max_iterations=3, temperature=0.2, timeout=60.0
    ),
    guardrails=("Must cite the exact wiki page/section read.",),
),
```

`AGENT_VISION.md` §6.2 (line 200): *"Interpretation wants a stronger model
tuned for close reading, a schema-repair loop, and possibly a
compare-and-synthesize pattern when cross-checking more than one wiki
source."* Two concrete, load-bearing differences from retrieval this plan
must honor:

1. **`min_iterations=2`, not 1.** Under the old generic `ReasoningBlock`, this
   governed the adaptive-early-exit gate (`pass_index >= min_iterations`
   before an early finish is even considered). Retrieval's `min_iterations=1`
   let it finish in round 1 when nothing was ambiguous (`AGENT_VISION.md`
   §6.1's "cheap deterministic attempt first" philosophy). Interpretation's
   `min_iterations=2` encodes something structurally different: there is no
   "nothing to look up" case for this role — interpreting *requires* calling
   `interpret_text` (or resolving a source via `search_knowledge`/`get_entity`
   first) at least once. **A `status: "ready"` on round 1, before any tool has
   run, must never be honored.**
2. **`source_ref` becomes a required field, not optional.** Retrieval's
   `source_ref` is optional because not every fact has one citable page (a
   Mongo student-record fact has none). Interpretation's own guardrail —
   *"Must cite the exact wiki page/section read"* — is absolute; there is no
   legitimate interpretation result without a citation. Making `source_ref`
   `required` in the output schema turns this from a prompt-level guardrail
   into a structural one: if no source was ever successfully interpreted, the
   finalize step **cannot** produce a schema-valid result, and correctly
   fails closed rather than needing separate logic to detect a missing
   citation.

## Why a dedicated block (recap)

Same extension point as `RetrievalReasoningBlock`,
`CalculationValidationReasoningBlock`, `RequestUnderstandingReasoningBlock`:
`BaseReasoningBlock` (`reasoning_blocks/base.py:87`) needs only
`_run_internal`; a block needing a `tool_registry` takes it as its own
constructor kwarg (`base.py:102-106`'s documented extension note).
`InterpretationReasoningBlock` follows the identical shape
`RetrievalReasoningBlock` already established: one bounded round loop,
inlined tool execution, no `tool_loop.py` involvement.

## Shared refactor: extract the tool-round-execution helper

`RetrievalReasoningBlock._run_internal` (`retrieval_block.py:195-246`) already
contains ~35 lines of inlined tool-round execution: grant check → registry
lookup → `descriptor.input_model(**arguments)` → `await
descriptor.callable(tool_input)` → audit-record append → merge into
`tool_results_so_far` keyed by `f"{tool_name}:{json.dumps(arguments,
sort_keys=True, default=str)}"`. `InterpretationReasoningBlock` needs this
*exact same* logic (only its own tool grant differs). Per this repo's own
DRY rule (`coding-style.md`: "introduce abstractions when repetition is real,
not speculative") — this is now real, demonstrated repetition across two
concrete call sites, not a speculative one.

New module: `app/agent_core/subagents/tool_round.py`:
```python
async def execute_tool_round(
    *,
    tool_requests: list[dict[str, Any]],
    tool_grant: list[str],
    tool_registry: ToolRegistry,
    tool_results_so_far: dict[str, Any],
) -> tuple[dict[str, Any], list[ToolInvocationRecord]]:
    """Returns a NEW merged results dict (never mutates the input one, per
    this repo's immutability rule) plus this round's new audit records.
    Never raises -- ungranted/unregistered/raising calls are audited
    output_ok=False and simply omitted from the merged dict."""
```
Behavior ported verbatim from `retrieval_block.py`'s inlined version (grant
check, registry lookup, try/except execute, the `tool_name:json(args)` keying
that fixes the real "Retrieval convergence failure" `tool_loop.py:56-63`
documents). `RetrievalReasoningBlock` is refactored to call this helper
instead of its own inlined copy (behavior-preserving; its existing test suite
must still pass unchanged) — done as part of *this* migration's rollout, not
retroactively re-litigated as a separate task.

## Control flow

```
round = 0
tool_results_so_far = {}
tool_audit_trail = []
_MIN_ROUNDS = 2   # roster's min_iterations -- never honor "ready" before this
_MAX_ROUNDS = 3   # roster's max_iterations

loop:
  round += 1
  is_final_round = (round == _MAX_ROUNDS)
  call LLM with: objective, task_context, tool_results_so_far, available tools
                 (from tool_grant), and:
                 - if round < _MIN_ROUNDS: "You must call at least one tool
                   before finalizing; a 'ready' status now will be ignored."
                 - if is_final_round: "NO MORE TOOL CALLS. Finalize with what
                   you have."
  parse response: {status: "ready" | "need_tools", tool_requests: [...],
                    result: {...} <- only when status == "ready"}

  if status == "need_tools" and not is_final_round:
      tool_results_so_far, new_records = await execute_tool_round(
          tool_requests=payload.tool_requests, tool_grant=block_input.tool_grant,
          tool_registry=self._tool_registry, tool_results_so_far=tool_results_so_far,
      )
      tool_audit_trail += new_records
      continue

  if status == "ready" and round < _MIN_ROUNDS:
      # Premature finalize attempt -- never honored. No tools executed this
      # round; just advance (bounded by _MAX_ROUNDS regardless, so no
      # infinite-loop risk even if the model keeps insisting).
      continue

  # status == "ready" (round >= _MIN_ROUNDS), OR this was the forced-finalize
  # final round
  if result is None:
      -> fail closed (round_budget_exhausted_no_result / status_ready_but_no_result)
  normalize + validate against the real `interpretation_agent_output_v1` schema
  if invalid: run the base class's generic `_repair_schema` (same reuse choice
              `RequestUnderstandingReasoningBlock` and `RetrievalReasoningBlock`
              both already made -- no bespoke semantic repair loop needed)
  if still invalid: fail closed
      -- NOTE: because `source_ref` is a *required* schema field, "no source
         was ever successfully interpreted" naturally fails here, structurally
         enforcing "never assert an uncited answer" without any separate
         detection logic.
  return completed, schema_valid=True, result=normalized, tool_audit_trail, rounds_used
```

## New module: `app/agent_core/subagents/interpretation_block.py`

Mirrors `retrieval_block.py`'s layout, using the new shared
`execute_tool_round` helper instead of an inlined copy:

- `_INTERPRETATION_ROUND_V1` — one prompt contract (same reasoning as
  retrieval: decide-or-finalize combined in a single per-round call; schema
  repair reuses the base class's generic `_repair_schema`). `role_prompt`
  adapts `roles/prompts.py::_interpretation_agent_contract()`'s existing text
  verbatim (same grounding block, same "read authoritative wiki text ...
  cite the exact page/section ... return cannot determine rather than
  guess" framing). `instructions` carry forward, essentially unchanged, the
  existing contract's 4 instructions (`prompts.py:76-83`) — including the
  gap #5 unverifiable-temporary-exception guardrail, verbatim — plus the new
  per-round response-shape instruction and the `_MIN_ROUNDS`/forced-finalize
  framing described above.
- `_INTERPRETATION_OUTPUT_SCHEMA_NAME = "interpretation_agent_output_v1"`
  (already declared, dead, in `roles/prompts.py:73` — same "finally make it
  real" move retrieval made for its own output schema name) and
  `_INTERPRETATION_OUTPUT_SCHEMA`:
  ```json
  {
    "type": "object",
    "properties": {
      "certainty_basis": {"type": "string", "enum": ["official_record", "wiki_derived", "predicted_pattern", "llm_interpretation", "hypothetical_simulation"]},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "source_ref": {
        "type": "object",
        "properties": {"page": {"type": "string"}, "section": {"type": ["string", "null"]}, "reasoning_path": {"type": ["string", "null"]}},
        "required": ["page", "section"]
      },
      "assumptions": {"type": "array", "items": {"type": "string"}},
      "answer": {"type": "string"}
    },
    "required": ["certainty_basis", "confidence", "source_ref", "answer"]
  }
  ```
  `answer` (plain string, not a speculative structured "rule" dict) mirrors
  `interpret_text`'s own tool-level output shape (`{answer, citedSection}`)
  directly — the role's job is fundamentally "resolve the right source, call
  `interpret_text`, surface its answer with citation," so the role-level
  schema stays faithful to that rather than inventing new structure nothing
  demonstrates a need for yet. `source_ref` is **required** (see Context,
  point 2) — the one deliberate schema difference from retrieval's own
  (optional) `source_ref`.
- **`warnings` surfaced structurally, not just as a prompt hope.** The
  per-round response schema adds a `"warnings": {"type": "array", "items":
  {"type": "string"}}` field (retrieval's own round schema has none — it
  doesn't need one). On finalize, these get threaded into
  `_InterpretationBlockOutput.warnings` (the field `BaseReasoningBlockOutput`
  already provides). This is what makes the gap #5 guardrail ("flag
  unverifiable absence of a temporary exception as a warning, never report it
  confirmed") mechanically real instead of prompt-text-only, per the open
  gaps doc's own stated concern that it "is not yet mechanically enforced
  anywhere."
- `_MIN_ROUNDS = 2`, `_MAX_ROUNDS = 3` (module constants, matching the
  roster's own `min_iterations`/`max_iterations` for this role — same
  "roster value becomes a fixed block constant" precedent retrieval set with
  its own `_MAX_ROUNDS = 3`).
- `_InterpretationBlockInput(BaseReasoningBlockInput)`: adds `tool_grant:
  list[str]` (same shape as `_RetrievalBlockInput`).
- `_InterpretationBlockOutput(BaseReasoningBlockOutput)`: adds
  `tool_audit_trail: list[ToolInvocationRecord]`, `rounds_used: int` (same
  shape as `_RetrievalBlockOutput`).
- `class InterpretationReasoningBlock(BaseReasoningBlock)`: constructor takes
  `tool_registry: ToolRegistry` as an extra kwarg, stores as
  `self._tool_registry` (identical shape to both existing dedicated blocks
  that need one). `_run_internal` implements the control flow above, calling
  `execute_tool_round` from the new shared module instead of inlining it.
- `_interpretation_failed_output(self, *, reason, tool_audit_trail,
  rounds_used)` — overrides `_failed_output` (same pattern all 3 existing
  dedicated blocks with extra required Output fields already follow).
- `async def run_interpretation_subagent(*, context_package, tool_registry,
  llm_adapter, block_id) -> SubagentResult` — same signature shape as
  `run_retrieval_subagent`/`run_calculation_validation_subagent`: builds
  `_InterpretationBlockInput` directly (bypassing whatever schema
  `context_package` carries, using the real `_INTERPRETATION_OUTPUT_SCHEMA`
  instead), runs the block, maps `status`: `"completed"` → `"succeeded"`,
  else `"failed"` (no `"partial"` produced from this path, matching both
  existing dedicated-block wrappers' own precedent).

## Dispatch integration: `task_handler.py`

One more `if` branch in `_dispatch_single_specialist`
(`orchestrator/task_handler.py:141-155`), same shape as the existing two:

```python
if role.name == "calculation_validation":
    return await run_calculation_validation_subagent(...)
if role.name == "retrieval":
    return await run_retrieval_subagent(...)
if role.name == "interpretation":
    return await run_interpretation_subagent(
        context_package=context_package, tool_registry=tool_registry,
        llm_adapter=llm_adapter, block_id=block_id,
    )
return await run_subagent(...)
```

No roster change needed — `roster.py`'s `interpretation` `RoleDefinition`
keeps its existing `prompt_contract_name=INTERPRETATION_AGENT_V1`, which goes
unused for dispatch purposes, the same already-accepted state both
`calculation_validation` and `retrieval` are already in.

## New contract doc: `docs/agent/INTERPRETATION_OUTPUT_CONTRACT.md`

Same pairing convention as `RETRIEVAL_OUTPUT_CONTRACT.md`/
`DETERMINISTIC_RULE_CONTRACT.md`: documents `interpretation_agent_output_v1`'s
shape, the required-`source_ref` design rationale, the fail-closed error
vocabulary, and a worked example (e.g. interpreting the retake-limit policy
for a specific course).

## Explicitly out of scope for v1

- **Compare-and-synthesize across multiple wiki sources.** `AGENT_VISION.md`
  §6.2 names this as a "possibly" — no test, gap doc, or worked example
  demonstrates a concrete current need to interpret 2+ sources and reconcile
  conflicting answers in one step. v1 supports calling `interpret_text`
  against more than one source **across multiple rounds** (the loop already
  allows this — nothing prevents round 2 targeting a different `source` than
  round 1 if the first didn't pan out), but no structured "compare N sources,
  flag disagreement" feature. Revisit if a real case demonstrates the need
  (same YAGNI posture `TOOL_PRIMITIVES_OPEN_GAPS.md` #5 itself explicitly
  models).
- **A `policy_exception` entity type** or any other new primitive to make
  "no unusual temporary exception applies" actually verifiable — gap #5's own
  explicit conclusion is to flag it as a warning, not build new
  infrastructure speculatively. Unchanged by this plan.
- **`step_prep.py`'s hardcoded `output_schema={"type": "object"}`** — left
  untouched, same precedent both existing dedicated blocks already set.
- **A configurable round budget per call** — `_MIN_ROUNDS`/`_MAX_ROUNDS` are
  fixed module constants for v1, matching the roster defaults; no
  demonstrated need for per-call tuning yet.

## Test plan

New `services/ai/tests/agent_core/test_interpretation_block.py`, same
convention as `test_retrieval_block.py`/`test_calculation_validation_block.py`
(`fake_llm_adapter_factory`, a counting wrapper around
`build_default_tool_registry()`, everything exercised through the public
`run_interpretation_subagent()` entry point):

- Round-1 `status: "ready"` is **not honored** even with a well-formed
  `result` — round advances instead (regression guard for the
  `_MIN_ROUNDS` behavior that structurally differs from retrieval).
- Happy path: round 1 calls `interpret_text` (or `search_knowledge` then
  `interpret_text` across 2 rounds), round 2/3 finalizes with a schema-valid,
  cited result.
- A tool request naming a tool not in `tool_grant` is skipped
  (`output_ok=False`) without aborting the round — other requests in the same
  round still execute (via the new shared `execute_tool_round` helper).
- `interpret_text` itself returning `ok=False` (its own internal
  `cannot_determine`) is handled as a normal failed-but-executed tool call —
  audited, not merged into `tool_results_so_far` — same convention as any
  other tool.
- **No source ever successfully interpreted** by the final round → finalize
  fails schema validation (missing required `source_ref`) → fails closed,
  never fabricates an uncited answer. This is the key regression guard for
  the required-`source_ref` design decision.
- Gap #5 case: a round's response includes a `warnings` entry about an
  unverifiable temporary exception → surfaces in the final
  `SubagentResult.warnings`, not silently dropped.
- Malformed `result` on finalize triggers the base class's generic
  `_repair_schema` and recovers; repair-exhausted fails closed.
- `SubagentResult` shape parity test (same as both existing dedicated
  blocks' own final test).

New `services/ai/tests/agent_core/test_tool_round.py` for the extracted
`execute_tool_round` helper directly: grant check, registry-not-found,
raising tool, the `tool_name:json(args)` anti-clobber keying regression guard
(ported from `test_retrieval_block.py`'s own version of this test), and
confirms it returns a **new** dict rather than mutating the one passed in
(per this repo's immutability rule).

Extend `test_retrieval_block.py`/`retrieval_block.py` itself: refactor its
inlined tool-round logic to call the new shared helper; its existing test
suite must pass **unchanged** (behavior-preserving refactor, not a rewrite).

Extend `test_orchestrator_task_handler.py` with one new test mirroring the
existing `retrieval`/`calculation_validation` dispatch-routing tests, for the
new `interpretation` branch.

## Rollout / verification plan

1. Extract `tool_round.py` + its test; refactor `retrieval_block.py` to use
   it; confirm retrieval's existing test suite is unaffected.
2. Implement `interpretation_block.py` + its test file.
3. Wire the `task_handler.py` dispatch branch + its test.
4. Write `docs/agent/INTERPRETATION_OUTPUT_CONTRACT.md`.
5. Run the full `services/ai` regression suite (`pytest services/ai/tests/agent_core/
   -m "not live"`) — confirm zero new failures beyond the 2 known
   pre-existing, unrelated `test_get_policy_answer.py` ones.
6. Commit in discrete batches (shared helper + retrieval refactor, then
   interpretation block + tests, then dispatch wiring + its test, then docs).
7. Live-eval verification deferred until explicitly requested, same policy
   held for both prior migrations.

## Open questions to resolve at implementation time

- **Premature-"ready" handling** (proposed: silently ignore and advance the
  round, as designed above, no error surfaced to the model beyond the
  system-prompt instruction already telling it not to). Alternative: treat an
  early "ready" as a schema/contract violation worth logging a warning about
  even though it's not honored. Proposed default keeps it quiet since the
  round budget bounds it regardless.
- **Whether `execute_tool_round`'s extraction should happen in this
  migration or be deferred to a standalone refactor commit** (proposed: do it
  as step 1 of this migration's rollout, since interpretation is what makes
  the duplication real and demonstrated — waiting further would mean writing
  the duplicate a second time first).
- **Whether to allow interpretation's final round to fall back to a
  low-confidence "cannot_determine"-shaped answer without a citation**
  (proposed: no — the required `source_ref` schema field should make this
  structurally impossible, which is the intended behavior per the "return
  cannot_determine rather than guess" guardrail; a step that never got a
  cited answer should surface as `status="failed"` and let the orchestrator's
  existing nested-replanning handle it, not synthesize a fake low-confidence
  answer).
