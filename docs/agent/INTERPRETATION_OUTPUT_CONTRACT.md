# Interpretation Output Contract

This document outlines the output contract of the `interpretation` role subagent (implemented via `InterpretationReasoningBlock`).

The orchestrator and downstream subagents rely on this structure when parsing results from the `interpretation` role.

## Canonical Schema (`interpretation_agent_output_v1`)

```json
{
  "type": "object",
  "properties": {
    "certainty_basis": {
      "type": "string",
      "enum": [
        "official_record",
        "wiki_derived",
        "predicted_pattern",
        "llm_interpretation",
        "hypothetical_simulation"
      ]
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "source_ref": {
      "type": "object",
      "properties": {
        "page": { "type": "string" },
        "section": { "type": ["string", "null"] },
        "reasoning_path": { "type": ["string", "null"] }
      },
      "required": ["page", "section"]
    },
    "assumptions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "answer": {
      "type": "string",
      "description": "The interpreted answer/rule for the specific question asked, grounded in the cited source."
    }
  },
  "required": ["certainty_basis", "confidence", "source_ref", "answer"]
}
```

## Why `source_ref` is required (unlike Retrieval's own contract)

`RETRIEVAL_OUTPUT_CONTRACT.md`'s `source_ref` is optional, because not every
retrieved fact has one citable page (a Mongo student-record fact has none).
Interpretation's own guardrail — *"must cite the exact wiki page/section
read"* — is absolute: there is no legitimate interpretation result without a
citation. Making `source_ref` a **required** field turns this from a
prompt-level guardrail into a structural one. If no source was ever
successfully interpreted (every `interpret_text` attempt failed or none was
ever called), the finalize step cannot produce a schema-valid result and
correctly fails closed — this is *intended* behavior, not a bug: it is the
mechanical enforcement of "return cannot determine rather than guess."

## Field Definitions

1. **`certainty_basis`**: Almost always `llm_interpretation` for this role
   (the interpretation itself is an LLM reading of prose), matching
   `interpret_text`'s own tool-level certainty convention.
2. **`confidence`**: A float between 0.0 and 1.0.
3. **`source_ref`** *(required)*:
   - `page`: The wiki slug read (e.g. `retake-policy`).
   - `section`: The specific heading/section cited — required (may be `null`
     only if the tool genuinely could not resolve a sub-section, but the page
     itself must always be present).
   - `reasoning_path` *(optional)*: How this source was reached, if resolving
     it required more than one tool call (e.g. `search_knowledge` → `get_entity`
     → `interpret_text`).
4. **`assumptions`** *(optional)*: Any assumptions made when resolving
   ambiguous phrasing in the source text.
5. **`answer`**: The interpreted answer/rule itself — a plain string,
   mirroring `interpret_text`'s own tool-level output shape (`{answer,
   citedSection}`) directly, rather than a speculative structured payload.

## Fail-closed error vocabulary (`SubagentResult.warnings`)

- `interpretation_failed: round_budget_exhausted_no_result` — the forced
  final round produced no `result` at all.
- `interpretation_failed: status_ready_but_no_result` — the model reported
  `status="ready"` without populating `result`.
- `interpretation_failed: schema_repair_exhausted: <errors>` — the finalize
  result was schema-invalid (most commonly: missing `source_ref` because no
  source was ever successfully interpreted) and the base class's generic
  schema-repair loop could not recover it.
- `interpretation_failed: reasoning_block_failed: <reason>` — an
  unexpected internal error, caught by `BaseReasoningBlock.run()`'s "never
  raises" safety net.

Additionally, a round's response may carry free-text entries in its own
`warnings` array (e.g. the gap #5 "cannot confirm absence of a temporary
exception" case) — these are threaded straight into the final
`SubagentResult.warnings` alongside the fail-closed vocabulary above, not
silently dropped.

## Worked example

Interpreting the retake-limit policy for a specific course:

1. Round 1: `status="need_tools"`, requests
   `interpret_text(source="retake-policy", question="How many times can I retake this course?")`.
2. Round 2: `interpret_text` succeeds (`answer="Up to 2 retakes allowed.", citedSection="Retakes"`);
   model finalizes: `status="ready"`, `result={certainty_basis: "llm_interpretation",
   confidence: 0.9, source_ref: {page: "retake-policy", section: "Retakes"},
   assumptions: [], answer: "Up to 2 retakes allowed."}`.

## Orchestrator Mapping

When `InterpretationReasoningBlock` returns its result, the orchestrator maps
this schema into the `SubagentResult` object, the same pattern
`RETRIEVAL_OUTPUT_CONTRACT.md` already documents:

- `result.result` -> `answer`
- `result.certainty.basis` -> `certainty_basis`
- `result.certainty.confidence` -> `confidence`
- `result.certainty.source_ref` -> `source_ref`
- `result.assumptions` -> `assumptions`

Any downstream subagent relying on `interpretation` will see this cited
answer natively unwrapped in its context via `dependency_state`.

## Status

Implemented in `services/ai/app/agent_core/subagents/interpretation_block.py`.
See `docs/agent/agent_plans/INTERPRETATION_REASONING_BLOCK_PLAN.md` for the
full control-flow design and rationale.
