# UniPilot Agent Service (V1 — RETIRED)

> **Historical reference only.** This is the design README of the retired
> `services/agent` conversational-agent service, salvaged verbatim before that
> service was deleted in the V1 teardown (2026-07-18). The live conversational
> path is now the V2 agent loop in `services/ai` — see
> [AGENT_ARCHITECTURE_V2.md](AGENT_ARCHITECTURE_V2.md). Nothing described below
> is running; paths like `services/agent/...` and the `/agent` page no longer
> exist. Kept for the design rationale it records.

Internal-only conversational agent service: intent classification, context
retrieval (Mongo + wiki RAG), the shared LLM reasoning runtime, the Task
Understanding Agent, and all workflow execution for the `/agent`
conversation experience. Never exposed to the host — `api` is the only
client-facing entry point.

## How it fits together

```
Browser (/agent)
  → api (auth, rate limiting, conversation CRUD, action confirm/reject)
      → agent  (POST /turn, internal-only, X-Internal-Service-Token)
          - intent → entities → context → workflow → response
          - streams SSE events back through api, unchanged
```

`api`'s `agent_conversation_service.stream_message_turn` persists the
incoming user message, then forwards the turn to this service's `POST /turn`
and streams its raw SSE response straight back to the client — `api` never
re-parses or re-serializes the events.

## Data access

This service has its **own direct MongoDB connection** (same database as
`api`):

- **Read-only** (by convention — no write methods are used) on shared
  academic/student collections: `courses`, `course_offerings`,
  `degree_programs`, `degree_requirements`, `catalog_rules`,
  `completed_courses`, `student_profiles`, `semester_plans`.
- **Full read/write** on its own collections: `agent_conversations`,
  `agent_messages`, `agent_runs`, `agent_steps`, `agent_tool_calls`,
  `agent_action_proposals`.
- It **never** writes to student-owned data directly. Workflows only ever
  create an `agent_action_proposals` document; `api`'s existing
  confirm/reject routes perform the actual write (save a plan, commit a
  transcript import) against that same collection.

A small number of internal HTTP endpoints on `api`
(`app/routes/internal_agent.py`, protected by `X-Internal-Service-Token`)
back computation that intentionally stays exclusively in `api` to avoid
duplicating complex, actively-evolving business rules also used by `api`'s
plain REST endpoints:

- `GET /internal/agent/graduation-audit/users/{id}` — graduation audit engine
- `POST /internal/agent/semester-plan-options/users/{id}` — semester plan generation
- `GET /internal/agent/course-requirement-contribution` — pool/matrix requirement matching
- `GET /internal/user-context/users/{id}` — canonical per-student summary (pre-existing endpoint, reused)

## Capability Registry + Context Compiler (Phase 4)

`app/agent/capabilities/` and `app/agent/context_compiler/` are two
foundational, purely deterministic packages (no database access, no LLM
calls) that prepare for a future Planner Agent — they do **not** change any
live routing or response behavior today.

- **`build_default_capability_registry()`** (`capabilities/default_registry.py`)
  returns a typed catalog describing the 6 live workflows, 10 future
  specialist-agent placeholders (only `task_understanding_agent` is
  `enabled=True` today — the other 9 are Phase 5+ placeholders), the
  existing deterministic `context_validator`/`response_composer`, and the
  tools/retrieval/internal-API capabilities the live path already uses.
  Every capability declares an explicit `CapabilityPermissionScope`
  (read/write scope, allowed collections/endpoints) and
  `CapabilityContextContract` (which context sections it may see).
- **`capabilities/source_of_truth.py`** defines an explicit 9-level trust
  hierarchy (`deterministic_api_business_rules` is most trusted,
  `llm_interpretation` least) with `get_source_of_truth_rank` /
  `compare_source_trust` / `is_higher_trust` helpers, for a future
  validator to resolve conflicting data.
- **`context_compiler.compile_context_for_capability(request, registry=...)`**
  takes a large `ContextCompilationRequest` and a target capability name and
  returns a `CompiledContext` containing only the context sections that
  capability's contract allows — forbidden sections (full catalog dumps,
  full transcript rows, attachment contents, raw PDF bytes, raw Mongo
  documents) are always stripped unless a capability explicitly opts in,
  with a compact warning recorded for every omission.
- **Optional diagnostic hook**: when `AGENT_TASK_UNDERSTANDING_ENABLED=true`
  (the existing Phase 3 flag — no new flag was added), the orchestrator also
  attaches a compact `capabilityDiagnostics` summary to
  `agent_runs.retrievalMetadata`, alongside the Phase 3 `taskUnderstanding`
  summary. This never affects workflow selection, the response, or the SSE
  event sequence — see `tests/integration/test_capability_diagnostics.py`.

See `docs/agent/CURRENT_STATE.md` → "Capability Registry + Context Compiler
— Phase 4" for full details.

## Planner Agent (Phase 5)

`app/agent/planner/` adds `PlannerAgent` (`build_execution_plan`) — a
diagnostic agent that converts the Phase 3 `TaskUnderstandingOutput` into a
structured, capability-aware execution plan (a task graph: subtasks,
dependencies, required context sections, success criteria, validation
requirements, write/confirmation risk), instead of the current hardcoded
`intent -> workflow` mapping. It is **diagnostic/dry-run only** — it never
executes a subtask, tool, or workflow, and `task_planner.py`'s deterministic
`intent -> workflow` mapping still fully controls production routing.

- Uses `ReasoningBlock` exclusively (contract `planner_agent_v1`, risk
  `high`, 3 reasoning passes) — never calls an LLM directly.
- `planner/normalizer.py` treats the LLM's plan as untrusted input:
  capability names must exist and be **enabled** in the `CapabilityRegistry`
  (an unknown or disabled/placeholder capability's subtask is dropped, never
  invented), subtask ids must be unique, dependencies must reference
  existing subtasks and form an acyclic graph (cycle detection via DFS), and
  explicit write/save/import subtasks always force user confirmation.
- Falls back to a deterministic single-subtask plan mirroring the *current*
  `task_planner.py` selection whenever the flag is off, the LLM is
  unavailable, reasoning fails, or the LLM's plan can't be normalized into
  something usable — the planner never leaves the caller without a plan.
- Uses `context_compiler.compile_context_for_capability` to *preview*
  (never execute) what each planned subtask's capability contract would
  actually let through — included/omitted sections and warnings only, never
  the raw compiled context.
- Optional diagnostic hook: when `AGENT_PLANNER_ENABLED=true` (a new,
  independent flag — not the Phase 3 flag), the orchestrator attaches a
  compact `plannerDiagnostics` summary to `agent_runs.retrievalMetadata`.
  This never affects workflow selection, the response, or the SSE event
  sequence — see `tests/integration/test_planner_diagnostics.py`.

See `docs/agent/CURRENT_STATE.md` → "Planner Agent — Phase 5" for full
details.

## Supervisor Orchestrator Runtime (Phase 6)

`app/agent/supervisor/` adds a runtime that takes a normalized
`PlannerOutput` (Phase 5) and executes its subtask graph **mechanics** —
dependency ordering, per-subtask context compilation, handler dispatch,
blackboard updates, retries/budgets, compact diagnostics — as a controlled
**shadow run**. It never executes a real workflow, calls a real internal
API, writes to Mongo, or creates an action proposal; every built-in
handler is a safe dry-run stand-in. Real capability execution is Phase 7
work.

- `graph.py`'s `ExecutionGraph` validates unique subtask ids, dependency
  references, and cycles (rejecting a broken plan with a typed error
  rather than executing it), then produces one deterministic,
  dependency-respecting sequential execution order.
- `blackboard.py`'s `SupervisorBlackboard` stores only compact, sanitized
  summaries — the same deterministic sanitizer the Phase 4 `ContextCompiler`
  uses is applied to every subtask result before it's stored, so a
  misbehaving handler can't smuggle raw context, chain-of-thought, or large
  documents onto the blackboard.
- `handlers.py`/`handler_registry.py` provide three built-in handlers
  (`DryRunCapabilityHandler`, `ContextPreviewHandler`,
  `UnsupportedCapabilityHandler`) resolved by capability name/type — Phase
  7 can register real handlers by capability name (which takes priority)
  without changing the registry's interface.
- `controller.py`'s `decide_next_action` is a small, deterministic
  (no-LLM) decision function: continue / retry / skip_dependents /
  fail_run, based on the subtask's result and the run's budget.
- `budgets.py`'s `BudgetTracker` enforces `max_subtasks`,
  `max_retries_per_subtask`, `max_total_retries`, `max_runtime_ms`, and
  `max_context_previews`; exceeding any of them stops the run safely as
  `status="budget_exceeded"`.
- Uses `context_compiler.compile_context_for_capability` per subtask but
  only ever stores a compact preview (included/omitted sections, warnings,
  estimated items) — never the raw compiled context.
- Optional diagnostic hook: when `AGENT_SUPERVISOR_ENABLED=true` (a new,
  independent flag), the orchestrator attaches a compact
  `supervisorDiagnostics` summary to `agent_runs.retrievalMetadata`, but
  only once Phase 5's planner diagnostics actually produced a plan. This
  never affects workflow selection, the response, or the SSE event
  sequence — see `tests/integration/test_supervisor_diagnostics.py`.

See `docs/agent/CURRENT_STATE.md` → "Supervisor Orchestrator Runtime —
Phase 6" for full details.

## Real Capability Handlers / Workflow Adapters (Phase 7)

`app/agent/supervisor/workflow_adapters.py` adds `ReadOnlyWorkflowAdapterHandler`
— a handler that executes a **real**, already-live deterministic workflow
(via the same `workflows.registry.get_workflow` lookup the orchestrator
uses) for shadow diagnostics only. Every candidate workflow was manually
read and reviewed before being marked safe:

- **Safe to shadow-execute** (never write to Mongo, never create an
  `agent_action_proposals` document): `graduation_progress_workflow`,
  `course_question_workflow`, `requirement_explanation_workflow`,
  `general_academic_workflow`.
- **Never shadow-executed** (call `create_agent_action_proposal(...)` on
  every successful run): `transcript_import_workflow`,
  `semester_planning_workflow`. These always get an explicit `"skipped"`
  result with a `shadow_execution_not_safe_for_capability` warning.

- `app/agent/capabilities/schemas.py`'s `CapabilityDescriptor` gained an
  `execution: CapabilityExecutionMetadata` field (conservative by default —
  nothing is executable or safe by omission); `default_registry.py` sets it
  explicitly, only after that manual review, for the 6 workflow
  capabilities above.
- `app/agent/supervisor/safety.py`'s `can_shadow_execute_capability(...)` is
  the single fail-closed gate — checked by the runtime every time a
  workflow-type capability is about to run, regardless of how the handler
  registry was built.
- `app/agent/supervisor/output_summarizer.py` converts a real
  `AgentResponse` into a compact summary (text preview, block
  count/types, warning/source/proposed-action counts) — never the full
  response, full blocks, or raw proposed-action payloads.
- `app/agent/supervisor/shadow_compare.py` is a standalone, tested,
  deterministic live-vs-shadow comparison utility — implemented but **not
  yet wired** into any live/diagnostic path (Phase 8 follow-up).
- New setting `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` (default `false`).
  When `false`, behavior is identical to Phase 6. When `true`, safe
  read-only workflows may be shadow-executed **if** a populated
  `SupervisorRuntimeContext` (real database + real `AgentContextPack`) is
  supplied — the live orchestrator's own diagnostic call site
  deliberately does **not** supply one yet (context-building happens after
  that call site in the live turn; reordering it was judged riskier than
  deferring — see `docs/agent/CURRENT_STATE.md`), so today this flag alone
  changes nothing about a live turn. The infrastructure is fully
  implemented and tested end-to-end against a real mongomock database.

See `docs/agent/CURRENT_STATE.md` → "Real Capability Handlers / Workflow
Adapters — Phase 7" for full details.

## Supervisor Shadow Compare + Validation (Phase 8)

Phase 8 wires the Phase 7 real-handler infrastructure into the live turn —
safely — via a **post-context hook**, and adds a deterministic layer that
validates the resulting live-vs-shadow comparison. Still fully diagnostic:
supervisor output never affects the final response, workflow selection, or
the SSE event sequence.

- `app/agent/supervisor/post_context_runner.py`'s
  `run_post_context_shadow_compare` is called from `orchestrator.py` **after**
  the live workflow already produced its `AgentResponse` (unlike Phase 6/7's
  earlier diagnostic call, a real `database` + `AgentContextPack` both exist
  at this point), so it can build a genuinely populated
  `SupervisorRuntimeContext` and let Phase 7's real read-only handlers
  actually execute.
- Gated by `AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED` (default
  `false`) — off by default, zero extra DB/workflow/LLM work when disabled.
- `app/agent/supervisor/shadow_compare.py` gained
  `build_comparison_summary(...)` — a run-level (not just single-capability)
  live-vs-shadow comparison: block type sets/counts, warning counts,
  proposed-action counts, source counts, shadow status, and which
  capabilities (if any) looked like an unsafe real execution attempt.
- `app/agent/supervisor/validation.py`'s `validate_shadow_run(...)` runs 6
  deterministic (no-LLM) validators over that comparison: no shadow proposed
  actions, no unsafe capability execution, block-type/count mismatches
  (warning-only), proposed-action count mismatches (fails), warning-count
  mismatches (warning-only), and shadow run failure/budget-exceeded. Gated
  by `AGENT_SUPERVISOR_VALIDATION_ENABLED` (default `false`) — when off, a
  comparison may still be attached, but with `status="skipped"`.
- `app/agent/supervisor/compare_diagnostics.py`'s
  `build_supervisor_validation_metadata(...)` produces the compact dict
  attached to `agent_runs.retrievalMetadata.supervisorValidation` — status,
  `safeToPromote` (diagnostic-only, always conservative, never read
  anywhere else), block type lists/counts, and a capped issue list — never
  the raw workflow response, raw compiled context, or raw prompts.
- `general_academic_workflow` (safe, but may call an LLM through the
  existing `ReasoningBlock` path) is excluded from real post-context
  execution by default via a new, orthogonal
  `CapabilityExecutionMetadata.operationally_expensive_for_shadow_execution`
  flag — checked by `runtime._select_handler` independently of
  `runtime_context` availability, so no flag combination introduces a new
  LLM call from this path.
- Unsafe/proposal workflows (`transcript_import_workflow`,
  `semester_planning_workflow`) are still refused real execution by Phase
  7's existing safety gate; validation passes when they are correctly
  skipped and fails loudly if that gate is ever bypassed.

See `docs/agent/CURRENT_STATE.md` → "Supervisor Shadow Compare + Validation
— Phase 8" for full details.

## Controlled Supervisor Promotion (Phase 9)

Phase 9 adds a narrow, off-by-default experiment that lets a validated
supervisor candidate response actually become the turn's final answer — for
exactly one workflow, with the legacy deterministic response always
computed first and always the fallback on any uncertainty.

- **Hard-restricted to `graduation_progress_workflow`.**
  `app/agent/supervisor/promotion.py`'s `eligible_promotion_workflows(settings)`
  intersects a hardcoded single-workflow set with whatever
  `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` is configured to — misconfiguring
  that setting can only ever narrow eligibility further, never add another
  workflow.
- New settings: `AGENT_SUPERVISOR_PROMOTION_ENABLED` (default `false`),
  `AGENT_SUPERVISOR_PROMOTION_MODE` (`off` | `shadow_only` |
  `promote_validated`, default `off`), `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS`.
- `promotion.evaluate_promotion_decision(...)` is the single deterministic
  gate: requires Phase 8 validation to be `status="passed"` +
  `safe_to_promote=True`, zero proposed actions on both sides, exactly
  matching block types/counts, no unsafe capability anywhere in the
  supervisor run, no forbidden raw/chain-of-thought-shaped diagnostic key,
  and a full in-memory candidate `AgentResponse` that itself passes
  `check_candidate_response_safety` (type-correct fields, valid blocks, no
  forbidden payload, exact block type/count match against the live
  response). Never raises — any unexpected input degrades to
  `status="failed"`.
- `workflow_adapters.ReadOnlyWorkflowAdapterHandler` gained an optional
  `candidate_sink` parameter (`None` by default, zero behavior change for
  every other caller) so `post_context_runner.py` can capture the full
  in-memory candidate response only when promotion could plausibly apply —
  which additionally requires `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true`
  (a candidate can only ever come from a genuinely real execution).
- `orchestrator.py`: the live workflow still always runs first; only when
  `evaluate_promotion_decision` returns `promoted=True` does the in-memory
  candidate replace the live response *before* the exact same
  finalize/persist/emit path Phase 1–8 already used — no new SSE event
  types, no schema changes, no change to confirm/reject behavior.
- Compact `agent_runs.retrievalMetadata.supervisorPromotion` metadata:
  `status`, `promoted`, `workflowName`, `mode`, a capped `reasons` list
  (`code`/`severity` only) — never the raw candidate/live response.

See `docs/agent/CURRENT_STATE.md` → "Controlled Supervisor Promotion — Phase
9" for full details.

## Specialist Agent Wrappers (Phase 10)

`app/agent/specialists/` adds the first real specialist-agent layer —
structured, `ReasoningBlock`-powered workers the supervisor runtime can call
for a subtask, instead of just a dry-run stand-in or a full workflow
adapter. Still fully shadow-only: specialist output never affects the final
response, workflow selection, or the Phase 9 promotion gate.

- **Three read-only specialists implemented:** `graduation_progress_agent`,
  `course_catalog_agent`, `requirement_explanation_agent` — each a thin
  wrapper around the shared `specialists.base.run_specialist_reasoning`
  helper, calling the LLM only through `ReasoningBlock` with its own prompt
  contract (`specialist_graduation_progress_v1` /
  `specialist_course_catalog_v1` / `specialist_requirement_explanation_v1`
  in `reasoning/prompt_registry.py`) and JSON output schema
  (`reasoning/task_schemas.py`).
- **Never implemented (deliberately out of scope):**
  `transcript_import_agent`, `semester_planning_agent`, and any future
  `action_proposal_agent`/`profile_update_agent` — these may involve writes
  or proposed actions.
- `SpecialistAgentOutput.proposed_actions` is forced to `[]` by the model's
  own field validator, unconditionally — no specialist can ever actually
  return a proposed action, and a raw LLM result that somehow carried one
  anyway is stripped with a `specialist_proposed_actions_blocked` warning
  before that model is even constructed.
- Falls back to a fixed, deterministic `status="skipped"` output (never
  raises) whenever specialist agents are disabled, `ReasoningBlock` fails,
  or the LLM is unavailable — no `OPENAI_API_KEY` is required for this
  fallback path.
- `app/agent/specialists/supervisor_handler.py`'s `SpecialistAgentHandler`
  is the new `SubtaskHandler` the supervisor runtime resolves for these
  three capability names — it independently re-checks
  `specialists.safety.is_specialist_agent_safe` (defense in depth, mirroring
  Phase 7's `ReadOnlyWorkflowAdapterHandler`/`safety.py` pattern), builds a
  compact `SpecialistAgentInput` from the subtask + compiled context +
  blackboard dependency outputs, and stores only a compact summary
  (`specialists.output_summarizer.summarize_specialist_output`) — never the
  raw compiled context, raw prompts, or chain-of-thought.
- `app/agent/capabilities/default_registry.py`'s three specialist
  descriptors are now `enabled=True` with `type="specialist_agent"`
  execution metadata (`side_effect_level="none"`,
  `handler_name="specialist_agent_handler"`) — the Planner Agent (Phase 5,
  LLM-driven, off by default) may now legitimately choose one of them in a
  plan; this is safe because supervisor output remains diagnostic-only and
  promotion (Phase 9) is restricted to `graduation_progress_workflow` (the
  workflow), never `graduation_progress_agent` (the specialist).
- New settings `AGENT_SPECIALIST_AGENTS_ENABLED` (default `false`) and
  `AGENT_SPECIALIST_AGENTS_DRY_RUN` (default `true`) — unlike the Phase 7
  real-workflow-adapter flag, the specialist capability names are *always*
  registered with `SpecialistAgentHandler`; the enabled flag is checked
  inside the handler itself.

See `docs/agent/CURRENT_STATE.md` → "Specialist Agent Wrappers — Phase 10"
for full details.

## Specialist Output Validation + Compare (Phase 11)

Phase 10 added specialist agents but never checked their output against
anything. Phase 11 adds a deterministic validation and comparison layer —
still fully diagnostic, still never affecting the final response.

- `app/agent/specialists/validation.py`'s `validate_specialist_output(...)`
  runs 7 deterministic validators (no proposed actions, no forbidden raw/
  chain-of-thought-shaped payload, confidence in range, valid status, no
  missing context, non-empty result, conservative scope-violation
  detection) over either a real `SpecialistAgentOutput` or its compact
  summary dict — never raises, never calls an LLM.
- `app/agent/specialists/compare.py`'s `compare_workflow_and_specialist(...)`
  structurally compares a live workflow's `AgentResponse` against a
  comparable specialist's summary, using a fixed, diagnostic-only mapping
  (`graduation_progress_workflow` ↔ `graduation_progress_agent`,
  `course_question_workflow` ↔ `course_catalog_agent`,
  `requirement_explanation_workflow` ↔ `requirement_explanation_agent`) —
  `general_academic_workflow`/`transcript_import_workflow`/
  `semester_planning_workflow` are never comparable in Phase 11.
- `app/agent/specialists/diagnostics.py` scans an already-computed
  `SupervisorRunOutput` for specialist-agent subtask results, validates and
  (when enabled) compares each, and builds the compact
  `agent_runs.retrievalMetadata.specialistValidation` dict — never the raw
  specialist result, raw live response, or raw context.
- Wired into `supervisor/post_context_runner.py` (not a new call site) —
  only runs when `AGENT_SPECIALIST_VALIDATION_ENABLED` and/or
  `AGENT_SPECIALIST_COMPARE_ENABLED` are `true`, and only when specialist
  subtask results actually exist in that turn's shadow run (which itself
  only happens when the — LLM-driven, off-by-default — Planner Agent chose
  a specialist capability). Never modifies `selected_response`, never adds
  an SSE event.
- New settings `AGENT_SPECIALIST_VALIDATION_ENABLED` / `AGENT_SPECIALIST_COMPARE_ENABLED`
  (both default `false`). Purely deterministic — no `OPENAI_API_KEY` needed.
- `safe_to_consider` remains diagnostic-only, exactly like Phase 8/9's
  `safe_to_promote` — specialist output is not promotable in Phase 11.

See `docs/agent/CURRENT_STATE.md` → "Specialist Output Validation + Compare
— Phase 11" for full details.

## Specialist Tool Observation Layer (Phase 12)

Phase 10 left `SpecialistAgentInput.deterministic_observations` permanently
empty. Phase 12 adds `app/agent/specialists/tools/` — a deterministic,
bounded, read-only observation-gathering step a specialist can consult
before its `ReasoningBlock` call. Still fully shadow-only: observations
never affect the final response, workflow selection, or the Phase 9
promotion gate.

- Read-only specialist observations exist for 10 kinds: `profile_summary`,
  `completed_courses_summary`, `graduation_audit_summary`,
  `requirement_bucket_summary`, `course_catalog_summary`,
  `prerequisite_summary`, `offering_summary`,
  `requirement_contribution_summary`, `wiki_snippet_summary`,
  `conversation_assumption_summary` — each with a fixed, per-specialist
  allowlist (`specialists/tools/registry.py`).
- Observations are deterministic and bounded: built only from data already
  in memory (an already-built `AgentContextPack`, the specialist's own
  `compiled_context`, or already-computed `dependency_outputs`) — never a
  new database/internal-API call, never a rebuilt context, never an
  unbounded list (`ObservationDescriptor.max_summary_items` + a hard
  `max_observations` cap, fail-closed to `20` regardless of configuration).
- Observations can be passed into specialist agents via
  `SpecialistAgentInput.deterministic_observations` (the existing Phase 10
  `SpecialistToolObservation` model, which gained one new, safely defaulted
  `status` field) — only when `AGENT_SPECIALIST_OBSERVATIONS_ENABLED=true`;
  when `false`, behavior is byte-for-byte Phase 10/11 (the list stays `[]`).
- Observations are shadow-only: only `SpecialistAgentHandler` (the existing
  Phase 10 `SubtaskHandler`) builds and passes them; nothing in the live
  `/turn` path, public API, or promotion gate reads them.
- No raw observation data is stored in diagnostics — `SubtaskResult.output_summary`
  only ever gains 4 compact keys (`observationCount`, `observationNames`,
  `observationWarningCount`, `missingObservationCount`), never a raw
  per-observation `summary` dict.
- No writes/action proposals are possible — `ObservationDescriptor` has no
  write-capable fields at all (every descriptor is `read_only=True`/
  `side_effect_level="none"` by construction), and
  `safety.sanitize_observation_payload` additionally strips any
  `proposed_action_payload`-shaped key defensively.
- Final answers remain controlled by the existing deterministic
  path/promotion gate — Phase 9 promotion is still hard-restricted to
  `graduation_progress_workflow` (the workflow), never any specialist agent
  name, observations or not.
- New settings `AGENT_SPECIALIST_OBSERVATIONS_ENABLED` (default `false`) and
  `AGENT_SPECIALIST_OBSERVATION_MAX_COUNT` (default `8`). Purely
  deterministic — no `OPENAI_API_KEY` needed, even when enabled.

See `docs/agent/CURRENT_STATE.md` → "Specialist Tool Observation Layer —
Phase 12" for full details.

## Specialist Tool-Request Loop (Phase 13)

Phase 12 gave specialists deterministic observations but no way to ask for
more. Phase 13 adds a bounded, read-only tool-request loop on top of the
same Phase 12 observation registry — still fully shadow-only.

- When a specialist's `ReasoningBlock` pass returns `status="needs_tool"`
  and `AGENT_SPECIALIST_TOOL_LOOP_ENABLED=true`, its `tool_requests` are
  validated (`specialists/tools/tool_requests.py`) against the existing
  Phase 12 `SpecialistObservationRegistry` — only a real, registered,
  read-only observation already allowed for that specialist can ever be
  approved.
- Approved requests are built through the existing Phase 12
  `observation_builder.build_specialist_observations` (`specialists/tools/tool_loop.py`)
  — no second observation system, no new database/internal-API call, no
  rebuilt context, no LLM call from the loop itself.
- Bounded by construction: at most
  `min(AGENT_SPECIALIST_TOOL_LOOP_MAX_ROUNDS, 2)` rounds (default `1`) and
  `min(AGENT_SPECIALIST_TOOL_LOOP_MAX_REQUESTS_PER_ROUND, 8)` requests per
  round (default `4`) — both hard ceilings independent of configuration.
- There is no arbitrary tool namespace: a request is only ever "approved",
  "rejected", or "unavailable" against the fixed observation registry —
  never a function call, never a write, never a proposed action.
- Diagnostics (`specialists/tools/tool_loop_diagnostics.py`) are compact —
  observation *names* and counts only, never raw tool-request arguments or
  raw observation content — folded into the same `SubtaskResult.output_summary`
  Phase 10/11/12 already use, never into `agent_runs.retrievalMetadata`
  directly.
- When `AGENT_SPECIALIST_TOOL_LOOP_ENABLED=false` (the default), behavior is
  byte-for-byte Phase 12 — a `needs_tool` result degrades to the same Phase 10
  fallback as before Phase 13 existed.
- New settings: `AGENT_SPECIALIST_TOOL_LOOP_ENABLED` (default `false`),
  `AGENT_SPECIALIST_TOOL_LOOP_MAX_ROUNDS` (default `1`, hard-capped at `2`),
  `AGENT_SPECIALIST_TOOL_LOOP_MAX_REQUESTS_PER_ROUND` (default `4`,
  hard-capped at `8`).

See `docs/agent/CURRENT_STATE.md` → "Specialist Tool-Request Loop — Phase 13"
for full details.

## Controlled Specialist Text Promotion (Phase 14)

Phase 10–13 kept specialist output fully diagnostic — nothing it produced
could ever reach a student. Phase 14 opens one narrow, strictly-gated door:
`graduation_progress_agent`'s own generated explanation text may replace
`AgentResponse.text` — never anything else.

- Only `response.text` can ever be promoted. `blocks`, `warnings`,
  `sources`/`used_sources`, and `proposed_actions` always come from the live
  deterministic `graduation_progress_workflow`, unchanged
  (`specialists/text_promotion.build_text_promoted_response` copies the live
  response and replaces only `text`).
- Only `graduation_progress_agent` is eligible, hard-restricted regardless
  of `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` configuration
  (`specialists/text_promotion.eligible_text_promotion_agents`) — the other
  two specialists (`course_catalog_agent`, `requirement_explanation_agent`)
  and any write/proposal specialist can never be promoted.
- Promotion requires every one of ~20 strict gates to pass
  (`specialists/text_promotion.evaluate_specialist_text_promotion`): the
  existing Phase 11 specialist validation/comparison must have passed
  cleanly and been marked `safeToConsider`/`safeMatch`, the specialist
  output must be `"completed"` with confidence ≥ 0.85, zero missing
  context, zero proposed actions, no Phase 13 tool-loop budget overrun, a
  present and safe `answer_text`
  (`specialists/answer_text_safety.check_answer_text_safety` — rejects
  empty/too-long text, forbidden raw-payload markers, and write-claim
  phrases like "I updated"/"I saved"/"I imported"), and the live response
  itself must have zero proposed actions and at least one block.
- Always defers to Phase 9 workflow promotion: if a workflow candidate was
  already promoted for this turn, text promotion is blocked with
  `workflow_promotion_already_selected_response` — the two promotion
  systems never modify the same turn independently.
- No second specialist pass is ever run for this experiment — it reuses the
  exact same post-context shadow supervisor run Phase 8/11 already make,
  capturing the specialist's full in-memory output via an optional sink on
  the existing `SpecialistAgentHandler` (mirrors Phase 9's own
  `candidate_sink` pattern on `ReadOnlyWorkflowAdapterHandler`).
- Diagnostics (`retrievalMetadata.specialistTextPromotion`) are compact —
  `status`, `promoted`, `mode`, `workflowName`, `specialistAgentName`, and
  capped `reasons` (`code`/`severity` only) — never the promoted answer
  text, raw specialist result, raw observations, or raw workflow response.
- New settings (all off/conservative by default):
  `AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED` (default `false`),
  `AGENT_SPECIALIST_TEXT_PROMOTION_MODE` (default `off`; `off` |
  `shadow_only` | `promote_validated`), `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS`
  (default `graduation_progress_agent`, intersected with the hardcoded
  ceiling), `AGENT_SPECIALIST_TEXT_PROMOTION_MAX_CHARS` (default `4000`).

See `docs/agent/CURRENT_STATE.md` → "Controlled Specialist Text Promotion —
Phase 14" for full details.

## Dynamic AgentSpec + Block Library + Builder — Phase 15

Phase 15 adds a configuration-driven dynamic sub-agent foundation:

- **`AgentSpec`** — structured spec describing role, objective, reasoning
  pattern, allowed blocks/observations, context contract, validation policy,
  and budget (`shadow_only` must stay `true`).
- **`TaskBrief`** — self-contained task context for one dynamic agent run.
- **`BlockLibrary`** — fixed, inspectable, read-only blocks (context filter,
  reasoning, observation loop, validation, synthesis, summarization, etc.).
- **`AgentBuilder`** — deterministic, non-generative assembler; never calls
  an LLM or executes the agent during build.
- **`DynamicAgentInstance`** — shadow-only runtime that executes a fixed block
  sequence via `ReasoningBlock` (`dynamic_agent_v1` prompt contract only).
- **`DynamicAgentHandler`** — supervisor handler for `dynamic_agent`
  subtasks / optional `PlannerSubtask.dynamic_agent_spec`; diagnostic only.
- Dynamic agents **cannot write**, **cannot create proposed actions**, and
  **do not affect final answers** (compact `retrievalMetadata.dynamicAgents`
  diagnostics only).
- New settings (all off/conservative by default):
  `AGENT_DYNAMIC_AGENTS_ENABLED` (default `false`),
  `AGENT_DYNAMIC_AGENTS_DRY_RUN` (default `true`; misconfigured `false` still
  forces shadow-only with a warning).

See `docs/agent/CURRENT_STATE.md` → "Dynamic AgentSpec + Block Library +
Builder — Phase 15" for full details.

## Monitor + Plan Assumption Tracking + Replan/Repair Signals — Phase 16

Phase 16 adds a deterministic Monitor layer:

- **`PlanAssumption`** — falsifiable assumptions with provenance and invalidation signals.
- **`SubtaskExpectation`** — expected subtask outcomes (no writes/proposals, confidence, custom criteria).
- **`DivergenceSignal`** — expected-vs-actual divergence classification.
- **`ReplanDecision`** — recommended control action (continue, local retry, ask clarification, request plan repair, …).
- **`monitor_plan_execution`** — compares assumptions/expectations against supervisor shadow results; never calls an LLM.
- Monitor is **diagnostic-only** — does not change final answers, does not trigger real replanning.
- Compact diagnostics attach to `retrievalMetadata.monitorDiagnostics`.
- New settings: `AGENT_MONITOR_ENABLED=false`, `AGENT_MONITOR_DRY_RUN=true`.

See `docs/agent/CURRENT_STATE.md` → "Monitor + Plan Assumption Tracking +
Replan/Repair Signals — Phase 16" for full details.

## Clarification as a First-Class Capability — Phase 17

Phase 17 adds deterministic clarification infrastructure:

- **`ClarificationNeed`** — explicit need with preference vs epistemic ambiguity and consequence.
- **`ClarificationDecision`** — consequence-aware ask / assume / resolve / skip policy.
- **`ClarificationQuestion`** / **`ClarificationAnswer`** — compact prompts and provenance-tagged answers.
- **`clarification_capability`** — registered read-only capability; no LLM, no writes, no proposals.
- Default mode is **diagnostic-only** — attaches `retrievalMetadata.clarificationDiagnostics` without changing final answers.
- New settings: `AGENT_CLARIFICATION_ENABLED=false`, `AGENT_CLARIFICATION_USER_FACING_ENABLED=false`, `AGENT_CLARIFICATION_MAX_QUESTIONS=3`.

See `docs/agent/CURRENT_STATE.md` → "Clarification as a First-Class Capability —
Phase 17" for full details.

## Cross-Turn Clarification State — Phase 18

Phase 18 adds cross-turn clarification state and user-facing flow (off by default):

- **`PendingClarificationState`** / **`ResolvedClarificationState`** — agent-owned clarification lifecycle models.
- **`ClarificationStateRepository`** — persists pending/answered/expired state in `agent_clarification_states` only.
- **`resolve_clarification_answer`** — deterministic answer matching (options, numbers, cancel phrases).
- Turn start resolves pending clarifications before intent classification; unresolved answers return a normal reminder response.
- User-facing mode (`AGENT_CLARIFICATION_USER_FACING_ENABLED=true`) can ask a clarification question and persist pending state for the next turn.
- Confirmed answers use `provenance="confirmed"`; expired fallbacks use `provenance="assumed"`.
- New settings: `AGENT_CLARIFICATION_MAX_PENDING_TURNS=3`, `AGENT_CLARIFICATION_STATE_ENABLED=true`.

See `docs/agent/CURRENT_STATE.md` → "Cross-Turn Clarification State — Phase 18" for full details.

## Warm Planner Invocation + Plan Repair Foundation — Phase 19

Phase 19 adds warm planner repair diagnostics (off by default):

- **`PlanSnapshot`** / **`PlanExecutionDelta`** / **`PlanRepairRequest`** / **`PlanRepairOutput`** in `app/agent/planner/`.
- Deterministic repair policy + fallback (`deterministic_plan_repair`) and optional `planner_repair_v1` ReasoningBlock path.
- **`build_effective_clarification_context`** injects compact confirmed-clarification metadata when enabled.
- Attaches **`retrievalMetadata.planRepairDiagnostics`** in dry-run; repaired plans do not affect final answers yet.

New settings: `AGENT_PLAN_REPAIR_ENABLED=false`, `AGENT_PLAN_REPAIR_DRY_RUN=true`, `AGENT_PLAN_REPAIR_USE_LLM=false`, `AGENT_CLARIFICATION_EFFECTIVE_CONTEXT_ENABLED=false`.

See `docs/agent/CURRENT_STATE.md` → "Warm Planner Invocation + Plan Repair Foundation — Phase 19" for full details.

## Dynamic Planner AgentSpec Emission — Phase 20

Phase 20 lets the Planner emit validated `AgentSpec` configurations on subtasks (off by default):

- Planner may attach `dynamic_agent_spec` to read-only subtasks when `AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=true`.
- Specs are validated with Phase 15 rules; invalid specs are stripped with compact rejection diagnostics.
- Valid specs execute in shadow via `DynamicAgentHandler` when `AGENT_DYNAMIC_AGENTS_ENABLED=true`.
- Attaches **`retrievalMetadata.plannerDynamicAgents`**; does not change final answers.

New settings: `AGENT_PLANNER_DYNAMIC_SPECS_*` (see `.env.example`).

See `docs/agent/CURRENT_STATE.md` → "Dynamic Planner AgentSpec Emission — Phase 20" for full details.

## Synthesis / Final Answer Composer — Phase 21

Phase 21 reconciles workflow, specialist, dynamic-agent, monitor, clarification, and plan-repair summaries into a diagnostic synthesis candidate (off by default):

- **`AGENT_SYNTHESIS_ENABLED=false`** — no synthesis diagnostics attached.
- When enabled, builds compact `SynthesisInput`, ranks evidence, detects conflicts, and runs deterministic (or optional ReasoningBlock) synthesis.
- Attaches **`retrievalMetadata.synthesisDiagnostics`**; does **not** change final answers.

New settings: `AGENT_SYNTHESIS_*` (see `.env.example`).

See `docs/agent/CURRENT_STATE.md` → "Synthesis / Final Answer Composer — Phase 21" for full details.

## Controlled Synthesis Text Promotion — Phase 22

Phase 22 may replace **only `response.text`** with a validated synthesis candidate when explicitly enabled:

- Default mode is **`off`** — no behavior change.
- **`shadow_only`** evaluates promotion gates and attaches **`retrievalMetadata.synthesisPromotion`** without changing the response.
- **`promote_validated`** replaces text only when all strict gates pass; blocks/warnings/sources/proposed_actions remain from the deterministic workflow.
- Candidate text is never stored in diagnostics.

New settings: `AGENT_SYNTHESIS_TEXT_PROMOTION_*` (see `.env.example`).

See `docs/agent/CURRENT_STATE.md` → "Controlled Synthesis Text Promotion — Phase 22" for full details.

## Offline Replay + Evaluation Harness — Phase 23

Offline evaluation for autonomous agent behavior gates (diagnostic-only; no production changes):

```bash
cd services/agent
.venv/bin/python scripts/run_agent_replay_eval.py \
  --cases tests/fixtures/eval_cases \
  --mode gates_only \
  --output /tmp/unipilot-agent-eval-report.json \
  --markdown /tmp/unipilot-agent-eval-report.md
```

- **`gates_only`** (default): deterministic gate checks from sanitized fixture summaries — no LLM, no DB, no orchestrator.
- **`shadow_replay`**: partial replay with fake `ReasoningBlock` outputs + synthesis promotion policy.
- Fixtures: `tests/fixtures/eval_cases/` — structured expected behavior + synthetic oracles (not answer similarity).
- Optional `--allow-real-llm` marks reports non-deterministic; do not use in CI/tests.

See `docs/agent/CURRENT_STATE.md` → "Offline Replay + Evaluation Harness — Phase 23".

## Eval-Guided Promotion Readiness — Phase 24

Offline promotion-readiness scorecards from eval suites (report-only; no production changes):

```bash
cd services/agent
.venv/bin/python scripts/run_agent_promotion_readiness.py \
  --cases tests/fixtures/eval_cases \
  --suites tests/fixtures/eval_suites \
  --mode gates_only \
  --output /tmp/unipilot-agent-readiness.json \
  --markdown /tmp/unipilot-agent-readiness.md
```

- Suite manifests group cases by purpose (regression, write safety, synthesis promotion, etc.).
- Nine default promotion candidates map to required suites and readiness thresholds.
- Outputs readiness levels, blocking reasons, and compact policy-hardening recommendations.
- Does **not** auto-edit `.env` or widen live promotion.

See `docs/agent/CURRENT_STATE.md` → "Eval-Guided Promotion Readiness — Phase 24".

## Runtime Readiness Gate + Controlled Broader Read-Only Promotion — Phase 25

Runtime gate requiring a human-reviewed activation manifest before promotion (disabled by default):

```bash
# Build a draft manifest from an offline readiness report (does not modify .env)
cd services/agent
.venv/bin/python scripts/build_promotion_activation_manifest.py \
  --readiness-report /tmp/unipilot-agent-readiness.json \
  --candidate synthesis_text_promotion.course_question_workflow \
  --level ready_for_limited_promotion \
  --reviewed-by "manual-review" \
  --output /tmp/promotion_readiness_manifest.json
```

Enable at runtime (explicit opt-in only):

```bash
AGENT_RUNTIME_READINESS_GATE_ENABLED=true
AGENT_RUNTIME_READINESS_MANIFEST_PATH=/path/to/promotion_readiness_manifest.json
```

- Gate **disabled** → Phase 9/14/22 promotion behavior unchanged.
- Gate **enabled** → promotion additionally requires manifest approval; fails closed when manifest missing/malformed/stale.
- Readiness scorecards do **not** auto-enable promotion.
- Text-only read-only promotion only; write workflows remain blocked; no action proposals.

Example manifest: `config/promotion_readiness_manifest.example.json`

See `docs/agent/CURRENT_STATE.md` → "Runtime Readiness Gate + Controlled Broader Read-Only Promotion — Phase 25".

## Real-World Case Import + Full LLM Shadow Replay Lab — Phase 26

Import anonymized real-world cases and run full-stack shadow replay in lab mode:

```bash
# Import anonymized cases (strict scanner, dry-run supported)
cd services/agent
.venv/bin/python scripts/import_real_world_eval_cases.py \
  --input /tmp/anonymized-real-cases.jsonl \
  --output-dir /tmp/unipilot-real-world-eval-cases \
  --strict \
  --dry-run

# Full LLM shadow replay (requires explicit --allow-real-llm)
.venv/bin/python scripts/run_agent_replay_eval.py \
  --cases tests/fixtures/eval_cases_real_world_like \
  --mode full_llm_shadow_replay \
  --allow-real-llm \
  --max-cases 5 \
  --max-reasoning-calls 50 \
  --output /tmp/unipilot-full-llm-shadow-report.json \
  --markdown /tmp/unipilot-full-llm-shadow-report.md
```

- Real LLM requires `--allow-real-llm`; default modes unchanged.
- Side-effect firewall blocks writes and action proposals during lab replay.
- Reports include reasoning contract summaries — not prompts/raw outputs.
- Production behavior is unchanged.

See `docs/agent/CURRENT_STATE.md` → "Real-World Case Import + Full LLM Shadow Replay Lab — Phase 26".

## Golden-Set Final Answer Evaluation — Phase 27 / 28.1

Wiki-ground-truth final-answer evaluation against `eval_sets/eval_cases.json` (25 cases), the paraphrase regression set `eval_sets/eval_cases_paraphrase.json` (8 cases), and the broader academic set `eval_sets/eval_cases_broader_academic.json`.

**Wiki mount is required** when bind-mounting only `services/agent` into the container — otherwise `CATALOG_VAULT_WIKI_PATH` points at an empty `/app` tree and catalog lookups fail.

### Fast deterministic regression (Phase 28.1)

Skips live LLM task understanding, planner, and orchestrator for wiki-grounded academic cases. Use for day-to-day regression on the broader set:

```bash
cd services/agent

docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases.json \
  --agent-mode deterministic_fast \
  --judge-mode deterministic \
  --require-mongo \
  --output /app/tmp/eval-fast.json \
  --markdown /app/tmp/eval-fast.md
```

### Full live sample (profiling subset)

```bash
docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases.json \
  --max-cases 5 \
  --agent-mode full_live \
  --allow-real-llm \
  --judge-mode deterministic \
  --require-mongo \
  --output /app/tmp/eval-full-sample.json \
  --markdown /app/tmp/eval-full-sample.md
```

### Full live with concurrency and trace-on-failure

```bash
docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases.json \
  --agent-mode full_live \
  --allow-real-llm \
  --judge-mode deterministic \
  --require-mongo \
  --concurrency 2 \
  --trace-on-failure \
  --trace-failure-dir /app/tmp/final_answer_eval_failed_traces \
  --output /app/tmp/eval-full-concurrent.json \
  --markdown /app/tmp/eval-full-concurrent.md
```

### Standard full-live final-answer eval (golden set)

```bash
cd services/agent

docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases.json \
  --agent-mode full_live \
  --allow-real-llm \
  --judge-mode deterministic \
  --require-mongo \
  --output /app/tmp/unipilot-final-answer-eval.json \
  --markdown /app/tmp/unipilot-final-answer-eval.md
```

### Eval CLI options (Phase 28.1)

| Flag | Purpose |
|------|---------|
| `--agent-mode deterministic_fast` | Wiki-grounded path without live LLM agent |
| `--agent-mode full_live` | Full MAS stack (default; requires `--allow-real-llm`) |
| `--max-cases N` | Profile or sample a subset |
| `--concurrency N` | Run up to 4 cases in parallel (stable report order) |
| `--trace-on-failure` | Write detailed traces only for failed/partial/errored cases |
| `--thresholds eval_sets/eval_thresholds.json` | Fail CI when quality regresses |
| `--fail-on-threshold-violation` | Exit non-zero on threshold breach |

Reports include per-case `timing`, aggregate `timingSummary`, `llmCallCount`, and `wikiCacheStats`.

### Trace-enabled eval (all cases)

```bash
docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases.json \
  --agent-mode full_live \
  --allow-real-llm \
  --judge-mode deterministic \
  --require-mongo \
  --trace-dir /app/tmp/final_answer_eval_traces \
  --trace-level detailed \
  --output /app/tmp/unipilot-final-answer-eval.json \
  --markdown /app/tmp/unipilot-final-answer-eval.md
```

### Paraphrase anti-overfit eval

```bash
docker compose run --rm \
  -v "$(pwd):/app" \
  -v "$(pwd)/../data-engineering/data/catalog_valut/catalog_valut/wiki:/app/data/academic/wiki:ro" \
  -e CATALOG_VAULT_WIKI_PATH=/app/data/academic/wiki \
  -e MONGO_URI="mongodb://unipilot:unipilot_dev_password@mongo:27017/unipilot_python?authSource=admin" \
  agent \
  python scripts/run_final_answer_eval.py \
  --cases eval_sets/eval_cases_paraphrase.json \
  --agent-mode full_live \
  --allow-real-llm \
  --judge-mode deterministic \
  --require-mongo \
  --output /app/tmp/unipilot-final-answer-eval-paraphrase.json \
  --markdown /app/tmp/unipilot-final-answer-eval-paraphrase.md
```

### Unit regression tests (no Docker)

```bash
cd services/agent
CATALOG_VAULT_WIKI_PATH="../data-engineering/data/catalog_valut/catalog_valut/wiki" \
  .venv/bin/python -m pytest \
  tests/unit/test_academic_lookup_service.py \
  tests/unit/test_course_question_service.py \
  tests/unit/test_golden_set_regression.py \
  tests/unit/test_final_answer_eval.py \
  tests/unit/test_final_answer_eval_performance.py \
  tests/unit/test_final_answer_trace_logging.py \
  -q --no-cov
```

- Eval is read-only: side-effect firewall blocks writes and action proposals.
- Deterministic catalog/wiki answers skip LLM rewrite when wiki sources are used.
- Regression helpers live in `app/agent/evaluation/regression_assertions.py`.

See `docs/agent/CURRENT_STATE.md` → "Golden-Set Final Answer Evaluation — Phase 27".

## Run tests

```bash
cd services/agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

No `OPENAI_API_KEY` or running `api`/Mongo is required — tests use
`mongomock-motor` for MongoDB and a fake `ReasoningBlock`/mocked
`internal_api_client` calls for anything that would otherwise need the LLM
or a real `api` process.

## Known follow-ups

- Coverage is currently ~78% (below the 80% gate other services enforce) —
  the reasoning/workflow/retrieval/capabilities/context_compiler/planner/
  supervisor core is well covered; `app/main.py`, a few repository edge
  branches, and some catalog-matching code paths still need tests.
- A handful of tests exhibit a few seconds of incidental latency from a
  DNS-resolution attempt to a non-routable hostname during local (non-Docker)
  runs; harmless but worth tightening.
