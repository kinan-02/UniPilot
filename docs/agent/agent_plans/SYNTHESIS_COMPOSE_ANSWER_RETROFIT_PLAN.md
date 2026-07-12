# `synthesis.py::compose_answer()` retrofit plan

**Status: implemented** -- full unit test suite green, zero new regressions
(full `services/ai` suite: 484 passed, 1 skipped, 0 failed). Live-eval
verification is still outstanding. Fifth and final generic-path migration
(`retrieval` ✅ → `interpretation` ✅ → `simulation_planning` ✅ →
`composition` ✅ → **`synthesis.py::compose_answer()`** ✅). All five
generic-path migrations are now complete.
Unlike the other four, this is not a new-block build — `CompositionReasoningBlock`/
`run_composition_subagent()` already exist (`docs/agent/agent_plans/
COMPOSITION_REASONING_BLOCK_PLAN.md`). This plan is a **retrofit**: swap
`synthesis.py`'s own generic `run_subagent` call + manual retry loop for one
call to the already-built `run_composition_subagent()`.

## Context

`synthesis.py::compose_answer()` (the orchestrator's terminal final-answer
step, called once from `orchestrator/loop.py:150-157` when the plan is
complete and the last `StateEntry` isn't already a composition step) today:

```python
async def compose_answer(
    *, state, user_goal, composition_role, tool_registry, llm_adapter, block_id,
) -> SubagentResult:
    if composition_role.tool_grant_ceiling:
        raise ValueError(...)
    context_package = SubagentContextPackage(
        rendered_prompt=f"Compose the final answer for: {user_goal}",
        structured_fields=StepInstructionFields(goal=user_goal, description="..."),
        dependency_state=list(state.entries),   # FULL state, unsliced
        tool_grant=[], output_schema_name="composition_agent_output_v1",
        output_schema=_COMPOSITION_OUTPUT_SCHEMA, guardrails=list(composition_role.guardrails),
    )
    result = await run_subagent(role=composition_role, context_package=context_package,
                                  tool_registry=tool_registry, llm_adapter=llm_adapter, block_id=block_id)
    if result.status == "failed" and _RESULT_MISSING_MARKER in result.warnings:
        result = await run_subagent(..., block_id=f"{block_id}-retry")   # manual retry-once
    return result
```

Confirmed during the composition-migration research (not re-derived here):
this call site's context assembly is **deliberately different** from the
per-step composition dispatch — `dependency_state=list(state.entries)` (the
entire accumulated plan, unsliced, since terminal synthesis is supposed to
see everything) vs. the per-step path's dependency-sliced state; a hardcoded
`rendered_prompt`/`StepInstructionFields` template with no `step_prep` pass,
vs. the per-step path's real step-prep call. **Both of these stay exactly as
they are** — this retrofit only changes *how the reasoning itself is
invoked*, not what context it's given.

The one piece that **does** get removed: the manual `_RESULT_MISSING_MARKER`
retry-once loop (`synthesis.py:26-34,68-75`). `run_composition_subagent()`
already absorbed an equivalent retry policy (checks for `"empty_answer_text"`
— `CompositionReasoningBlock`'s own actual failure-reason string — rather
than synthesis's `"result_is_missing"` string, since the new block's fail
path never actually emits `"result_is_missing"` verbatim; the two markers
served the same purpose but aren't byte-identical strings). Once
`compose_answer()` calls the wrapper, its own retry loop is fully redundant.

## Changes

### 1. `synthesis.py::compose_answer()`

Replace the two `run_subagent(...)` calls with one call to
`run_composition_subagent()`:

```python
from app.agent_core.subagents.composition_block import run_composition_subagent

async def compose_answer(
    *, state, user_goal, composition_role, tool_registry, llm_adapter, block_id,
) -> SubagentResult:
    if composition_role.tool_grant_ceiling:
        raise ValueError("compose_answer requires a composition role with zero tool grant")

    context_package = SubagentContextPackage(
        rendered_prompt=f"Compose the final answer for: {user_goal}",
        structured_fields=StepInstructionFields(
            goal=user_goal,
            description="Compose a grounded final answer from the accumulated plan-execution state.",
        ),
        dependency_state=list(state.entries),
        tool_grant=[],
        output_schema_name="composition_agent_output_v1",
        output_schema=_COMPOSITION_OUTPUT_SCHEMA,
        guardrails=list(composition_role.guardrails),
    )
    return await run_composition_subagent(
        context_package=context_package, llm_adapter=llm_adapter, block_id=block_id,
    )
```

- `tool_registry` parameter: **kept** on `compose_answer()`'s own signature
  (its callers — `orchestrator/loop.py` — pass it, and changing a public
  orchestrator-facing signature is out of scope for a retrofit), but no
  longer forwarded anywhere internally, since `run_composition_subagent()`
  doesn't take one. Confirmed unused-but-harmless, same as how
  `composition_role`'s own `tool_grant_ceiling` is checked but never
  populated.
- `_RESULT_MISSING_MARKER` constant and its docstring/rationale comment
  (`synthesis.py:26-34`): **removed** — dead now that the retry lives in
  `run_composition_subagent()`.
- `_COMPOSITION_OUTPUT_SCHEMA` (`synthesis.py:20-24`): **kept as-is**
  (`{"type": "object", "properties": {"answer_text": {"type": "string"}},
  "required": ["answer_text"]}`, no `additionalProperties: false`) — it's
  still passed into `context_package.output_schema`, but per the same
  precedent every dedicated block already established,
  `run_composition_subagent()` ignores it and uses its own real
  `_COMPOSITION_OUTPUT_SCHEMA` (which *does* have `additionalProperties:
  false`) internally. The two schemas being subtly different is now
  harmless (one is vestigial), not a real inconsistency — not worth forcing
  them byte-identical just to remove an already-inert field.
- `run_subagent` import: removed (no longer used anywhere in this file).

### 2. `test_synthesis.py`

The existing 3 tests
(`test_retries_once_when_result_is_missing_and_returns_the_retry_outcome`,
`test_does_not_retry_when_the_failure_is_not_result_is_missing`,
`test_does_not_retry_on_a_successful_result`) monkeypatch `run_subagent`
directly to test synthesis's *own* retry loop — that loop no longer exists
after this retrofit, and the retry behavior itself is already covered by
`test_composition_block.py`'s own retry tests (ported there during the
composition migration). **These 3 tests are replaced, not kept alongside
new ones** — retesting the same retry behavior at both layers would be
redundant coverage of logic that only lives in one place now.

New tests, monkeypatching `run_composition_subagent` instead (same
established convention this suite already uses — monkeypatch the
collaborator, not an LLM adapter):
- `test_compose_answer_passes_the_full_unsliced_state_as_dependency_state` —
  asserts the `context_package` passed to `run_composition_subagent` has
  `dependency_state == list(state.entries)`, not a sliced subset (the key
  behavioral guarantee that must survive this refactor unchanged).
- `test_compose_answer_raises_on_a_nonempty_tool_grant` — the existing
  `ValueError` guard, confirmed still enforced (may already exist; port
  forward if so, don't duplicate).
- `test_compose_answer_delegates_to_run_composition_subagent_and_returns_its_result`
  — a single call, no retry logic left in `synthesis.py` itself; whatever
  `run_composition_subagent` returns (`succeeded` or `failed`) passes straight
  through unchanged.

### 3. `test_skeleton_end_to_end.py` and other integration tests

No changes expected — this test drives the per-step composition dispatch
(already migrated), not `synthesis.py::compose_answer()`'s own code path
(which only fires when the plan's last entry isn't already a composition
step — the skeleton test's composition step *is* the plan's last entry, so
`compose_answer()` is never actually reached in that test). Confirm this
during implementation rather than assuming.

## Explicitly out of scope

- **Any change to `orchestrator/loop.py`'s call site** — it already calls
  `compose_answer(...)` with the same arguments; the function's public
  signature is unchanged.
- **Removing the now-unused `tool_registry` parameter from
  `compose_answer()`'s signature** — technically dead internally now, but
  removing a parameter from a function `loop.py` calls is a separate,
  larger-blast-radius change than "swap the internal implementation," and
  nothing demonstrates it's worth doing right now.
- **Reconciling `_COMPOSITION_OUTPUT_SCHEMA`'s missing
  `additionalProperties: false`** with the real schema `composition_block.py`
  uses — vestigial-but-harmless, per the explanation above.

## Test plan

1. `test_synthesis.py` rewritten per section 2 above.
2. Full `services/ai` regression suite — confirm zero new failures (current
   baseline: 484 passed, 1 skipped, 0 failed as of the composition
   migration's own verification).

## Rollout / verification plan

1. Implement the `synthesis.py` retrofit.
2. Rewrite `test_synthesis.py`.
3. Run the full regression suite.
4. Commit in one discrete batch (this is a small, single-file-plus-its-tests
   change, unlike the four block-building migrations).
5. Live-eval verification deferred until explicitly requested — same policy
   held throughout, and this is the last of the 5 migrations, so this is
   also the point at which a full live-eval run (real LLM, real seeded
   student, the original motivating scenario from earlier in this project)
   becomes meaningful to actually request.

## Open questions to resolve at implementation time

- **Whether `test_synthesis.py`'s 3 retry tests should be deleted outright
  or kept as thin pass-through regression guards** (proposed: delete —
  keeping them would mean asserting behavior that no longer exists in this
  file, which is misleading regardless of whether they'd pass).
