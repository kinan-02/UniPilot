# UniPilot AI — Specialist Router & Planner Split

Last updated: 2026-07-14

## Motivation

The `agent_core` pipeline is: Request Understanding → Planner → Orchestrator loop
→ per-step Task Handler → specialist subagents → Monitor → Synthesis. The Task
Handler is a **mini-orchestrator of specialists**: it does not use tools itself;
it decides *which specialist type(s)* execute a step and how their outputs chain.

The concept is sound; the **implementation** overloaded one component. A single
`PlannerReasoningBlock` (+ council) served two genuinely different jobs:

1. **Top-level planning** — decompose the user's *request* into a graph of
   sub-goals (from Request Understanding).
2. **Nested decomposition** — decompose *one complex step* into a pipeline of
   specialist subagents.

Evidence the sharing hurt:

- `_planner_nested_contract()` is `_planner_contract().model_copy(...)` — it
  inherits **all ~30 top-level instructions verbatim**, only swapping the intro.
- The nested path receives `sub_asks=[]`, `implies_action_request=False`, so a
  large block of the inherited prompt is about fields that are *structurally
  always empty* for it — pure dilution.
- The prior fix (`council_enabled=False` for nested) was a boolean that means
  "this caller is really a different component" — the classic overloaded-
  abstraction smell.
- A full-turn live eval showed the flagship case ("Can I take Algorithms next
  semester?") spending **71 of 128 LLM calls on planner-council critics**, mostly
  from nested rounds; and each nested sub-step was **re-classified** by a second
  `classify_and_prep` call.

## Decisions (locked)

- **Fork A — top-level planner becomes specialist-agnostic.** It plans WHAT
  (sub-goals + inter-sub-goal data dependencies); it stops pre-splitting for
  specialist types. Specialist-routing knowledge moves to the router.
- **Fork B — merge classification and nested decomposition into one Specialist
  Router.** "Atomic vs. complex" is a cardinality question about specialist
  *types*: one type ⇒ atomic; a pipeline of types with data handoff ⇒ complex.
  Classification is decomposition at N=1.

## Key design refinements

1. **The router is one-shot + bounded repair, not a multi-round council.** A
   well-scoped step's specialist pipeline is statically determinable
   (GPA = retrieval→calculation; policy = retrieval→interpretation). The router
   emits the whole typed pipeline in ONE call; only *failure* is uncertain and is
   handled by bounded repair rounds. Genuinely content-adaptive branching
   escalates to the top-level planner (partial/failed entry), never inside the
   router.
2. **Clarification stays a top-level concern.** The router routes; if it cannot,
   that is a failure that escalates. It never emits `blocked_needs_clarification`.
3. **Shared knowledge is already `build_shared_grounding_block()`** (entity
   shapes / real fields) — both planner and router use it. Specialist-routing
   rules are router-only. Minimal duplication risk.
4. **`council_enabled` and the whole `planner_nested_v1` contract are deleted.**
   The nested path no longer calls the planner/council at all.
5. **Per-sub-step re-classification is deleted.** Each pipeline sub-step already
   names its specialist, so the second `classify_and_prep` per sub-step is gone.
6. **The router's specialist model is rendered from the roster** so it cannot
   drift from what specialists actually do — the single load-bearing anti-drift
   decision. Requires a new `RoleDefinition.routing_capability` field.

## Target architecture

```
Orchestrator ──(coarse sub-goal + graph)──► Task Handler
   plans WHAT (specialist-AGNOSTIC)            routes HOW (which specialists)
        │                                            │
        ▼                                            ▼
Top-level Planner (council)              Specialist Router (one-shot + repair)
   grounding block                          grounding block
   + request-level planning rules           + roster-derived capability catalog
                                            + routing rules
                     ╲                      ╱
                      ►  SHARED, unchanged ◄
      output schema · rewrite_step_ids · compute_plan_graph ·
      dispatch_layer_concurrently · _dispatch_single_specialist ·
      build_subagent_context_package · success_check · Monitor · Synthesis
```

## Component spec — Specialist Router

**Home:** new `services/ai/app/agent_core/orchestrator/specialist_router.py`
(replaces `task_handler_classify_and_prep.py`).

**Input:** one `PlanStep` (objective + success_criteria + depends_on) + the
dependency context (parent deps), same as `classify_and_prep_step` today.

**Output schema** `specialist_pipeline_v1`:

```json
{ "pipeline": [
  { "sub_step_id": "s1", "specialist": "retrieval",
    "objective": "Fetch the student's completed courses and grades.",
    "depends_on": [], "success_criteria": ["completed courses with grades returned"],
    "specific_instructions": [], "context_requirements": [] },
  { "sub_step_id": "s2", "specialist": "calculation_validation",
    "objective": "Compute cumulative GPA from the completed courses.",
    "depends_on": ["s1"], "success_criteria": ["cumulative GPA computed"] }
] }
```

- `specialist` ∈ the 5 `RoleName`s. **Atomic ⇒ one element.**
- **Fails closed** to a single `retrieval` sub-step mirroring the parent
  objective (safe default; the outer Monitor still verifies and can trigger a
  top-level replan).
- The pipeline reuses `compute_plan_graph` → `execution_layers`, dispatched via
  the existing `dispatch_layer_concurrently` + `_dispatch_single_specialist`.
  Each sub-step becomes a `PlanStep` carrying a new optional
  `assigned_specialist: RoleName | None = None` (top-level `PlanStep` leaves it
  `None`).

**Prompt** = grounding block + roster-derived specialist catalog + routing rules.
The catalog is rendered deterministically from the roster:

```
SPECIALISTS (route each sub-step to exactly one):
- retrieval — fetches existing records / searches the KB. CANNOT derive values
  or interpret prose meaning. Tools: get_entity, search_knowledge,
  get_course_profile, get_policy_answer, get_track_requirements,
  get_current_semester …
- interpretation — reads/explains the MEANING of fetched prose (policy
  implications, requirement-fulfillment). CANNOT compute numbers. Tools:
  interpret_text, get_policy_answer …
- calculation_validation — DERIVES numeric/boolean results from already-fetched
  facts (GPA, standing, credit totals). CANNOT fetch or interpret prose. Tools:
  apply_deterministic_rule, extract_temporal_pattern.
- simulation_planning — what-if / eligibility / audit composites. Tools:
  simulate_course_disruption, check_eligibility, audit_graduation_progress …
- composition — writes the answer from handed-in facts. Zero tools.
```

The "does / CANNOT" sentence comes from `RoleDefinition.routing_capability`; the
tool list from `tool_grant_ceiling`.

**Executor** (in `task_handler.py`, replacing `_run_nested_subplan`): route →
execute the pipeline layer-by-layer (each sub-step: `_dispatch_single_specialist`
+ `success_check`) → all pass ⇒ aggregate into one `StateEntry` with a
`nested_trace`; a sub-step fails ⇒ bounded repair round (re-route with the
unmet-criteria context) up to `max_rounds`; still failing ⇒ partial/failed entry
→ outer Monitor → top-level replan. The atomic fast path is the length-1
pipeline — same call cost as today's `classify_and_prep`.

## Fork A — specialist-agnostic top-level planner

Principle: **planner decides WHAT (sub-goals + inter-sub-goal data deps); router
decides HOW (specialists).** From `_planner_contract()`:

- **Move to the router** (specialist-routing knowledge): GPA-is-derived →
  calculation; requirement-fulfillment → interpretation; program-credit-
  requirement → interpretation; get_current_semester → retrieval (never a
  "compute next semester" calc step); entity-single-fetch mechanics.
- **Stays** (request-level): sub_asks joint planning, constraints threading,
  open_questions → clarification, confidence → verify-early,
  implies_action_request → propose-action, depends_on completeness at sub-goal
  level, no-branching-in-one-batch, don't-re-fetch-conclusively-absent,
  unresolvable_entities, hypothetical-needs-current-state.
- **Reframe:** "write each objective precisely enough to tell what KIND of work
  it is" → "…precisely enough to be routable/decomposable."

Parallelism is unaffected: the sequential pairs the planner used to split
(fetch→compute) were never parallel; independent sub-goals still parallelize at
the loop level.

## Implementation phases (TDD; each phase independently green)

### Phase 1 — Roster capability model
**Goal:** a roster-derived specialist catalog, no behavior change.
- Add `RoleDefinition.routing_capability: str`.
- Fill all 5 roles in `roster.py` with concise "does / CANNOT / hands off"
  statements.
- Add `render_specialist_catalog(roster)` helper.
- **Exit criteria:** unit tests (catalog names every role, includes tool grants,
  reflects the field); full non-live suite green.

### Phase 2 — Router core
**Goal:** `route_step()` produces a typed pipeline.
- New `specialist_router.py`: `specialist_pipeline_v1` schema, router contract
  (grounding + catalog + routing rules), reasoning block, `route_step()`.
- Fail-closed to a single retrieval sub-step.
- **Exit criteria:** unit tests — atomic→1 step; GPA→retrieval+calculation;
  policy→retrieval+interpretation; eligibility/audit→single simulation_planning;
  malformed→fail-closed. Suite green.

### Phase 3 — Rewire the Task Handler
**Goal:** task handler uses the router; nested planner gone.
- Add `assigned_specialist` to the pipeline step representation.
- Replace `classify_and_prep_step` + `_run_nested_subplan` with `route_step` +
  the pipeline executor. Delete per-sub-step re-classification.
- Reuse `_dispatch_single_specialist` / `success_check` / Monitor unchanged.
- **Exit criteria:** `test_orchestrator_task_handler.py` migrated; suite green.

### Phase 4 — Trim the planner + delete dead weight
**Goal:** clean separation, less prompt, no dead code.
- Move/trim planner instructions per Fork A.
- Delete `_planner_nested_contract` / `NESTED_PLANNER_V1`.
- Delete `council_enabled` from `run_planner_council` / `build_next_plan_steps`.
- Retire the dead `thinking_enabled/reasoning_effort/timeout` params in
  `build_next_plan_steps`, `loop.py`, and `reasoning_effort.py`.
- **Exit criteria:** planner/council/skeleton/e2e tests updated; suite green.

### Phase 5 — Verify + measure
**Goal:** prove it, not on faith.
- Full non-live `agent_core` suite green.
- Isolated live re-runs (call-count is throttle-independent) of a complex case
  (e.g. case_05, which timed out) and case_04.
- Record: calls/complex-step (router replaces classify_and_prep + nested-draft +
  N×per-sub-step-classify), routing accuracy (spot-check pipelines in the trace),
  final-answer correctness, nested round-counts.

#### Phase 5 outcome (what the live runs actually taught us)

1. **Repair loop thrash.** The first cut kept a per-step repair/re-route loop.
   case_04 measured 109 calls -> TIMEOUT: 8 distinct steps but 18 router calls,
   because a failing atomic step just re-produced the SAME single specialist.
   Fix: **removed the task-handler repair loop** — a routed pipeline runs ONCE;
   failures escalate to the Monitor (which sees the whole plan). case_04 ->
   81 calls / 250s, passing.

2. **Fork A was a net regression.** Even without the repair loop, the
   specialist-agnostic planner over-decomposed (15 top-level steps) and produced
   coarse, hard-to-satisfy criteria (~50% success-check failures -> replan
   churn). **Reverted Fork A** (restored the planner's specialist-aware
   step-scoping guidance). The Specialist Router (Fork B) is kept.

3. **Expanded the council with a Parsimony Critic** (4th critic): flags
   redundant / over-decomposed steps so plans stay tight. It runs in parallel
   with the other three (no added latency, +1 call per full-council invocation),
   and pays for itself many times over in fewer downstream dispatches.

4. **Substance-over-shape verification.** The success-check + router/planner
   criteria now target OUTCOMES, not exact data shapes/field names — killing the
   false-negative check failures that drove replan churn.

**Final measured state (call-count is the throttle-independent metric):**
| case | pre-refactor | final |
|------|-------------|-------|
| case_01 (simple) | 20 calls | **18 calls**, correct answer |
| case_04 (complex/ambiguous) | 47 calls | **48 calls, 7 steps (was 15), 83% check-pass (was 50%)** |

Net: performance-neutral vs the pre-refactor baseline, with a cleaner
architecture (planner/router separation, roster-derived routing, no
`council_enabled` flag) and a smarter planner (parsimony critic → tighter
plans). Remaining orthogonal issue: an inherently-ambiguous entity ("Algorithms")
can exhaust the planner-invocation budget without composing an answer or asking
to clarify — a pre-existing ambiguity-handling gap, not caused by this refactor.

## Untouched (blast radius)

`loop.py` dispatch structure, the top-level council, `context_builder`,
`to_dependency_view`, Monitor, Synthesis, all 5 specialist blocks, and the
output/graph/rewrite pipeline.

## Risks & mitigations

- **Capability catalog wrong → bad routing.** Mitigated by roster-derivation, the
  fail-closed default, and outer-Monitor re-verification.
- **More steps go "complex" under specialist-agnostic planning.** Acceptable —
  routing is now one cheap call, not a council loop.
- **`test_orchestrator_task_handler.py` migration is non-trivial.** Called out;
  done as part of Phase 3.
