# V1 teardown plan

Executable plan to remove the replaced V1 agent architecture now that the V2 loop is
live-validated (the live `/advisor` page already runs on the new `ai` service). **Not
yet executed** — run each phase as its own focused pass (ideally a fresh session) on
`rewrite/agent-v2`.

Two INDEPENDENT phases (either order, separate commits):

- **Phase A** — dead V1 org-chart *code inside `services/ai`* (the loop replaced the
  old orchestrator internally). Surgical, single-service.
- **Phase B** — retire the dead conversational *agent feature* end-to-end across
  `services/agent` + `services/api` + `services/web` (users are on the V2 `/advisor`
  page instead; the old `AgentPage`/`/agent` UI is unused). Cross-service.

## Preconditions (met, 2026-07-18)

- V2 loop validated live: 11/11 grounded, `sub_loop_investigation` closed via the
  `map` path. See [AGENT_ARCHITECTURE_V2.md](AGENT_ARCHITECTURE_V2.md) §18–§19.
- `/advise` is wired to `run_agent_loop` and imports **no** V1 org-chart module
  (verified: grep of `routes/advise.py`).
- The live web `/advisor` page → `advisorApi` → api `advisor.py` → `ai_advisor_client`
  → the `ai` (V2) service. The dead agent feature is a **separate** page
  (`AgentPage`/`/agent`) → `agent_service_client` → `services/agent`.
- The validated V2 work is committed (`1d896ee`) — clean baseline, so the teardown
  lands as isolated, revertible commits on top.

## Phase A — dead V1 org-chart code inside `services/ai`

### What the reachability audit found (2026-07-18)

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

### Phase A — ordered execution (fresh session, on `rewrite/agent-v2`)

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

### Phase A — risk notes (do-not-break list)

- Do **not** delete `planning/state.py` wholesale — breaks ~20 live tools.
- Do **not** delete `reasoning_blocks/base.py` without first refactoring
  `interpret_text` (and `compose_answer`/`boundary_handler` if kept) off it.
- Do **not** delete `subagents/fact_projection.py` or `subagents/tool_round.py` —
  the runner depends on both.
- Suite-run after **each** deletion group; keep each group a separate commit so any
  breakage is bisectable.

## Phase B — retire the dead agent feature (`agent` + `api` + `web`)

The predecessor conversational-agent feature is unused — users are on the V2
`/advisor` page (→ `ai` service); the old `AgentPage` / `/agent` UI (→ `services/agent`)
is dead. Removing it spans THREE services + infra. **Import boundary verified clean
(2026-07-18):** only `web/src/App.tsx` references the agent UI, and no live/shared
module imports the agent web modules — so the deletion cannot touch the live
`/advisor` path.

### KEEP — do NOT remove (the live V2 path, confusingly also named "advisor")

- web: `pages/AdvisorPage.tsx`, `advisorApi` (in `api/endpoints.ts`), the `/advisor`
  route + its nav entry.
- api: `routes/advisor.py`, `clients/ai_advisor_client.py`, `services/advisor_service.py`.
- `services/ai` (the whole service) and everything Phase A concerns.

### DELETE — the dead agent feature

**`services/web/`** (agent UI — self-contained):
- `pages/AgentPage.tsx`; `components/agent/*` (AgentChatArea, AgentContextPanel,
  AgentSidebar, AgentBlocks, AgentComposer, agentMotion); `hooks/useAgentChat.ts`;
  `api/agentConversations.ts`; `lib/agentStream.ts`; `types/agent.ts`.
- `App.tsx`: remove the `AgentPage` import, `<Route path="/agent">`, and the
  `<Route path="agents" → Navigate to="/agent">` redirect.
- `components/layout/AppLayout.tsx`: remove the `/agent` nav entry (`nav.agents`);
  drop the now-unused `nav.agents` i18n key.

**`services/api/`** (agent subsystem):
- routes: `agent_conversations.py`, `internal_agent.py` (its docstring: exists only to
  back the `agent` service's deep-computation callbacks — dies with it; **confirm no
  other caller in step 1**).
- client: `clients/agent_service_client.py`.
- services: `agent_conversation_service.py`, `agent_action_service.py`,
  `agent_attachment_service.py`.
- repositories: `agent_conversation_repository.py`, `agent_message_repository.py`,
  `agent_run_repository.py`, `agent_tool_call_repository.py`,
  `agent_action_proposal_repository.py`.
- schemas: `agent_conversation.py`, `agent_context_snapshot.py` (**confirm agent-only**).
- `main.py`: unmount `agent_conversations_router` + `internal_agent_router`.
- `config.py`: remove `agent_service_url`, `agent_turn_timeout_seconds`, the six
  `agent_*_collection` fields, and `resolved_agent_service_url()`.
- all corresponding tests.

**`services/agent/`** — the entire service directory.

**infra / config:**
- `docker-compose.yml`: remove the `agent:` service block; remove `agent` from the
  `api` service's `depends_on`; remove `AGENT_SERVICE_URL` + `AGENT_TURN_TIMEOUT_SECONDS`
  from the `api` env. (prod/atlas compose + CI already have **no** agent reference —
  verified.)
- `.env.example`: remove `AGENT_SERVICE_PORT`, `AGENT_TURN_TIMEOUT_SECONDS`.
- `.CLAUDE/settings.local.json`: drop the vestigial `services/agent` test-path allowlist
  entries (cosmetic).

### SALVAGE before deleting

- `services/agent/eval_sets/*.json` (eval_cases, paraphrase, set2, thresholds,
  full_architecture_lab) and the 51 KB `README.md` — check for eval cases or design
  notes worth porting to `services/ai` first.
- Mongo collections `agent_conversations/messages/runs/steps/tool_calls/action_proposals`
  are orphaned **data** (not code) — decide separately whether to drop them; a code
  teardown leaves them harmlessly unused.

### Phase B — ordered execution (fresh session, per-service commits)

1. **AUDIT.** Confirm `internal_agent.py`'s endpoints have no non-agent caller; confirm
   `agent_context_snapshot`/schemas are agent-only; confirm the api boots with the
   `agent_*` config fields removed (nothing else reads them).
2. **WEB** first (self-contained): delete the agent UI files + the `App.tsx`/`AppLayout`
   route/nav edits; `npm run build` + typecheck green. Commit.
3. **API**: delete the agent routes/client/services/repos/schemas + `main.py`/`config.py`
   edits + tests; api suite green. Commit.
4. **COMPOSE/ENV**: edit `docker-compose.yml` + `.env.example`; `docker compose config`
   validates; bring the stack up **without** `agent` and smoke `/advisor` end-to-end. Commit.
5. **SERVICE**: delete `services/agent/` (after salvage). Commit.
6. Full monorepo test pass; `graphify update .`.

### Phase B — risk notes (do-not-break list)

- The KEEP list is load-bearing: the live `/advisor` page shares the "advisor" name but
  **not** the agent code — do not remove `AdvisorPage`/`advisorApi`/`advisor.py`/
  `ai_advisor_client`.
- Delete per-service in separate commits (web → api → compose → service) so any breakage
  is bisectable and the live `/advisor` path is provable green at each step.
