# Composition reasoning block implementation plan

**Status: implemented** -- full unit test suite green, zero new regressions
(full `services/ai` suite: 484 passed, 1 skipped, 0 failed). Live-eval
verification is still outstanding. Fourth of five generic-path migrations
(`retrieval` ✅ → `interpretation` ✅ → `simulation_planning` ✅ →
`composition` ✅ → the orchestrator's own **`synthesis.py::compose_answer()`**),
tackled one at a time per explicit instruction. This plan covers the
**per-step `composition` role dispatch only** — see "Relationship to the
fifth migration" below for why the two are related but not the same change.

## Context

The roster (`roles/roster.py:59-67`):
```python
"composition": RoleDefinition(
    name="composition",
    prompt_contract_name=COMPOSITION_AGENT_V1,
    tool_grant_ceiling=(),
    default_reasoning_params=RoleReasoningDefaults(
        risk_level="low", min_iterations=1, max_iterations=2, temperature=0.4, timeout=60.0
    ),
    guardrails=("Zero tool access -- works only from what it's handed.",),
),
```
Zero tool grant, enforced by a `RoleDefinition` validator that rejects any
non-empty `tool_grant_ceiling` for this role (`test_roles.py::
test_composition_role_validator_rejects_a_nonempty_tool_grant`).
`AGENT_VISION.md` §6 (line 181): *"Deliberately gets no tool access at all —
the one hard guarantee that keeps the very last step from reaching out and
grabbing something ungrounded at the last second."* §7.2 (line 239): *"No
role is ever allowed to return free text except Composition, on the terminal
step."*

**This is the simplest of the four tool-calling-role migrations, because
there's no tool-calling at all.** Composition needs no `tool_registry`, no
`tool_grant` field, no round loop, no `execute_tool_round` — just a
single-shot reasoning call, structurally identical to
`RequestUnderstandingReasoningBlock` (the one existing dedicated block that
also has zero tool access) rather than to
`Retrieval`/`Interpretation`/`SimulationPlanning`'s bounded-round-loop shape.
A near-identical single-shot, zero-tool reference implementation **already
exists**: `tools/primitives/compose_answer.py::ComposeAnswerReasoningBlock`
— a *tool primitive* (registered as the callable tool `"compose_answer"`,
invoked BY other subagents that hold it in their own tool grant), not the
composition role's own dispatch, but its control flow (one `_invoke_llm` →
normalize → validate → repair (max 2) → an extra semantic check beyond bare
schema validity → success/failure) is exactly the shape this new block
needs, adapted to the role's own `SubagentContextPackage` input instead of
the tool's bespoke `_InterpretedFact` list.

**Today, the per-step `composition` role already falls through to the
generic path** — `task_handler.py::_dispatch_single_specialist` has explicit
branches for `calculation_validation`/`retrieval`/`interpretation`/
`simulation_planning` (lines 143-170) but composition hits the generic
`return await run_subagent(...)` fallback (lines 171-177). No existing test
exercises the *real* per-step composition dispatch chain end-to-end except
one: `test_skeleton_end_to_end.py`'s hand-built 2-step
`retrieval → composition` plan, which drives a real composition step through
the real generic path with 2 canned LLM responses (`step-prep`, then a
"pass 1/2 not final" + "pass 2/2 final" pair, matching the old generic
`ReasoningBlock`'s internal 2-pass loop for `max_iterations=2`). **Migrating
composition to a single-shot dedicated block will need the same kind of
test-fixture update `retrieval`'s own migration needed** — collapsing those
2 canned composition responses into 1, the same "stale call-count
assumption" fix already made once.

## Relationship to the fifth migration (`synthesis.py::compose_answer()`)

Investigated directly rather than assumed: **both call sites use the exact
same role, prompt contract, and zero-tool-grant enforcement, and both
currently terminate in the same generic `run_subagent` call** — but they
build meaningfully different `SubagentContextPackage` inputs, so one wrapper
function cannot simply serve both unchanged:

1. **`dependency_state` scope differs.** The per-step path
   (`context_builder.py:20`) slices to only the step's declared
   dependencies (`state.slice(step_prep.context_requirements)`).
   `synthesis.compose_answer()` (`synthesis.py:55`) always passes
   `list(state.entries)` — the **entire** accumulated plan state,
   unconditionally. Terminal synthesis intentionally sees everything; a
   per-step composition step only sees what it declared it needs.
2. **Prompt/instruction assembly differs.** The per-step path runs a real
   `step_prep` reasoning call producing full `StepInstructionFields`
   (`goal`, `description`, `specific_instructions`, `tone_language_notes`),
   rendered via `render_subagent_prompt`. `synthesis.compose_answer()`
   hardcodes a bare template instead (`rendered_prompt=f"Compose the final
   answer for: {user_goal}"`, empty `specific_instructions`/
   `tone_language_notes`) — no step-prep pass at all.
3. **Retry-on-missing-result is currently synthesis-only.** The
   `_RESULT_MISSING_MARKER` retry-once policy
   (`synthesis.py:26-34,68-75`) exists only in `compose_answer()`; the
   per-step dispatch chain has no equivalent today.

**Decision for this plan**: build the dedicated `CompositionReasoningBlock` +
a `run_composition_subagent()` wrapper that **absorbs the retry-on-missing-
result policy into the wrapper itself** (not synthesis-specific — "fix the
structure, don't invent the missing prose" is equally true for a per-step
composition call), so both call sites get it "for free" once migration #5
retrofits `synthesis.py` to call this wrapper instead of duplicating the
retry loop. This plan wires the wrapper into `task_handler.py`'s per-step
dispatch only; migration #5 is a small follow-up (swap `synthesis.py`'s
manual `run_subagent` + retry-loop for one call to `run_composition_subagent()`,
keeping its own full-state/no-step-prep context assembly as a thin layer on
top) — not bundled into this plan, per the explicit one-at-a-time
instruction.

## Why a dedicated block (recap)

Same extension point as all four existing dedicated blocks. Since
composition needs no `tool_registry`, its constructor is even simpler than
`RetrievalReasoningBlock`'s — it takes only `llm_adapter`/`prompt_registry`,
matching `RequestUnderstandingReasoningBlock`'s constructor shape exactly
(no tool dependency at all).

## Control flow

Single-shot, no loop — mirrors `ComposeAnswerReasoningBlock`'s shape:

```
resolve contract (COMPOSITION_V1) + LLM params (temperature=0.4 via contract)
one _invoke_llm call (phase="pass1_of_1")
normalize + validate against the real `composition_agent_output_v1` schema
if invalid:
    run the base class's generic _repair_schema (max_attempts=2) --
    reuse, not a bespoke loop, same choice RequestUnderstandingReasoningBlock
    and every prior dedicated block made
    if still invalid: fail closed
extra semantic check (beyond bare schema validity, mirroring
ComposeAnswerReasoningBlock's own defense-in-depth): answer_text must be a
non-blank string, not a placeholder -- schema validity alone can't express
"non-empty, non-placeholder", same reasoning ComposeAnswerReasoningBlock's
own _to_output-equivalent check already uses
return completed, schema_valid=True, result={"answer_text": ...}
```

No round budget, no tool grant, no tool_audit_trail — genuinely the
simplest of the five migrations.

## New module: `app/agent_core/subagents/composition_block.py`

- `_COMPOSITION_V1` — one prompt contract, `role_prompt`/`instructions`/
  `safety_rules` adapted verbatim from
  `roles/prompts.py::_composition_agent_contract()` (same "you have NO tool
  access... never introduce a number, status, or fact not already present...
  preserve certainty distinctions... preserve the user's own language"
  framing). `default_temperature=0.4` (flows through automatically via
  `_resolve_llm_call_parameters`, same mechanism every dedicated block uses).
- `_COMPOSITION_OUTPUT_SCHEMA_NAME = "composition_agent_output_v1"` (already
  declared, dead-at-the-role-level, in `roles/prompts.py` — same
  "finally make it real" move all three prior migrations made) and
  `_COMPOSITION_OUTPUT_SCHEMA`:
  ```json
  {
    "type": "object",
    "properties": {"answer_text": {"type": "string"}},
    "required": ["answer_text"],
    "additionalProperties": false
  }
  ```
  Matches `tools/primitives/compose_answer.py::_OUTPUT_SCHEMA` exactly
  (including `additionalProperties: false`) — this is the canonical schema
  both the tool primitive and (after migration #5) `synthesis.py` will
  share; `synthesis.py`'s own current inline schema lacks
  `additionalProperties: false` and will be reconciled onto this one at that
  point, not duplicated with a subtly different shape.
- **No `_CompositionBlockInput`/`_CompositionBlockOutput` subclasses needed
  at all** — `BaseReasoningBlockInput`/`BaseReasoningBlockOutput` already
  carry everything this block needs (`block_id`, `agent_name`, `objective`,
  `task_context`, `output_schema`/`name`, `prompt_contract_name`,
  `llm_call_parameters` on the input side; `status`, `schema_valid`,
  `result`, `confidence`, `warnings`, `total_llm_calls_used` on the output
  side) — no tool grant, no audit trail, no round counter. This is the one
  dedicated block in the whole set that needs zero shape extension.
- `class CompositionReasoningBlock(BaseReasoningBlock)`: constructor takes
  only `llm_adapter`/`prompt_registry` (no `tool_registry` — nothing to
  store), matching `RequestUnderstandingReasoningBlock`'s constructor shape.
  `_run_internal` implements the control flow above.
- `_composition_failed_output(self, reason)` — overrides `_failed_output`
  the same way every dedicated block with a distinct failure-reason
  convention does (even though the Output type itself needs no new fields
  here, the override keeps the `warnings=[f"composition_failed: {reason}"]`
  convention consistent with the other four).
- `async def run_composition_subagent(*, context_package, llm_adapter,
  block_id) -> SubagentResult` — **note: no `tool_registry` parameter**,
  the one signature difference from the other three `run_xxx_subagent`
  wrappers, since composition never touches a tool. Builds the base
  `BaseReasoningBlockInput` directly (bypassing whatever schema
  `context_package` carries, using the real `_COMPOSITION_OUTPUT_SCHEMA`
  instead), runs the block once; **if the result is `status="failed"` and
  `"result_is_missing"` is among its warnings, retries once** (the
  `_RESULT_MISSING_MARKER` policy absorbed from `synthesis.py`, see
  "Relationship to the fifth migration" above) with `block_id=
  f"{block_id}-retry"`; maps `status`: `"completed"` → `"succeeded"`, else
  `"failed"` (no `"partial"`, matching every other wrapper's precedent).

## Dispatch integration: `task_handler.py`

One more `if` branch in `_dispatch_single_specialist`, same shape as the
existing four — note it does **not** need `tool_registry` passed through to
the wrapper call (composition never uses one), unlike the other three
branches:

```python
if role.name == "calculation_validation":
    return await run_calculation_validation_subagent(...)
if role.name == "retrieval":
    return await run_retrieval_subagent(...)
if role.name == "interpretation":
    return await run_interpretation_subagent(...)
if role.name == "simulation_planning":
    return await run_simulation_planning_subagent(...)
if role.name == "composition":
    return await run_composition_subagent(
        context_package=context_package, llm_adapter=llm_adapter, block_id=block_id,
    )
return await run_subagent(...)
```

No roster change — `composition`'s `RoleDefinition` keeps its existing
`prompt_contract_name=COMPOSITION_AGENT_V1` and its (already-enforced-empty)
`tool_grant_ceiling` unchanged.

## New contract doc: `docs/agent/COMPOSITION_OUTPUT_CONTRACT.md`

Same pairing convention as the three existing `*_OUTPUT_CONTRACT.md` docs —
though the shortest of the four, since the schema itself is a single
required string field. Documents `composition_agent_output_v1`'s shape, the
"why no tool access" design rationale (cross-referencing `AGENT_VISION.md`
§6/§7.2), the fail-closed error vocabulary, and the retry-on-
`result_is_missing` policy now living in `run_composition_subagent()`.

## Explicitly out of scope for v1

- **Retrofitting `synthesis.py::compose_answer()` to call this new
  wrapper.** That's migration #5, done separately once this one is
  implemented and tested — see "Relationship to the fifth migration."
  `synthesis.py` is untouched by this plan.
- **`step_prep.py`'s hardcoded `output_schema={"type": "object"}`** — left
  untouched, same precedent all prior dedicated blocks set (this block
  bypasses it the same way the other three do, using its own real schema
  directly).
- **Any change to `AGENT_VISION.md` §7.2's "Composition never gets tools"
  invariant** — this plan reinforces it (zero-tool constructor), never
  weakens it.

## Test plan

New `services/ai/tests/agent_core/test_composition_block.py`, same
convention as the other three block test files (`fake_llm_adapter_factory`,
everything exercised through the public `run_composition_subagent()` entry
point — no tool registry needed at all, the simplest fixture setup of the
five):

- Happy path: one LLM call, valid `answer_text` → `status="succeeded"`.
- Malformed result (missing `answer_text`, or `additionalProperties`
  violation) triggers the base class's generic `_repair_schema` and
  recovers.
- Repair exhausted fails closed.
- **Blank/placeholder `answer_text`** (e.g. `""` or a known blank-field
  placeholder) fails closed via the extra semantic check, even though it's
  schema-valid — the key regression guard mirroring
  `ComposeAnswerReasoningBlock`'s own equivalent test
  (`test_to_output_clamps_out_of_range_confidence`-style defense-in-depth
  precedent).
- **Retry-on-`result_is_missing`**: first call fails with
  `warnings=["schema_validation_failed", "result_is_missing"]`, second call
  succeeds → `run_composition_subagent()` returns the retry's result,
  exactly 2 LLM calls (ported directly from
  `test_synthesis.py::test_retries_once_when_result_is_missing_and_returns_the_retry_outcome`,
  now exercised at the block-wrapper level instead of the synthesis level).
- **No retry for other failure reasons**: a schema failure without
  `result_is_missing` in its warnings does not retry (ported from
  `test_synthesis.py::test_does_not_retry_when_the_failure_is_not_result_is_missing`).
- `SubagentResult` shape parity test (same as every other dedicated block's
  own final test).

Update `test_skeleton_end_to_end.py`'s canned composition responses: the old
generic path's 2-call "pass 1/2 not final" + "pass 2/2 final" pair collapses
into 1 single-shot call, the same kind of fixture fix retrieval's own
migration already required.

Extend `test_orchestrator_task_handler.py` with one new test mirroring the
existing four dispatch-routing tests, for the new `composition` branch.

## Rollout / verification plan

1. Implement `composition_block.py` + its test file.
2. Wire the `task_handler.py` dispatch branch + its test.
3. Update `test_skeleton_end_to_end.py`'s composition fixture (call-count
   fix, same pattern as retrieval's migration).
4. Write `docs/agent/COMPOSITION_OUTPUT_CONTRACT.md`.
5. Run the full `services/ai` regression suite — confirm zero new failures
   beyond the 2 known pre-existing, unrelated `test_get_policy_answer.py`
   ones.
6. Commit in discrete batches (block + tests, then dispatch wiring + its
   test + the skeleton-test fixture fix, then docs).
7. Live-eval verification deferred until explicitly requested, same policy
   held for all three prior migrations.
8. Migration #5 (`synthesis.py` retrofit) planned and implemented
   separately, after this one lands.

## Open questions to resolve at implementation time

- **Whether the retry-on-`result_is_missing` policy belongs in the wrapper
  or should stay purely synthesis-specific until migration #5 actually needs
  it** (proposed: put it in the wrapper now, since it costs nothing to
  include and means the per-step composition path gets the same recovery
  behavior immediately rather than waiting for migration #5 to retrofit it
  in).
- **Whether to add `additionalProperties: false`** to the canonical schema
  now, even though `synthesis.py`'s current inline schema doesn't have it
  (proposed: yes, matching the tool primitive's own stricter schema — no
  reason for the role-level schema to be looser than the tool-level one it
  will eventually be reconciled with).
