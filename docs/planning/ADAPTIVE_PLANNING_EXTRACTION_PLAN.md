# Adaptive Planning — Extraction Implementation Plan

Source idea: [`docs/agent/agent_plans/planner_architecture_idea.md`](../agent/agent_plans/planner_architecture_idea.md)
(the "Adaptive Graph Planning Architecture" reference doc).

## 1. Decision & scope

We are **not** adopting the reference architecture wholesale. It is strong on
*principles* and misaligned on several *mechanisms* — some of which we
deliberately rejected already (this repo's planner is specialist-aware and
emits objective-only steps; binding to specialists/tools happens just-in-time
at dispatch, per `SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md`).

We extract **three** things and shelve the rest:

1. **Deterministic validator gate** — lift structural/heuristic checks out of
   LLM critics; surface them as findings that drive critic selection.
2. **Conditional critic selection** — grow the critic *palette* (4 → 6) but
   *activate a subset* per invocation, so per-turn critic cost drops while
   failure-mode coverage rises.
3. **Graded replanning** — the real prize. Replace the "any failure → full
   global replan" behavior with (a) a replan-escalation guard that stops
   re-attempting a dead region, and (b) a scoped replan that repairs only the
   failed region and protects validated work.

### Explicitly OUT of scope (rejected/deferred, do not build)

- **PlanIR with upfront tool/capability binding** (idea §8) — reverses the
  specialist-router decision. Our steps stay objective-only.
- **Capability registry with I/O schemas / historical stats** (idea §6) — this
  is the old fixed-workflow/capability system this module moved away from.
- **Plan-template retrieval / Tier 0** (idea §7) — large new subsystem,
  staleness risk, out of scope for now.
- **Two independent candidate planners + Graph Comparator** (idea §13–14) —
  doubles planning tokens against the 300s ceiling; the council already gives
  diversity, and the new **strategy critic** covers the anti-anchoring motive
  far more cheaply.
- **Risk & Recovery critic** (idea §10.4) — low ROI for a read-mostly advisor;
  leave a slot for when write-heavy flows exist.
- **Transient retry tier** (idea §19.1) — deferred; see §4.3.

### Grounding facts this plan is built on (verified in code)

- `planning/rewrite.py` already does id-rewrite, dangling-dep strip, cycle
  break, hollow-result check, and execution-layer derivation — but silently,
  and *after* the council returns.
- `planning/planner_council.py` runs draft → (gate `_should_run_full_council`)
  → **all 4** critics in parallel → gated synth. Critics:
  `coverage`, `grounding`, `criteria`, `parsimony`.
- `orchestrator/monitor.py::evaluate_step_result` → `continue | replan |
  clarify`; only nested entries get an outer success re-check.
- `orchestrator/loop.py` sets `monitor_flags`/`replan_reason` and re-invokes
  the **whole** planner; state is preserved but the planner re-derives freely.
- `orchestrator/task_handler.py` runs a routed pipeline **once**, no per-step
  repair loop (a repair loop was measured thrashing: 8 steps → 18 routes).
- `StateEntry.status` ∈ `{succeeded, partial, failed}` — **no transient/error
  class**. Subagent LLM calls already retry internally (`max_retries`).
- Anti-thrash already present: `UnresolvableEntityRegistry` (entity dead-ends,
  surfaced as `PlannerInvocationInput.unresolvable_entities`) and the
  `final_round` wrap-up.
- Cost profile: the planner council is <15% of a turn's LLM calls; execution
  (routing + specialists + monitor + **replan cascades**) dominates. This is
  why W3 is the highest-leverage workstream.

---

## 2. Workstream 1 — Deterministic validator gate

New pure module `planning/plan_validator.py`. Runs on the **draft** batch
(`PlanStepDraft`s with local labels) *before* critics, inside
`run_planner_council`. Read-only — it never mutates; `rewrite.py` remains the
authoritative repairer. Its findings drive critic selection (W2).

Because our steps have no typed I/O schemas, the validator is scoped to what
our model actually carries: graph structure + cheap lexical heuristics.

```python
Severity = Literal["structural", "efficiency", "quality", "coverage"]

class ValidatorFinding(BaseModel):
    code: str            # F_DANGLING | F_CYCLE | F_DUP_OBJECTIVE
                         # | F_EMPTY_CRITERIA | F_UNADDRESSED_SUBASK
    severity: Severity
    step_ids: list[str]  # local labels involved (may be empty for coverage)
    detail: str

class ValidatorReport(BaseModel):
    findings: list[ValidatorFinding]
    def codes(self) -> set[str]: ...

def validate_plan_draft(
    drafts: list[PlanStepDraft],
    *, known_global_ids: set[str], planner_input: PlannerInvocationInput,
) -> ValidatorReport: ...
```

Checks (all deterministic, no LLM):

| Code | Severity | Rule |
|------|----------|------|
| `F_DANGLING` | structural | `depends_on` names neither a batch sibling nor a known global id (today: silently dropped by rewrite). |
| `F_CYCLE` | structural | back-edge cycle among batch steps (today: silently broken). |
| `F_DUP_OBJECTIVE` | efficiency | two steps whose normalized objectives exceed a token-overlap threshold. |
| `F_EMPTY_CRITERIA` | quality | a step with empty `success_criteria` (Monitor can't verify it). |
| `F_UNADDRESSED_SUBASK` | coverage | a `sub_ask` with ~zero lexical overlap with any step objective (weak signal only). |

Shared edge-analysis (dangling/cycle detection) is extracted so the validator
and `rewrite.py` agree instead of drifting: factor `_find_dangling` /
`_find_cycles` helpers used read-only by the validator and by rewrite's
repair. Findings are **advisory** — they never block a plan; they route critics
and (optionally, later) inform the synthesizer.

---

## 3. Workstream 2 — Conditional critic selection

### 3.1 Palette 4 → 6

Keep `coverage`, `grounding`, `criteria`, `parsimony`. Add:

- **`STRATEGY_CRITIC_V1`** — anti-anchoring, one narrow job: "is there a
  materially simpler/more direct overall approach? is the plan solving the
  wrong subproblem or over-planning?" This is the cheap, in-council answer to
  the anchoring problem that motivated the (rejected) dual-planner tier.
- **`DOMAIN_CRITIC_V1`** — Technion academic-reasoning correctness: prerequisite
  semantics, credit-bucket / degree-rule logic, semester availability,
  catalog-version consistency; e.g. "does it check prereqs against the
  student's *actual* completed courses and the course's *actual* prereq rules
  rather than assuming?" Grounded via `build_shared_grounding_block()`. **Not**
  a hardcoded rule engine — a critic prompt.

Skip `risk_recovery` (documented slot for future write flows).

### 3.2 Deterministic selector

New pure function (in `planner_council.py` or a small `critic_selector.py`):

```python
def select_critics(
    *, invocation: int, planner_input: PlannerInvocationInput,
    report: ValidatorReport, palette: tuple[str, ...],
    max_active: int = 2,
) -> tuple[str, ...]: ...
```

Signal → critic rules (idea §11, adapted to our signals):

| Signal | Selects |
|--------|---------|
| `F_DANGLING` / `F_CYCLE` / `F_UNADDRESSED_SUBASK` | `coverage` |
| `F_EMPTY_CRITERIA`, or `replan_reason` mentions criteria/unmet | `criteria` |
| `F_DUP_OBJECTIVE` | `parsimony` |
| goal/steps reference grounded entities (course codes, profile fields, semester) | `grounding` |
| goal/sub_asks mention prereq / eligibility / credits / degree / graduation / track | `domain` |
| replan in progress, or `confidence < 0.8`, or high step count | `strategy` |

Then rank by severity and take top `max_active`.

- **Cap:** default 2; allow **3 during a replan** (where correctness matters
  most and we're already paying the round).
- **Floor:** on the *first* invocation, if the selector is empty, default to
  `{coverage, parsimony}` — the two most universally useful checks — so the
  shape-setting round always gets real review.
- Selector is **deterministic** (no LLM) — keeps cost flat, per idea §5/§11.

### 3.3 Wiring into the council

`_should_run_full_council` stays as the *outer* gate (routine continuations
still run draft-only). When it returns `True`, the "run all 4" branch is
**replaced** by: `validate_plan_draft` → `select_critics` → run the selected
0–3 critics in parallel → existing gated synth. Net: palette up, per-turn
critic calls typically **down** (4 → ~2).

---

## 4. Workstream 3 — Graded replanning

Guiding constraint (hard-won): **every replan level must add new information or
change scope, or it thrashes.** We extend the two mechanisms we already have
rather than reinventing them.

### 4.1 W3a — Replan escalation guard (highest value)

Generalizes `UnresolvableEntityRegistry` from *entities* to *steps/regions*.
New turn-scoped `ReplanLedger` (plain mutable collaborator, like the
unresolvable registry; created per turn in `turn.py`, threaded through the
loop):

```python
class ReplanLedger:
    def record(self, step_objective: str, reason: str) -> None: ...
    def attempts(self, step_objective: str) -> int: ...
    def exhausted(self, *, threshold: int = 2) -> list[str]: ...  # objectives
```

- On each Monitor `replan`/`clarify`, `loop.py` records the failing step's
  normalized objective (same `strip().lower()` normalization the unresolvable
  registry uses).
- Before the next planner invocation, pass `exhausted_steps: list[str]` (new
  field on `PlannerInvocationInput`) with the instruction: *"these objectives
  have been attempted repeatedly and still fail — do NOT reschedule equivalent
  work; proceed with what's known (compose around the gap) or, if essential,
  ask the student to clarify."*
- Mirrors `unresolvable_entities` exactly (proven, low-risk). Directly cures
  the general thrash class the Algorithms case was one instance of; layers
  cleanly under the `final_round` last-resort conclude.

### 4.2 W3b — Scoped / subgraph replan (medium value)

Give a replan a **failure locus + protect-list** so the planner repairs only
the failed region instead of re-deriving the whole plan. New optional field:

```python
class ReplanFocus(BaseModel):
    failed_step_ids: list[str]
    protected_step_ids: list[str]   # validated, completed — keep as-is
    unmet_criteria: list[str]

# PlannerInvocationInput.replan_focus: ReplanFocus | None = None
```

- Populated in `loop.py` from the Monitor's decision (the failed step) + the
  completed `succeeded` entries (protected) + threaded `unmet_criteria`.
- Planner instruction: *"Fix ONLY the failed region and its dependents; keep
  every protected step exactly as-is; do not re-emit validated work."* Maps to
  idea §12.2 (protected regions) + §19.3 (subgraph replan). Pure prompt +
  input-field change; reuses the existing planner + preserved state; **no new
  execution machinery.**
- Composes with W3a: the guard decides *when to stop*; the scoped replan makes
  each attempt *tighter and cheaper* (also helps the 300s budget).
- Neither new field feeds `_should_run_full_council` (they're separate from
  `monitor_flags`, avoiding the `final_round` gate-trip bug); a scoped replan
  *is* a replan, which correctly takes the full-council path anyway.

### 4.3 W3-deferred — Transient retry tier (NOT in this cut)

Deferred with reason: `StateEntry` carries no transient/error class (status is
`succeeded/partial/failed` only), and subagent LLM calls already retry
internally, so a step-level retry risks redundancy or masking a semantic
failure. Revisit only if we add a `failure_class` to `SubagentResult`.

---

## 5. Phased execution (TDD, feature-by-feature, commit per phase)

Each phase: write failing tests first (RED) → implement (GREEN) → run the
non-live suite → keep coverage ≥ 80% → commit. Test env:
`services/ai/.venv/bin/python -m pytest -o addopts="" -p no:cacheprovider`,
excluding the live investigation file.

- **Phase 0 — scaffolding, no behavior change.** New `plan_validator.py`
  (types + `validate_plan_draft`), `ReplanLedger`, new `PlannerInvocationInput`
  fields (`exhausted_steps`, `replan_focus`), strategy + domain critic
  contracts registered. Unit tests for each new unit in isolation.
- **Phase 1+2 — W1 validator gate + W2 conditional selection (shipped
  together).** W1 alone has no behavioral effect (the validator's only consumer
  is the selector), so they are one feature. `plan_validator.validate_plan_draft`
  (read-only) + `critic_selector.select_critics` wired into the council's
  review branch, replacing run-all. Validator/rewrite agreement is guarded by
  matching detection rules + tests rather than a risky extraction from rewrite's
  repair-coupled code. Tests: each finding code; signal→critic mapping; cap (2
  default / 3 on replan); first-invocation floor; draft-only path unchanged;
  two real-selector e2e council tests. **Done** — 594 passed, 1 skipped.
- **Phase 3 — W3a escalation guard.** Thread `ReplanLedger` through
  `turn.py`/`loop.py`; populate `exhausted_steps`; planner instruction. Tests:
  a step failing K times appears in `exhausted_steps`; planner is told to
  conclude/clarify; no leak into `monitor_flags`. **Done** — 595 passed.
  Note: keyed by the step's normalized objective text (like the unresolvable
  registry); a heavily-reworded re-attempt can dodge the match -- fuzzy keying
  is a possible follow-up.
- **Phase 4 — W3b scoped replan.** Populate `replan_focus` in `loop.py`;
  planner instruction. Tests: failed + protected ids computed correctly;
  instruction present only on a focused replan.
- **Phase 5 — integration + live re-check.** Full non-live suite green. Live
  re-check on **case_04** (flagship "Can I take Algorithms next semester?") and
  **case_01** (simple), measuring: (a) critic calls/turn (expect ↓ from 4),
  (b) replan rounds on the hard case (expect ↓), (c) no correctness regression.
  Record outcomes in §6.

## 6. Validation & rollout

- Non-live gate each phase; live measurement only at Phase 5 (and rested
  endpoint, since throttling inflates wall-time).
- Success = critic-calls-per-turn down, replan-churn on the hard case down,
  answers still correct, whole suite green, coverage ≥ 80%.
- Outcomes appended here as phases land (mirrors how
  `SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md` recorded its Phase-5 result).

## 7. Files touched (anticipated)

- New: `planning/plan_validator.py`, `orchestrator/replan_ledger.py`
  (+ their tests).
- Edit: `planning/planner_council.py` (palette, selector, gate wiring),
  `planning/planner.py` (strategy/domain contracts if co-located; scoped-replan
  + exhausted-steps instructions), `planning/schemas.py`
  (`exhausted_steps`, `replan_focus`), `planning/rewrite.py` (extract shared
  edge-analysis), `orchestrator/loop.py` (ledger + focus plumbing),
  `orchestrator/turn.py` (create ledger), plus updated tests
  (`test_planner_council.py`, `test_planning_planner.py`,
  `test_orchestrator_loop_parallelism.py`, `test_planning_schemas.py`, new
  `test_plan_validator.py`, `test_critic_selector.py`, `test_replan_ledger.py`).
