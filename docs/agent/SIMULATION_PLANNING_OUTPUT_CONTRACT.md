# Simulation/Planning Output Contract

This document outlines the output contract of the `simulation_planning` role subagent (implemented via `SimulationPlanningReasoningBlock`).

The orchestrator and downstream subagents rely on this structure when parsing results from the `simulation_planning` role.

## Canonical Schema (`simulation_planning_agent_output_v1`)

```json
{
  "type": "object",
  "properties": {
    "certainty_basis": {
      "type": "string",
      "enum": ["hypothetical_simulation", "predicted_pattern"]
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "source_ref": {
      "type": ["object", "null"],
      "properties": {
        "page": { "type": "string" },
        "section": { "type": ["string", "null"] },
        "reasoning_path": { "type": ["string", "null"] }
      },
      "required": ["page"]
    },
    "assumptions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "outcome": {
      "type": "object",
      "description": "The projected plan/state payload produced by mutate_state/search_over_state -- e.g. a semester-by-semester schedule, or a before/after comparison."
    }
  },
  "required": ["certainty_basis", "confidence", "outcome"]
}
```

## Why `certainty_basis` is a restricted enum (unlike Retrieval's or Interpretation's own contracts)

The role's own guardrail — *"Never present a simulated outcome as an official
record"* (`roster.py`) — is absolute: nothing this role produces is ever a
real, official fact, because neither `mutate_state` nor `search_over_state`
touches real persisted state; both operate on a hypothetical in-memory
`base_state`. Restricting the enum to exactly `{hypothetical_simulation,
predicted_pattern}` — excluding `official_record`, `wiki_derived`, and
`llm_interpretation` — turns this from a prompt-level guardrail into a
structural one: a finalize attempt tagging its own result `official_record`
fails schema validation outright, the same "guardrail becomes a
schema constraint" move `INTERPRETATION_OUTPUT_CONTRACT.md`'s required
`source_ref` already made for its own guardrail.

## Field Definitions

1. **`certainty_basis`**: `hypothetical_simulation` for a `mutate_state`-perturbed
   projection; `predicted_pattern` when the outcome leans on a statistical
   prediction (e.g. an `extract_temporal_pattern`-derived offering forecast
   surfaced by `search_over_state`).
2. **`confidence`**: A float between 0.0 and 1.0.
3. **`source_ref`** *(optional, usually absent)*: a simulated projection's
   "source" is tool-computed state, not a single citable wiki page — present
   only if a specific wiki-sourced constraint (e.g. a track's requirement
   list) is worth citing back.
4. **`assumptions`** *(optional)*: e.g. "assumes the course is offered in the
   predicted semester pattern," "assumes no additional failures."
5. **`outcome`**: The actual projected plan/state payload — a free-form
   object, matching `search_over_state`'s own output shape
   (`plan`, `semestersUsed`, `unscheduledCourses`, etc.) or a
   `mutate_state`-perturbed `state` snapshot, depending on what the step
   asked for.

## Fail-closed error vocabulary (`SubagentResult.warnings`)

- `simulation_planning_failed: round_budget_exhausted_no_result` — the
  forced final round produced no `result` at all.
- `simulation_planning_failed: status_ready_but_no_result` — the model
  reported `status="ready"` without populating `result`.
- `simulation_planning_failed: schema_repair_exhausted: <errors>` — the
  finalize result was schema-invalid (most commonly: `certainty_basis` set
  to a disallowed value like `official_record`) and the base class's generic
  schema-repair loop could not recover it.
- `simulation_planning_failed: reasoning_block_failed: <reason>` — an
  unexpected internal error, caught by `BaseReasoningBlock.run()`'s "never
  raises" safety net.

## Worked example

Projecting the impact of failing a course:

1. Round 1: `status="need_tools"`, requests
   `mutate_state(base_state=<current state>, change={"type": "fail_course", "courseNumber": "00440105", "semester": "2024-2"})`.
2. Round 2: `status="need_tools"`, requests
   `search_over_state(state=<perturbed state from round 1>, constraints=[...], objective="minimize_semesters")`.
   If `unscheduledCourses` comes back non-empty (a failed/incomplete
   candidate), a further round may retry with revised constraints — the
   *same* loop, no special "retry" code path.
3. Final round: `status="ready"`, `result={certainty_basis:
   "hypothetical_simulation", confidence: 0.8, assumptions: [...],
   outcome: {semestersUsed: 2, plan: {...}}}`.

## Orchestrator Mapping

When `SimulationPlanningReasoningBlock` returns its result, the orchestrator
maps this schema into the `SubagentResult` object, the same pattern both
existing `*_OUTPUT_CONTRACT.md` docs already document:

- `result.result` -> `outcome`
- `result.certainty.basis` -> `certainty_basis`
- `result.certainty.confidence` -> `confidence`
- `result.certainty.source_ref` -> `source_ref` (usually `null`)
- `result.assumptions` -> `assumptions`

Any downstream subagent relying on `simulation_planning` will see this
projected outcome natively unwrapped in its context via `dependency_state` —
this is what makes "simulate → then re-check requirements against the
simulated state" possible (`AGENT_VISION.md` §8): a later step reads a prior
`simulation_planning` step's `outcome` back out of shared state rather than
recomputing it.

## Status

Implemented in `services/ai/app/agent_core/subagents/simulation_planning_block.py`.
See `docs/agent/agent_plans/SIMULATION_PLANNING_REASONING_BLOCK_PLAN.md` for
the full control-flow design and rationale, including the explicit
doc/code drift note re: `tool_grant_ceiling` not yet including the composite
tools `HIGHER_LEVEL_TOOLS.md` describes.
