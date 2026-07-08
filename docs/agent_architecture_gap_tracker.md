# Agent Architecture Gap Tracker

Phase 28.2 audit follow-up. Tracks intentional deferrals and resolved gaps.

## 1. Supervisor parallel dispatch

| Field | Value |
| --- | --- |
| Status | Not implemented |
| Risk | Latency only — independent subtask branches run sequentially |
| Priority | Later performance phase |
| Notes | `graph.py` Phase 6 and `runtime.py` walk `topological_order()` one subtask at a time. Architecture doc prefers concurrent dispatch for independent branches. |

## 2. Synthesis feedback loop into orchestrator

| Field | Value |
| --- | --- |
| Status | Post-hoc only |
| Risk | Synthesis cannot request extra evidence or clarification before final answer generation |
| Priority | Future architecture phase |
| Notes | `build_synthesis_input` consumes finished summaries; `run_synthesis_diagnostics` is a one-way sink. Requires call-graph change. |

## 3. Clarification batching

| Field | Value |
| --- | --- |
| Status | Single-question default; flag-gated batching available |
| Risk | Chained user interruptions when batching disabled |
| Priority | Medium |
| Notes | `AGENT_CLARIFICATION_BATCHING_ENABLED=false` preserves legacy single-question behavior. When enabled, up to `AGENT_CLARIFICATION_MAX_QUESTIONS_PER_TURN` compatible questions may be combined. Diagnostics report `deferredQuestionCount`. |

## 4. Monitor→Planner signal fidelity

| Field | Value |
| --- | --- |
| Status | Fixed in Phase 28.2 |
| Risk | Wrong repair vs regeneration choice when signals collapse |
| Priority | High (resolved) |
| Notes | `exhausted_path` now maps to `PlanDeltaKind.exhausted_path`. `choose_repair_mode` distinguishes exhausted strategy from ordinary subtask failure. |

## 5. Replan cycle bound

| Field | Value |
| --- | --- |
| Status | Partially implemented in Phase 28.2 |
| Risk | Unbounded repair loop across turns |
| Priority | High before broader promotion |
| Notes | `ReplanCycleBudget` and `apply_replan_cycle_bounds` enforce same-turn diagnostic bounds (`AGENT_REPLAN_MAX_REPAIRS_PER_GOAL=2`, `AGENT_REPLAN_MAX_REGENERATIONS_PER_GOAL=1`). Cross-turn persistence is not yet wired. |

## 6. Promotion readiness manifest operations

| Field | Value |
| --- | --- |
| Status | Audit tooling added in Phase 28.2 |
| Risk | Promotion blocked without a reviewed manifest at the configured path |
| Priority | Operational — run before any promotion attempt |
| Notes | Use `python scripts/audit_promotion_readiness.py --workflow <wf> --manifest <path> --candidate <id>`. Report-only; promotion remains off by default. |
