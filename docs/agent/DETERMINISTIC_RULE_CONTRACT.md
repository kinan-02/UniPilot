# Deterministic rule contract

Defines the `rule` argument shape for `apply_deterministic_rule(rule, facts)`
([`AGENT_VISION.md` §5](AGENT_VISION.md), primitive 6). Like
[`SIMULATION_STATE_CONTRACT.md`](SIMULATION_STATE_CONTRACT.md), nothing else
in the codebase defines a "rule" shape — in production, `rule` would
eventually come from a future `interpret_text` call (Group 4, not yet
implemented) reading the applicable wiki regulation; this doc is that
contract's producer-agnostic consumer side. **Update this doc whenever the
rule vocabulary changes.**

## Design principle: fail closed harder than the other primitives

Per §5.1, `apply_deterministic_rule` is one of only two primitives (with
`interpret_text`) that must return a real "cannot determine" outcome instead
of a best-guess default. Concretely here that means: a `facts` key the rule
references being **entirely absent** is `ok=False` ("we don't have this
data"); a `facts` key present as an **empty list** is a real, computable
answer (e.g. "zero completed courses" → sum is legitimately `0`) — these are
different states and must not collapse into the same behavior.

## `rule` shape

Discriminated by `rule["type"]` (runtime-validated `str`, not `Literal` —
same extensibility rationale as every other primitive's vocabulary field).
Three types, chosen to cover AGENT_VISION's own named examples ("credit
totals, academic-standing checks") without building a general expression
language:

| `rule["type"]` | Fields | Computes |
|---|---|---|
| `sum_threshold` | `source, field, filter?, comparator, threshold` | Sums `field` across every record in `facts[source]` matching `filter` (if given), compares the sum to `threshold` |
| `count_threshold` | `source, filter?, comparator, threshold` | Counts records in `facts[source]` matching `filter` (if given), compares the count to `threshold` |
| `field_comparison` | `source, field, comparator, threshold` | Compares a single scalar value at `facts[source][field]` to `threshold` (no aggregation — `facts[source]` is a dict here, not a list) |

- `filter` (when present) is a plain `{field: value}` equality map — a
  record must match every key exactly to be included. No inequality/range
  filters in v1; add a new `rule["type"]` rather than overloading `filter`
  if that's ever needed (keeps the fail-closed logic simple to audit).
- `comparator` ∈ `{">=", ">", "<=", "<", "==", "!="}`.
- Example `sum_threshold` rule + facts (a credit-total graduation check):
  ```json
  {
    "rule": {
      "type": "sum_threshold",
      "source": "completedCourses",
      "field": "credits",
      "filter": {"status": "completed"},
      "comparator": ">=",
      "threshold": 130
    },
    "facts": {
      "completedCourses": [
        {"courseNumber": "00440105", "credits": 3.5, "status": "completed"}
      ]
    }
  }
  ```

## Output shape (`ToolOutputEnvelope.data`)

- `sum_threshold`: `{"type": "sum_threshold", "sum": <number>, "comparator": ..., "threshold": ..., "satisfied": <bool>, "matchedCount": <int>}`
- `count_threshold`: `{"type": "count_threshold", "count": <number>, "comparator": ..., "threshold": ..., "satisfied": <bool>}`
- `field_comparison`: `{"type": "field_comparison", "value": <number>, "comparator": ..., "threshold": ..., "satisfied": <bool>}`

`certainty.basis` is always `"official_record"` — this primitive only ever
computes over facts it was handed, never interprets or predicts; the
computation itself introduces no additional uncertainty beyond whatever the
input facts already carried (which is the *caller's* job to track via its
own certainty tags on those facts, not this primitive's).

## Fail-closed error vocabulary

- `rule_type_required` / `unknown_rule_type: <type>`
- `<field>_required` — a required rule field is missing (e.g. `source_required`, `comparator_required`, `threshold_required`)
- `unknown_comparator: <value>`
- `facts_source_missing: <source>` — `facts[source]` key doesn't exist at all (distinct from an empty list/dict, which is a valid answer)
- `facts_source_wrong_shape: <source>` — e.g. `sum_threshold`/`count_threshold` require a list at `facts[source]`, `field_comparison` requires a dict
- `non_numeric_field_value: <source>.<field>` — a matched record's field isn't a number (for `sum_threshold`/`field_comparison`)

## Status

- `apply_deterministic_rule` (`services/ai/app/agent_core/tools/primitives/apply_deterministic_rule.py`) — implements all 3 rule types above.
