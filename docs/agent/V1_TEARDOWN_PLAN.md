# V1 org-chart teardown plan

Executable plan to remove the replaced V1 orchestration architecture from
`services/ai` now that the V2 loop is live-validated. **Not yet executed** — this
is the plan; run it as its own focused pass (ideally a fresh session) on
`rewrite/agent-v2`.

## Preconditions (met, 2026-07-18)

- V2 loop validated live: 11/11 grounded, `sub_loop_investigation` closed via the
  `map` path. See [AGENT_ARCHITECTURE_V2.md](AGENT_ARCHITECTURE_V2.md) §18–§19.
- `/advise` is wired to `run_agent_loop` and imports **no** V1 org-chart module
  (verified: grep of `routes/advise.py`).
- The validated V2 work is committed (`1d896ee`) — clean baseline, so the teardown
  lands as isolated, revertible commits on top.

## What the reachability audit found (2026-07-18)

The dead/live boundary is **not clean at the directory level**. Two shared
infrastructure layers are threaded into live V2 code and must be handled *before*
the V1 cluster can be deleted.

### Confirmed SURVIVORS (imported by live V2 tools / the loop)

- **`planning/state.py` TYPES** — `CertaintyTag`, `CertaintyBasis`, `SourceRef`,
  `ToolInvocationRecord`. Imported by ~20 live tool primitives/composites,
  `tools/envelope.py`, `subagents/tool_round.py`, and the runner (via
  `ToolInvocationRecord`). **MUST be preserved** (split out; see Tangle 1).
- **`reasoning_blocks/base.py`** — `BaseReasoningBlock`, `RunTelemetry`,
  `BaseReasoningBlockInput/Output`, `LLMCallParameters`. Imported by the live
  primitives `interpret_text.py` and `compose_answer.py`, and by
  `boundary_handler/boundary_handler.py`. Survives unless those are refactored off
  it (see Tangle 2).
- **`subagents/`**: `fact_projection.py` (project_facts/resolve_path) and
  `tool_round.py` (`execute_tool_round`, used by the runner). Verify their own
  deps (`run.py`, `tool_loop.py`, `schemas.py`).
- **`loop/`**, **`reasoning/`** (`llm_adapter`, `llm_client`), **`tools/`**
  (primitives + composites + `registry` + `envelope` + `call_cache` +
  `default_registry`), **`retrieval/`**, `response_language.py`.

### V1 DELETION candidates (confirm zero live importer in step 1 before deleting)

- `orchestrator/` — `loop.py`, `task_handler.py`, `monitor.py`
- `planning/` **minus the surviving state types** — `planner.py`,
  `planner_council.py`, and `state.py`'s `PlanExecutionState` / `StateEntry`
- `complexity_classifier/`
- `request_understanding/`
- `synthesis/`
- `turn.py`, `turn_context.py` (the V1 entrypoint + its `ReplanLedger`)
- `subagents/` V1 blocks: `calculation_validation_block.py`, `composition_block.py`,
  `retrieval_block.py`, `interpretation_block.py`, `simulation_planning_block.py`
- `roles/` and `planning/schemas.py` (`RoleName`) — **verify**: used by
  `turn_context` (V1) and `roles/catalog.py`; determine if anything V2 needs them
- `boundary_handler/` — **verify**: imports `base.py`; the V2 loop has its own
  `front_door` + `answer_boundary`, so it is likely dead, but confirm it is not
  registered/used
- `tools/primitives/compose_answer.py` — **verify**: the loop answers via
  `final_answer`/`resolve_final`, so `compose_answer` may be dead; if so it (and
  its `base.py` dependency) can go, simplifying Tangle 2

### Tangles to untangle BEFORE any deletion

1. **Split `planning/state.py`.** Move `CertaintyTag` / `CertaintyBasis` /
   `SourceRef` / `ToolInvocationRecord` into a survivor module (e.g.
   `agent_core/certainty.py`); delete `PlanExecutionState` / `StateEntry`; repoint
   ~30 import sites. Note `StateEntry` is imported by V1 blocks **and**
   `subagents/schemas.py` — confirm `schemas.py`'s fate in step 1.
2. **Decide `reasoning_blocks/base.py`.** Either keep it as-is (simplest — it is
   small shared infra that `interpret_text`/`compose_answer`/`boundary_handler`
   use) or, if `compose_answer`/`boundary_handler` turn out dead, refactor
   `interpret_text` off it and delete. Recommendation: **keep `base.py`** unless the
   audit shows it only served now-dead consumers.
3. **`roles/` + `planning/schemas.py` `RoleName`.** Trace whether any V2 path needs
   `RoleName`; if only V1 does, they die with the cluster.

## Ordered execution (fresh session, on `rewrite/agent-v2`)

1. **AUDIT.** Build the definitive import graph: `graphify query`/`path` + a grep of
   every candidate. Mark a module for deletion only after confirming **zero** live
   (non-V1) importer. Produce the final survive/die list.
2. **SPLIT `state.py`** (Tangle 1): extract survivor types → new module, repoint
   imports, delete `PlanExecutionState`/`StateEntry`. Run the suite → green. Commit
   as its own `refactor(ai): split state.py` — safe and isolated.
3. **Resolve Tangles 2–3** per the audit (keep/refactor `base.py`; settle
   `roles`/`RoleName`, `compose_answer`, `boundary_handler`).
4. **DELETE** the confirmed-dead V1 modules **and their test files**, one cohesive
   group at a time (orchestrator; planning/planner*; request_understanding;
   synthesis; complexity_classifier; turn*; the V1 subagent blocks), **running the
   full suite after each group** — never batch-delete then test at the end.
5. **DOCS.** Retire/supersede the V1 architecture docs; keep
   `AGENT_ARCHITECTURE_V2.md` as the source of truth; update service READMEs. Delete
   this file once the teardown is complete.
6. **VERIFY.** Full `services/ai` suite green + a live `/advise` smoke (one real
   question) confirming the endpoint still answers grounded.
7. **`graphify update .`** to refresh the graph, then commit as focused
   `chore(ai): remove V1 org chart` commits (reviewable in isolation).

## Risk notes (do-not-break list)

- Do **not** delete `planning/state.py` wholesale — breaks ~20 live tools.
- Do **not** delete `reasoning_blocks/base.py` without first refactoring
  `interpret_text` (and `compose_answer`/`boundary_handler` if kept) off it.
- Do **not** delete `subagents/fact_projection.py` or `subagents/tool_round.py` —
  the runner depends on both.
- Suite-run after **each** deletion group; keep each group a separate commit so any
  breakage is bisectable.
