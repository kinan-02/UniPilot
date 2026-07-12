# Calculation-Validation reasoning block & expression-tree implementation plan

**Status: planned, not yet implemented.** This document is the execution-ready plan for two
related changes, designed together in conversation on 2026-07-12 after a live-eval investigation
(see `TOOL_PRIMITIVES_OPEN_GAPS.md`/session history) found the Calculation-Validation role
structurally unable to answer "how many credits do I have left" — both because
`apply_deterministic_rule`'s rule vocabulary has no plain-aggregation type, and because the model
reliably guessed the wrong field name (`rule_type` instead of `type`) since `rule: dict[str, Any]`
carries no visible schema at all.

Two changes, landed together because the second only pays off with the first:

1. **Give `apply_deterministic_rule` a small, composable expression-tree rule type** — not a
   general eval, a closed set of arithmetic/aggregate operators combined into a JSON tree — so a
   caller can express "160 minus the sum of completed credits" without us having had to
   pre-name that exact calculation.
2. **Give Calculation-Validation its own purpose-built reasoning block**, following the
   `BaseReasoningBlock` extension pattern already used by `RequestUnderstandingReasoningBlock` and
   `ComposeAnswerReasoningBlock`, instead of routing through the generic multi-pass
   `ReasoningBlock` + `tool_loop.py` machinery every other specialist role shares — because
   "compose a correct expression tree" is a genuinely different shape of work than "fetch
   something, iterate if ambiguous."

Both are additive. Nothing existing changes behavior unless a step is classified as
`calculation_validation`.

---

## Part 1 — `apply_deterministic_rule`'s expression-tree rule type

### 1.1 New module: `app/agent_core/tools/primitives/expression_tree.py`

A new, small module — kept separate from `apply_deterministic_rule.py` itself so that file doesn't
grow past a focused size, and so the tree schema/evaluator can be imported directly by the new
reasoning block (Part 2) for pre-execution structural validation, without importing the whole
`apply_deterministic_rule` primitive.

**`ExpressionNode` schema** (recursive Pydantic model — this is what makes the vocabulary visible
in the tool's own JSON schema, unlike today's bare `rule: dict[str, Any]`):

```python
class ExpressionNode(BaseModel):
    # Exactly one of const/ref/op is set per node -- enforced by a
    # model_validator(mode="after"), not by the type system alone.
    const: float | int | None = None
    ref: str | None = None
    op: str | None = None  # one of _OPERATORS' keys, see below

    # Aggregate ops (sum/count/average): "of" resolves to a list, "field"
    # names which key to pull off each item, "filter" is the same
    # plain {field: value} equality map apply_deterministic_rule already uses.
    of: "ExpressionNode | None" = None
    field: str | None = None
    filter: dict[str, Any] | None = None

    # Binary ops (add/subtract/multiply/divide/compare)
    left: "ExpressionNode | None" = None
    right: "ExpressionNode | None" = None
    comparator: str | None = None  # compare only; same 6-value set as today

ExpressionNode.model_rebuild()
```

Operator vocabulary (`_OPERATORS`, deliberately small — grow it the same reactive way
`apply_deterministic_rule`'s rule types have grown, not by pre-guessing everything that might ever
be needed):

| `op` | Shape | Computes |
|---|---|---|
| `sum` | `of` (list), `field`, `filter?` | Sum of `field` across matching items in `of` |
| `count` | `of` (list), `filter?` | Count of matching items in `of` |
| `average` | `of` (list), `field`, `filter?` | Mean of `field` across matching items in `of` |
| `add` | `left`, `right` | `left + right` |
| `subtract` | `left`, `right` | `left - right` |
| `multiply` | `left`, `right` | `left * right` |
| `divide` | `left`, `right` | `left / right` (division by zero → error, never `inf`/`NaN`) |
| `compare` | `left`, `comparator`, `right` | Same 6 comparators as today (`>=,>,<=,<,==,!=`); returns a bool |

A leaf is either `{"const": <number>}` or `{"ref": "<facts key>"}` — `ref` looks up
`facts[ref]` directly, exactly like today's `source`/`filter` on `sum_threshold`.

### 1.2 Validation before execution: `validate_expression_tree`

```python
def validate_expression_tree(
    node: ExpressionNode, *, facts: dict[str, Any], max_depth: int = 6, max_nodes: int = 30
) -> list[str]:
    ...
```

Pure, synchronous, no I/O — walks the tree and returns a list of human-readable errors (empty list
= valid), each naming the exact node path, e.g. `"subtract.right.sum: ref 'completedCourses' not "
"found in facts (available: completed_courses)"`. Checks, in order:
- Depth and total node count within bounds (reject an oversized/degenerate tree before ever
  touching it — same "bound an LLM-controlled structure" instinct as the tool-loop round cap and
  the reasoning-call budget already in this codebase).
- Exactly one of `const`/`ref`/`op` is set per node.
- Every `ref` exists as a key in `facts`.
- Each `op`'s required sibling fields are present (`sum`/`average` need `of` + `field`; `count`
  needs `of`; `add`/`subtract`/`multiply`/`divide` need `left` + `right`; `compare` needs `left` +
  `comparator` + `right`).
- `comparator` (when present) is one of the 6 known values.

This function is called **twice** in the full flow: once by the new reasoning block (Part 2)
*before* ever calling the tool, so a malformed tree gets repaired without wasting a real tool call;
and once inside the tool itself (defense in depth — nothing should assume the reasoning block's own
pre-check was actually run).

### 1.3 Evaluator: `evaluate_expression`

```python
def evaluate_expression(
    node: ExpressionNode, facts: dict[str, Any]
) -> tuple[Any, list[str], list[str]]:  # (value, trace_lines, errors)
    ...
```

Recursive, fails closed exactly like today's `_sum_threshold`/`_count_threshold`/
`_field_comparison` (a non-numeric field value, missing facts key, etc. all become a real error
string, never a guess). Returns a **trace**: one human-readable line per evaluated node (e.g.
`"sum(completed_courses.credits_earned) = 3.5"`, `"160 - 3.5 = 156.5"`) so Composition can cite the
derivation instead of asserting a bare number — this is the same "never assert a computed fact
without the tool call backing it" principle `DETERMINISTIC_RULE_CONTRACT.md` already states, just
extended to *how* the number was derived, not only *that* a tool produced it.

### 1.4 Wiring into `apply_deterministic_rule.py`

One new entry in `_HANDLERS`:

```python
from app.agent_core.tools.primitives.expression_tree import (
    ExpressionNode, evaluate_expression, validate_expression_tree,
)

def _expression(rule: dict[str, Any], facts: dict[str, Any]) -> _HandlerResult:
    raw_expression = rule.get("expression")
    if not isinstance(raw_expression, dict):
        return None, "expression_required"
    try:
        node = ExpressionNode.model_validate(raw_expression)
    except ValidationError as exc:
        return None, f"invalid_expression_shape: {exc}"

    errors = validate_expression_tree(node, facts=facts)
    if errors:
        return None, f"expression_validation_failed: {'; '.join(errors[:5])}"

    value, trace, eval_errors = evaluate_expression(node, facts)
    if eval_errors:
        return None, f"expression_evaluation_failed: {'; '.join(eval_errors[:5])}"

    return {"type": "expression", "result": value, "trace": trace}, None

_HANDLERS["expression"] = _expression
```

Existing 3 rule types are **untouched** — `sum_threshold`/`count_threshold`/`field_comparison`
keep their exact current behavior, tests, and callers. `run_apply_deterministic_rule`'s own
`rule_type` extraction (already fixed this session to accept `rule_type` as an alias for `type`)
needs no further change — `"expression"` is just a new value that key can hold.

Also update `DESCRIPTOR.description` to mention the new type, and
`docs/agent/DETERMINISTIC_RULE_CONTRACT.md` per its own "update this doc whenever the rule
vocabulary changes" instruction — add a 4th row to the rule-type table and an `expression` example.

### 1.5 Test plan (Part 1)

New file `tests/agent_core/tools/test_expression_tree.py`:
- One test per operator (`sum`, `count`, `average`, `add`, `subtract`, `multiply`, `divide`,
  `compare`), happy path + its own specific failure mode (missing field, non-numeric value, div by
  zero, unknown comparator).
- `validate_expression_tree`: depth-exceeded, node-count-exceeded, unknown `ref`, missing required
  sibling field, ambiguous node (more than one of const/ref/op set), no shape set at all.
- A multi-level tree (the credits-remaining example: `subtract(const 160, sum(ref
  completed_courses, credits_earned))`) — both validate and evaluate, asserting the full trace
  content, not just the final number.

Extend `tests/agent_core/tools/test_apply_deterministic_rule.py`:
- `type: "expression"` end-to-end through `run_apply_deterministic_rule` (happy path + a
  validation-failure path + an evaluation-failure path), confirming the new handler is wired
  correctly and existing 3 rule types still pass unchanged.

---

## Part 2 — `CalculationValidationReasoningBlock`

### 2.1 Why a dedicated block (recap, for the record)

Today, Calculation-Validation is dispatched through `subagents/run.py::run_subagent` →
`reasoning/reasoning_block.py::ReasoningBlock` — the same generic multi-pass, tool-loop-bounded
machinery every specialist role shares, built around "fetch something via tools, iterate if
ambiguous." That shape doesn't fit "compose a correct expression tree": there's no reason to
*iterate rounds of tool calls* for this role the way Retrieval legitimately does, and the generic
schema-repair loop (`reasoning/schema_repair.py`) only ever sees raw `jsonschema` validation
errors, not the *semantic* errors `validate_expression_tree` can catch (a `ref` that doesn't exist
in `facts` isn't a JSON-Schema-expressible constraint).

`reasoning_blocks/base.py::BaseReasoningBlock` already exists specifically to let a component own
a genuinely different `_run_internal` shape (see `RequestUnderstandingReasoningBlock`,
`ComposeAnswerReasoningBlock` in `tools/primitives/compose_answer.py`). This is the third instance
of that same pattern, not a new one.

### 2.2 Control flow

```
1. Draft   — one LLM call: given the step's facts + objective, produce an ExpressionNode tree
             (and, only if genuinely needed, an intent to call extract_temporal_pattern instead --
             see 2.6 scope note).
2. Validate — validate_expression_tree(tree, facts=facts), in-process, zero LLM cost.
   2a. Valid  → go to 3.
   2b. Invalid → one repair LLM call: "here is your tree, here is exactly which node is invalid
                 and why (from validate_expression_tree's own error list), fix it." Bounded to
                 _MAX_REPAIR_ATTEMPTS (2, matching every other repair loop in this codebase).
                 Re-validate after each attempt; still invalid after all attempts → fail closed
                 (status="failed", never call the tool with a tree we know is broken).
3. Execute — call apply_deterministic_rule exactly once (via the normal tool_registry, preserving
             the existing tool-grant-ceiling mechanism -- this block is not a special case for
             *permissions*, only for *control flow*). The tree is already validated, so this call
             should essentially always succeed; if it still comes back ok=False (a real runtime
             surprise, e.g. a non-numeric field value only detectable at evaluation time), that is
             a genuine failure, not a retry loop -- fail closed.
4. Return  — the tool's own {result, trace} becomes this block's `result`; certainty is always
             `official_record` (mirrors DETERMINISTIC_RULE_CONTRACT.md's existing rule: computing
             over given facts adds no uncertainty of its own).
```

No tool-loop rounds, no multi-pass "understand → draft → final" sequence — one draft call, at
most `_MAX_REPAIR_ATTEMPTS` repair calls, one tool call. Materially cheaper and more predictable
than today's path, on top of being more likely to actually succeed.

### 2.3 New module: `app/agent_core/subagents/calculation_validation_block.py`

Placed alongside `subagents/run.py`/`builder.py`/`tool_loop.py` (not under `roles/` or its own
top-level package like `request_understanding/`) because it *is* an alternate, purpose-built
specialist runner for exactly one role — squarely `subagents/`'s existing domain, just not the
generic one.

```python
class _CalculationValidationBlockInput(BaseReasoningBlockInput):
    facts: dict[str, Any]          # flattened from context_package.dependency_state
    tool_grant: list[str]          # from context_package.tool_grant, unchanged mechanism

class _CalculationValidationBlockOutput(BaseReasoningBlockOutput):
    expression_used: dict[str, Any] | None = None
    trace: list[str] = Field(default_factory=list)

class CalculationValidationReasoningBlock(BaseReasoningBlock):
    async def _run_internal(self, block_input, telemetry) -> _CalculationValidationBlockOutput:
        ...  # draft -> validate -> repair -> execute, per 2.2

async def run_calculation_validation_subagent(
    *, context_package: SubagentContextPackage, tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter, block_id: str,
) -> SubagentResult:
    """Same signature/return type as subagents.run.run_subagent -- a drop-in
    alternate dispatch target, not a parallel result type."""
```

`facts` is built once, up front, by flattening `context_package.dependency_state` (a
`list[StateEntry]`) into a `dict[str, Any]` keyed by each entry's `step_id` — the model already
successfully references dependency data this way today (its own tool-call arguments already say
things like `"source": "completed_courses record (user_id ...) + course entity 00950120"`), so this
doesn't require the model to learn a new referencing convention, just gives it a smaller, cleaner
surface to build expressions against than raw `dependency_state`.

### 2.4 Prompt contracts

Two new contracts, registered in their own `PromptRegistry` builder
(`build_calculation_validation_prompt_registry()`), mirroring `compose_answer.py`'s
`_build_prompt_registry()` pattern:

- **`CALCULATION_VALIDATION_DRAFT_V1`** — role prompt explains the operator vocabulary (mirrors
  the table in 1.1) and instructs: reference facts by the exact keys given, prefer the smallest
  tree that answers the objective, never invent a `ref` that isn't in the given facts (the same
  "never assert a fact not backed by a tool/given data" rule every other role's contract already
  states).
- **`CALCULATION_VALIDATION_REPAIR_V1`** — takes the invalid tree + `validate_expression_tree`'s
  own error list (not raw jsonschema errors) and asks for a corrected tree. Explicitly scoped:
  "fix only the structural/reference errors listed; do not change what the expression computes."

Both contracts' `output_schema` is `ExpressionNode.model_json_schema()` directly — this is the
real payoff of Part 1's recursive schema over today's bare dict: the model sees the actual allowed
shapes structurally, not just in prose, and (optionally, recommended) this pairs well with
`AGENT_REASONING_STRUCTURED_OUTPUT_ENABLED` (`llm_adapter.py`) for provider-native schema
enforcement on this specific call.

### 2.5 Dispatch integration: `task_handler.py`

`_dispatch_single_specialist` currently always ends with:

```python
return await run_subagent(role=role, context_package=context_package, tool_registry=tool_registry,
                           llm_adapter=llm_adapter, block_id=block_id)
```

Change to:

```python
if role.name == "calculation_validation":
    return await run_calculation_validation_subagent(
        context_package=context_package, tool_registry=tool_registry,
        llm_adapter=llm_adapter, block_id=block_id,
    )
return await run_subagent(role=role, context_package=context_package, tool_registry=tool_registry,
                           llm_adapter=llm_adapter, block_id=block_id)
```

One `if`, one new import. Every downstream consumer (`StateEntry` construction, success-check,
nested re-planning) only ever sees a `SubagentResult` either way — nothing else in `task_handler.py`
needs to know or care which path produced it. This mirrors how `compose_answer.py`'s primitive and
`synthesis.py`'s role-based path are already deliberately allowed to coexist without full
reconciliation (see that file's own docstring) — the same "not every dedicated shape needs the
generic path retired immediately" precedent already exists in this codebase.

`roles/roster.py`'s `calculation_validation` `RoleDefinition` (name, `prompt_contract_name`,
`tool_grant_ceiling`, `default_reasoning_params`) needs **no changes** — the dedicated block still
respects the same tool grant and role identity, it just runs a different internal control flow.

### 2.6 Explicitly out of scope for v1

- **`extract_temporal_pattern` support in the dedicated block.** The role's `tool_grant_ceiling`
  already includes it (for "have you taken X in the last N semesters"-shaped rules), but today's
  live-eval evidence only shows a real, concrete gap around `apply_deterministic_rule`. Extend the
  dedicated block to handle temporal-pattern-driven steps when a real failure demonstrates the
  need, not speculatively now (same reactive-growth principle as the rule-type vocabulary itself).
- **Retiring the generic path for other roles.** Retrieval/Interpretation/Simulation-Planning keep
  using `run_subagent`/`ReasoningBlock`/`tool_loop.py` unchanged. Each role only migrates to its own
  dedicated block when a concrete, demonstrated shape mismatch justifies it (RU and Composition
  already did; this plan does Calculation-Validation; the other two stay generic until/unless a
  similar live-eval finding justifies migrating them too).
- **Reconciling `_sum_threshold`/`_count_threshold`/`_field_comparison` into expression-tree sugar.**
  Mentioned as a possible future simplification in conversation, but not required for this plan to
  land — the 3 existing rule types stay exactly as they are, tested and working.

### 2.7 Test plan (Part 2)

New file `tests/agent_core/test_calculation_validation_block.py` (pattern: `FakeLLMAdapter` +
`fake_llm_adapter_factory`, same convention as `test_request_understanding.py`/
`test_synthesis.py`):
- Draft succeeds, tree valid on first try → tool called once, correct result/trace returned.
- Draft produces an invalid tree (bad `ref`) → one repair call → valid tree → tool called once.
  Assert the repair call's prompt includes `validate_expression_tree`'s exact error string, not a
  generic one.
- Repair exhausted (`_MAX_REPAIR_ATTEMPTS` invalid trees in a row) → `status="failed"`, tool never
  called (assert on the fake tool registry's call count = 0).
- Tool itself returns `ok=False` despite a pre-validated tree (a genuine runtime surprise) →
  `status="failed"`, not a retry.
- `run_calculation_validation_subagent` returns a `SubagentResult` with the same shape
  (`status`/`result`/`certainty`/`warnings`/`tool_audit_trail`) `build_subagent_result` produces
  today, so `task_handler.py`'s downstream handling needs zero changes.

Extend `tests/agent_core/test_orchestrator_task_handler.py`:
- A step classified with `role_if_atomic="calculation_validation"` dispatches through
  `run_calculation_validation_subagent`, not `run_subagent` (monkeypatch both, assert only the
  former was called) — mirrors this suite's existing "monkeypatch the collaborator" convention.

`roles/roster.py`'s existing tests (`test_roles.py`) need no changes (`RoleDefinition` itself is
untouched).

---

## Part 3 — Rollout / verification plan

Same rigor this session already established for every other fix:

1. Implement Part 1 (expression tree), full unit test suite green, no changes to existing
   `apply_deterministic_rule` behavior.
2. Implement Part 2 (dedicated block + dispatch wiring), full unit test suite green.
3. Full regression suite (`pytest -m "not live"`) — zero new failures beyond the pre-existing,
   unrelated `test_get_policy_answer.py` ones.
4. Rebuild `ai`, redeploy, rerun the exact live-eval scenario that motivated this plan: a seeded
   test student with a real `degreeId`, question "How many total credits have I completed, and how
   many more do I need to graduate?" — confirm it now completes well inside the turn budget with a
   correct, grounded answer citing the actual derivation trace.
5. Commit in the same discrete, reported batches this session used throughout (Part 1 alone, then
   Part 2 alone, or together if both are small enough to review as one unit — judgment call at
   implementation time).

## Part 4 — Open questions to resolve at implementation time (not blocking, but worth a second look)

- Exact `_MAX_REPAIR_ATTEMPTS` value for the new block (proposed: 2, matching
  `_MAX_SCHEMA_REPAIR_ATTEMPTS` elsewhere) — no strong reason to differ, but confirm against real
  live-eval behavior once implemented.
- Whether `divide`'s division-by-zero should be a hard `ok=False` error or a defined `null`/`None`
  result with a warning — proposed: hard error (fail closed, consistent with
  `DETERMINISTIC_RULE_CONTRACT.md`'s stated design principle), but worth confirming no real
  question needs "N/A" semantics instead.
- Whether `average` needs a `filter`-matched-zero-records case to return `0` (like sum) or fail
  closed as "insufficient data" (unlike sum, an average of zero items is arguably undefined, not
  zero) — proposed: fail closed with a distinct error (`average_of_empty_set`), since "zero" and
  "undefined" are genuinely different answers here, unlike a sum.
