# Simulation/Planning reasoning block implementation plan

**Status: implemented** -- full unit test suite green (29 new/extended tests
across `test_simulation_planning_block.py` and the dispatch-routing test in
`test_orchestrator_task_handler.py`), zero new regressions in the full
`services/ai` suite. Live-eval verification is still outstanding. One test
implementation note: the plan's assumption that `search_over_state` could be
exercised for real (no external infra, like `mutate_state`) turned out
false -- it needs a configured academic graph engine even for trivial cases,
so it's stubbed in tests the same way `interpret_text`/`get_entity` were for
prior migrations; `mutate_state` alone is used for real. Third of five
generic-path migrations (`retrieval` ✅ implemented → `interpretation` ✅
implemented → `simulation_planning` ✅ implemented → **`composition`** → the
orchestrator's own `synthesis.py::compose_answer()`), tackled one at a time
per explicit instruction. This plan covers **simulation_planning only**.

## Context

The roster (`roles/roster.py:50-58`):
```python
"simulation_planning": RoleDefinition(
    name="simulation_planning",
    prompt_contract_name=SIMULATION_PLANNING_AGENT_V1,
    tool_grant_ceiling=("mutate_state", "search_over_state"),
    default_reasoning_params=RoleReasoningDefaults(
        risk_level="medium", min_iterations=2, max_iterations=4, temperature=0.2, timeout=60.0
    ),
    guardrails=("Never present a simulated outcome as an official record.",),
),
```

Unlike `interpretation`, **neither granted tool is LLM-backed.**
`mutate_state` (a pure, deterministic, in-memory transform — never a real
database write) and `search_over_state` (a deterministic greedy/topological
scheduler composing already-tested primitives: `get_entity`,
`traverse_relationship`, `extract_temporal_pattern`,
`AcademicGraphEngine.evaluate_eligibility`) are both `side_effect="compute"`,
zero nested reasoning-block calls. This makes `SimulationPlanningReasoningBlock`
structurally **closer to `RetrievalReasoningBlock`'s shape than
`InterpretationReasoningBlock`'s** — no nested-LLM-dispatch concern, just a
flat bounded tool-round loop using the same shared
`subagents/tool_round.py::execute_tool_round` helper. The "reasoning" this
role needs lives entirely in the *outer* LLM turn: deciding what
`change`/`constraints`/`objective` to construct, and whether to retry after a
failed candidate.

`AGENT_VISION.md` §6.2 (line 202): *"Simulation/Planning wants a larger
iteration budget, since constraint search often needs a reflect-and-revise
pass when the first candidate fails a constraint."* — the largest iteration
budget of any role (`max_iterations=4`, vs. retrieval's 3 and
interpretation's 3). The existing prompt contract's third instruction
(`prompts.py:129-155`) is the direct prompt-level expression of this: *"If
the first candidate fails a constraint, revise and retry before giving up."*
Mechanically, this needs **no new code-level machinery beyond what the round
loop already provides** — "call tools, see results, decide to try a
different `change`/`constraints` instead of finalizing" is exactly the same
shape as retrieval's "ambiguous search → try again," just with different
round budgets and a stricter output schema (below).

**A real doc/code drift, surfaced during research, explicitly NOT addressed
by this plan:** `docs/agent/HIGHER_LEVEL_TOOLS.md`'s "Architecture decision:
no role-private tools" section states as already-done that
"Simulation/Planning's tool_grant_ceiling gains `simulate_course_disruption`/
`audit_graduation_progress`" (the flagship composite tools built on top of
`mutate_state`/`search_over_state`). **The live `roster.py` does not reflect
this** — `simulation_planning`'s ceiling is still exactly
`("mutate_state", "search_over_state")`, no composites. Widening the ceiling
is a distinct behavioral change (more capability granted to the role) from
"give this role its own reasoning-block architecture" (what was actually
asked), so this plan explicitly does **not** touch `tool_grant_ceiling` —
see "Explicitly out of scope" and "Open questions" below.

## Why a dedicated block (recap)

Same extension point as `RetrievalReasoningBlock`/
`InterpretationReasoningBlock`/`CalculationValidationReasoningBlock`:
`BaseReasoningBlock` (`reasoning_blocks/base.py:87`) needs only
`_run_internal`; a block needing a `tool_registry` takes it as its own
constructor kwarg. `SimulationPlanningReasoningBlock` reuses the shared
`execute_tool_round` helper (`subagents/tool_round.py`) exactly as
`RetrievalReasoningBlock` does — no third copy of the grant-check/registry-
lookup/execute logic.

## Control flow

Structurally identical to `RetrievalReasoningBlock`'s loop shape (not
`InterpretationReasoningBlock`'s, since there's no nested-LLM tool to worry
about), with `interpretation`'s `_MIN_ROUNDS` enforcement carried over --
there is no "nothing to simulate" case for this role either; producing a
projection always requires at least one tool call.

```
round = 0
tool_results_so_far = {}
tool_audit_trail = []
_MIN_ROUNDS = 2   # roster's min_iterations -- never honor "ready" before this
_MAX_ROUNDS = 4   # roster's max_iterations -- the largest of any role

loop:
  round += 1
  is_final_round = (round == _MAX_ROUNDS)
  below_min_rounds = round < _MIN_ROUNDS
  call LLM with: objective, task_context, tool_results_so_far, available tools
                 (from tool_grant), and:
                 - if below_min_rounds: "You must call at least one tool
                   before finalizing; a 'ready' status now will be ignored."
                 - if is_final_round: "NO MORE TOOL CALLS. Finalize with what
                   you have."
  parse response: {status: "ready" | "need_tools", tool_requests: [...],
                    result: {...} <- only when status == "ready"}

  if status == "need_tools" and not is_final_round:
      tool_results_so_far, new_records = await execute_tool_round(
          tool_requests=payload.tool_requests, tool_grant=block_input.tool_grant,
          tool_registry=self._tool_registry, tool_results_so_far=tool_results_so_far,
          log_prefix="simulation_planning",
      )
      tool_audit_trail += new_records
      continue   # this IS the reflect-and-revise mechanism -- a failed
                 # candidate just means the next round's tool_requests
                 # propose a different change/constraints; no special
                 # "retry" code path needed beyond the existing loop.

  if status == "ready" and below_min_rounds:
      continue   # premature finalize -- never honored, same as interpretation

  # status == "ready" (round >= _MIN_ROUNDS), OR forced-finalize final round
  if result is None:
      -> fail closed (round_budget_exhausted_no_result / status_ready_but_no_result)
  normalize + validate against the real `simulation_planning_agent_output_v1` schema
  if invalid: run the base class's generic `_repair_schema` (same reuse as
              both existing dedicated blocks)
  if still invalid: fail closed
  return completed, schema_valid=True, result=normalized, tool_audit_trail, rounds_used
```

## New module: `app/agent_core/subagents/simulation_planning_block.py`

Mirrors `retrieval_block.py`'s layout almost exactly (same round-loop shape,
same shared `execute_tool_round` helper), with one structurally significant
schema difference:

- `_SIMULATION_PLANNING_ROUND_V1` — one prompt contract, `role_prompt`
  adapted verbatim from `roles/prompts.py::_simulation_planning_agent_contract()`
  (same grounding block, same "translates loose constraints into the formal
  object... a hypothetical/simulated result must always be tagged as such"
  framing), carrying forward its existing 3 instructions plus the new
  per-round response-shape instruction and the `_MIN_ROUNDS`/forced-finalize
  framing (same pattern both existing dedicated blocks use).
- `_SIMULATION_PLANNING_OUTPUT_SCHEMA_NAME =
  "simulation_planning_agent_output_v1"` (already declared, dead, in
  `roles/prompts.py` — same "finally make it real" move both prior
  migrations made) and `_SIMULATION_PLANNING_OUTPUT_SCHEMA`:
  ```json
  {
    "type": "object",
    "properties": {
      "certainty_basis": {
        "type": "string",
        "enum": ["hypothetical_simulation", "predicted_pattern"]
      },
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "source_ref": {
        "type": ["object", "null"],
        "properties": {"page": {"type": "string"}, "section": {"type": ["string", "null"]}, "reasoning_path": {"type": ["string", "null"]}},
        "required": ["page"]
      },
      "assumptions": {"type": "array", "items": {"type": "string"}},
      "outcome": {"type": "object"}
    },
    "required": ["certainty_basis", "confidence", "outcome"]
  }
  ```
  **The deliberate schema difference from both existing dedicated blocks**:
  `certainty_basis`'s enum is restricted to exactly
  `{hypothetical_simulation, predicted_pattern}` — `official_record`,
  `wiki_derived`, and `llm_interpretation` are structurally excluded. This
  turns the role's own guardrail (*"Never present a simulated outcome as an
  official record"*, `roster.py:57`) into a schema-level enforcement, not
  just a prompt instruction — the same "guardrail becomes a required/
  restricted schema field" move `InterpretationReasoningBlock`'s required
  `source_ref` already made for its own guardrail. `source_ref` stays
  optional (matching retrieval's convention, not interpretation's) since a
  simulated projection's "source" is tool-computed state, not a single
  citable wiki page. `outcome` (free-form object, matching retrieval's open
  `facts` convention) is the actual projected plan/state payload —
  named to match `AGENT_VISION.md`'s own vocabulary ("produces projected
  plans or outcomes"), distinct from retrieval's `facts` and interpretation's
  `answer`.
- `_MIN_ROUNDS = 2`, `_MAX_ROUNDS = 4` (module constants, matching the
  roster's own `min_iterations`/`max_iterations` — same precedent both prior
  migrations set).
- `_SimulationPlanningBlockInput(BaseReasoningBlockInput)`: adds
  `tool_grant: list[str]` (same shape as the other two).
- `_SimulationPlanningBlockOutput(BaseReasoningBlockOutput)`: adds
  `tool_audit_trail: list[ToolInvocationRecord]`, `rounds_used: int` (same
  shape as the other two).
- `class SimulationPlanningReasoningBlock(BaseReasoningBlock)`: constructor
  takes `tool_registry: ToolRegistry` as an extra kwarg (identical shape to
  both existing tool-calling dedicated blocks). `_run_internal` implements
  the control flow above, calling `execute_tool_round` (no third copy of the
  tool-execution logic).
- `_simulation_planning_failed_output(self, *, reason, tool_audit_trail,
  rounds_used)` — overrides `_failed_output` (same pattern all dedicated
  blocks with extra required Output fields follow).
- `async def run_simulation_planning_subagent(*, context_package,
  tool_registry, llm_adapter, block_id) -> SubagentResult` — same signature
  shape as `run_retrieval_subagent`/`run_interpretation_subagent`: builds
  `_SimulationPlanningBlockInput` directly (bypassing whatever schema
  `context_package` carries, using the real
  `_SIMULATION_PLANNING_OUTPUT_SCHEMA` instead), runs the block, maps
  `status`: `"completed"` → `"succeeded"`, else `"failed"` (no `"partial"`,
  matching both existing wrappers' precedent). `certainty.basis` defaults to
  `"hypothetical_simulation"` if the result omits it (never
  `"llm_interpretation"`/`"wiki_derived"` as a retrieval/interpretation
  wrapper would — this default itself reinforces the same guardrail).

## Dispatch integration: `task_handler.py`

One more `if` branch in `_dispatch_single_specialist`, same shape as the
existing three:

```python
if role.name == "calculation_validation":
    return await run_calculation_validation_subagent(...)
if role.name == "retrieval":
    return await run_retrieval_subagent(...)
if role.name == "interpretation":
    return await run_interpretation_subagent(...)
if role.name == "simulation_planning":
    return await run_simulation_planning_subagent(
        context_package=context_package, tool_registry=tool_registry,
        llm_adapter=llm_adapter, block_id=block_id,
    )
return await run_subagent(...)
```

No roster change — `simulation_planning`'s `RoleDefinition` keeps its
existing `prompt_contract_name=SIMULATION_PLANNING_AGENT_V1` and its
existing `tool_grant_ceiling` **unchanged** (see Context's doc/code drift
note — deliberately not touched here).

## New contract doc: `docs/agent/SIMULATION_PLANNING_OUTPUT_CONTRACT.md`

Same pairing convention as the two existing `*_OUTPUT_CONTRACT.md` docs:
documents `simulation_planning_agent_output_v1`'s shape, the restricted-
`certainty_basis`-enum design rationale, the fail-closed error vocabulary,
and a worked example (e.g. simulating a failed-course delay via
`mutate_state(fail_course)` → `search_over_state(minimize_semesters)`).

## Explicitly out of scope for v1

- **Widening `tool_grant_ceiling` to include the composite tools**
  (`simulate_course_disruption`, `audit_graduation_progress`, etc.) per
  `HIGHER_LEVEL_TOOLS.md`'s stated (but not yet implemented) intent. This is
  a capability change, not an architecture change — orthogonal to what this
  migration is for. Flagged as a separate, distinct follow-up (see Open
  questions).
- **A structured "compare N candidate plans" feature** beyond what the round
  loop's natural reflect-and-revise already provides. No test or gap doc
  demonstrates a concrete need for the block itself to explicitly hold onto
  and compare multiple full candidates side-by-side (as opposed to just
  trying again with a revised `change`/`constraints`) — the existing
  `compare_plans` composite tool already exists for structured plan diffing
  if a future step needs it explicitly, and it's already in the registry
  (just not in this role's current tool grant, per the point above).
- **`step_prep.py`'s hardcoded `output_schema={"type": "object"}`** — left
  untouched, same precedent all prior dedicated blocks set.
- **A configurable round budget per call** — `_MIN_ROUNDS`/`_MAX_ROUNDS` are
  fixed module constants for v1, matching the roster defaults.

## Test plan

New `services/ai/tests/agent_core/test_simulation_planning_block.py`, same
convention as `test_retrieval_block.py`/`test_interpretation_block.py`
(`fake_llm_adapter_factory`, a counting wrapper around a registry with the
real deterministic `mutate_state`/`search_over_state` tools -- both work
against a plain in-memory `base_state` dict with no external infra
dependency, unlike `get_entity`/`interpret_text`, so the REAL tools can be
used directly in these tests rather than stubs):

- Round-1 `status: "ready"` is **not honored** — round advances instead
  (same `_MIN_ROUNDS` regression guard as interpretation's own test).
- Happy path: round 1 calls `mutate_state(fail_course)`, round 2 calls
  `search_over_state(minimize_semesters)` on the perturbed state, round 3
  (or 2, if the model combines the decision) finalizes with a schema-valid
  `outcome`.
- **Reflect-and-revise regression guard**: round 1's `search_over_state`
  call comes back with `unscheduledCourses` non-empty (a failed/incomplete
  candidate); round 2 requests a *different* `mutate_state`/`search_over_state`
  call (e.g. relaxed constraints); finalizes on round 3. Asserts no special
  "retry" code path was needed — this is just the ordinary loop.
- A tool request naming a tool not in `tool_grant` is skipped
  (`output_ok=False`) without aborting the round.
- **Restricted `certainty_basis` enum regression guard**: a finalize attempt
  with `certainty_basis: "official_record"` fails schema validation (not in
  the restricted enum) → triggers repair → if the repair also insists on
  `official_record`, fails closed. This is the key regression guard for the
  "never present a simulated outcome as an official record" guardrail now
  being schema-enforced.
- Round budget exhausted (`_MAX_ROUNDS` rounds all `need_tools`) → forced
  finalize on the last round; no result → fails closed.
- Malformed `result` on finalize triggers the base class's generic
  `_repair_schema` and recovers; repair-exhausted fails closed.
- `SubagentResult` shape parity test; `certainty.basis` defaults to
  `"hypothetical_simulation"` (never `"llm_interpretation"`) when the model
  omits it.

Extend `test_orchestrator_task_handler.py` with one new test mirroring the
existing three dispatch-routing tests, for the new `simulation_planning`
branch.

## Rollout / verification plan

1. Implement `simulation_planning_block.py` + its test file.
2. Wire the `task_handler.py` dispatch branch + its test.
3. Write `docs/agent/SIMULATION_PLANNING_OUTPUT_CONTRACT.md`.
4. Run the full `services/ai` regression suite (`pytest services/ai/tests/agent_core/
   -m "not live"`) — confirm zero new failures beyond the 2 known
   pre-existing, unrelated `test_get_policy_answer.py` ones.
5. Commit in discrete batches (block + tests, then dispatch wiring + its
   test, then docs).
6. Live-eval verification deferred until explicitly requested, same policy
   held for both prior migrations.

## Open questions to resolve at implementation time

- **Whether to widen `tool_grant_ceiling` to include the composite tools**
  now that `HIGHER_LEVEL_TOOLS.md` already claims this is done (proposed:
  no, not as part of this migration — raise it as a separate, explicit
  follow-up once this block's own architecture is settled and tested; the
  doc's claim appears to be aspirational/stale rather than a design decision
  this migration should silently correct).
- **Whether `outcome` should be split into narrower named sub-fields** (e.g.
  `plan`, `appliedChanges`) rather than one free-form object (proposed: keep
  it free-form for v1, matching retrieval's own `facts` convention — no
  concrete downstream consumer demonstrates a need for a narrower shape yet).
- **Whether the reflect-and-revise pattern needs any explicit
  "previousAttempts" context carried forward across rounds** beyond what
  `tool_results_so_far` already accumulates (proposed: no — the accumulated
  tool results already give the model everything it needs to see that its
  last candidate failed a constraint; no evidence a separate structured
  attempt-history is needed).
