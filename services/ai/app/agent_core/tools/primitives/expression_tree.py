"""A small, closed, composable expression-tree vocabulary for
`apply_deterministic_rule`'s `"expression"` rule type.

Deliberately NOT a general expression evaluator: `_OPERATORS` is a fixed,
auditable set (sum/count/average/add/subtract/multiply/divide/compare), and
`evaluate_expression` never uses `eval`/`exec` or any other arbitrary-code
path. This is the load-bearing security constraint the design was chosen
for -- grow `_OPERATORS` reactively, the same way
`apply_deterministic_rule`'s rule-type vocabulary already grows, never by
adding a generic escape hatch.

Kept separate from `apply_deterministic_rule.py` so that module doesn't grow
past a focused size, and so `CalculationValidationReasoningBlock` (Part 2)
can import the schema/validator directly for pre-execution checks without
importing the whole primitive.
"""

from __future__ import annotations

from numbers import Number
from typing import Any

from pydantic import BaseModel, model_validator

_COMPARATORS: dict[str, Any] = {
    ">=": lambda left, right: left >= right,
    ">": lambda left, right: left > right,
    "<=": lambda left, right: left <= right,
    "<": lambda left, right: left < right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
}

_AGGREGATE_OPS = ("sum", "count", "average")
_BINARY_ARITHMETIC_OPS = ("add", "subtract", "multiply", "divide")
_OPERATORS = frozenset({*_AGGREGATE_OPS, *_BINARY_ARITHMETIC_OPS, "compare"})

# Marks an error that NO edit to the expression can fix: the facts themselves
# lack what any correct expression would have to read. Every other error here is
# a defect in the tree and a repair pass can act on it; these are a defect in the
# DATA, and a repair pass can only burn attempts rewriting an expression that was
# already right. Callers' repair loops must branch on this rather than retrying
# (see `calculation_validation_block._draft_valid_expression`).
FACTS_DEFECT_PREFIX = "facts_defect:"


class ExpressionNode(BaseModel):
    """Exactly one of `const`/`ref`/`op` is set per node. Which other fields
    apply depends on `op` (see `_OPERATORS` above for the operator set) --
    those op-specific
    requirements are checked by `validate_expression_tree`, not here, so the
    error messages can name the exact node and be human-readable rather than
    raw jsonschema output.
    """

    # Widened from float|int only: a live-eval run found the Calculation
    # role needing a plain equality comparison against a string constant
    # (e.g. current_semester == "Spring 2025/2026") -- const's Pydantic
    # type rejected the string outright, the repair loop then "fixed" it
    # into a nonsensical `ref` (treating the literal string as a fact-name
    # lookup), which failed too, and the SECOND repair attempt gave up by
    # fabricating an always-true `{"const": 0} == {"const": 0}` placeholder
    # -- silently producing a wrong answer rather than failing closed.
    # `evaluate_expression`'s `==`/`!=` comparators already work generically
    # on any comparable Python value; only this type annotation blocked it.
    const: float | int | str | bool | None = None
    ref: str | None = None
    op: str | None = None

    of: "ExpressionNode | None" = None
    field: str | None = None
    filter: dict[str, Any] | None = None

    left: "ExpressionNode | None" = None
    right: "ExpressionNode | None" = None
    comparator: str | None = None

    @model_validator(mode="after")
    def _exactly_one_of_const_ref_op(self) -> "ExpressionNode":
        set_count = sum(1 for value in (self.const, self.ref, self.op) if value is not None)
        if set_count != 1:
            raise ValueError(f"exactly one of const/ref/op must be set (found {set_count})")
        return self


ExpressionNode.model_rebuild()


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _as_arithmetic_number(value: Any) -> Any | None:
    """A number, or a string that is wholly one. `None` when it is neither.

    Applied ONLY in arithmetic operand position, never to `compare`. Live
    (2026-07-16, `credits_remaining`) the degree's total credits reached the
    calculator as the STRING "155" -- an interpretation step read it off the ISE
    track wiki page, and `InterpretationReasoningBlock`'s `answer` is a string by
    schema, so every number ever read out of prose arrives this way. Refusing to
    subtract it means prose-sourced numbers can never be computed with at all.

    Deliberately not applied to `compare`, and deliberately not applied when
    promoting facts. A course number IS a numeric string -- `"00940224"` --
    and coercing it to 940224.0 would silently destroy the leading zeros that
    every prerequisite and requirement match keys on. Arithmetic position is
    unambiguous about intent (nobody subtracts course numbers); equality is not.
    """
    if isinstance(value, bool):
        return None
    if _is_number(value):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return None
    return None


def _describe_operand(node: Any, value: Any) -> str:
    """Name what an operand WAS and what it resolved TO.

    `non_numeric_operand: subtract` named neither. Live (2026-07-16,
    `credits_remaining`) the model got that back, had nothing to act on, and
    re-emitted the identical expression -- then the Planner replanned the step
    and it failed the same way a third time. An error a model cannot act on is
    retried verbatim.
    """
    if node is None:
        source = "missing operand"
    elif getattr(node, "ref", None) is not None:
        source = f"ref {node.ref!r}"
    elif getattr(node, "const", None) is not None:
        source = "const"
    else:
        source = "sub-expression"
    rendered = repr(value)
    if len(rendered) > 60:
        rendered = f"{rendered[:57]}..."
    return f"{source} -> {type(value).__name__} {rendered}"


def _matches_filter(record: dict[str, Any], record_filter: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in record_filter.items())


def _describe_leaf(node: ExpressionNode) -> str:
    if node.const is not None:
        return "const"
    if node.ref is not None:
        return f"ref:{node.ref}"
    return f"op:{node.op}"


def _tree_has_ref(node: ExpressionNode) -> bool:
    """True when any node anywhere in the tree reads a supplied fact."""
    if node.ref is not None:
        return True
    return any(child is not None and _tree_has_ref(child) for child in (node.of, node.left, node.right))


def _validate_node(
    node: ExpressionNode,
    *,
    facts: dict[str, Any],
    path: str,
    depth: int,
    max_depth: int,
    max_nodes: int,
    counter: dict[str, int],
    errors: list[str],
) -> None:
    counter["nodes"] += 1
    if counter["nodes"] > max_nodes:
        errors.append(f"{path}: expression tree exceeds max_nodes={max_nodes}")
        return
    if depth > max_depth:
        errors.append(f"{path}: expression tree exceeds max_depth={max_depth}")
        return

    set_count = sum(1 for value in (node.const, node.ref, node.op) if value is not None)
    if set_count != 1:
        errors.append(f"{path}: exactly one of const/ref/op must be set (found {set_count})")
        return

    if node.const is not None:
        return

    if node.ref is not None:
        if node.ref not in facts:
            errors.append(f"{path}: ref '{node.ref}' not found in facts (available: {sorted(facts.keys())})")
        return

    op = node.op
    if op not in _OPERATORS:
        errors.append(f"{path}: unknown op '{op}'")
        return

    node_path = f"{path}.{op}" if path != "root" else op

    if op in _AGGREGATE_OPS:
        if node.of is None:
            errors.append(f"{node_path}: 'of' is required for op '{op}'")
        else:
            _validate_node(
                node.of,
                facts=facts,
                path=f"{node_path}.of",
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                counter=counter,
                errors=errors,
            )
            # An aggregate can only run over a LIST. Checking that here -- not
            # just at evaluation time -- is what makes the mistake repairable:
            # `_eval_node` raises `of_not_a_list` only once the tool is already
            # executing a tree that passed validation, and the block never
            # retries a validated tree, so the whole step fails. Observed live
            # (2026-07-15): the model summed over `creditBreakdown` (the
            # credit-buckets DICT) instead of the `completedCourses` list in the
            # same facts; the step died and a retrieval block then did the sum
            # in-model and asserted a wrong total. Naming the list-valued facts
            # gives the repair pass something concrete to switch to.
            of_ref = node.of.ref
            if of_ref is not None and of_ref in facts and not isinstance(facts[of_ref], list):
                list_refs = sorted(key for key, value in facts.items() if isinstance(value, list))
                errors.append(
                    f"{node_path}.of: ref '{of_ref}' is not a list (it is a "
                    f"{type(facts[of_ref]).__name__}); op '{op}' aggregates over a list of records. "
                    f"List-valued facts available: {list_refs}"
                )
            elif (
                op in ("sum", "average")
                and node.field
                and of_ref is not None
                and isinstance(facts.get(of_ref), list)
            ):
                # sum/average need a NUMERIC field on the records. Catching a
                # wrong/absent field name here -- not only at eval time -- turns
                # a fatal `non_numeric_field_value` on an already-validated tree
                # into a repairable error the bounded repair loop can act on.
                # Observed live (ISE credits_remaining): the model summed field
                # 'deficit', absent from the course records, so the step died and
                # the composition reported a hallucinated earned-credits total.
                # Naming the numeric fields that DO exist gives repair a target.
                records = [record for record in facts[of_ref] if isinstance(record, dict)]
                if records and not any(_is_number(record.get(node.field)) for record in records):
                    numeric_fields = sorted(
                        {key for record in records for key, value in record.items() if _is_number(value)}
                    )
                    if numeric_fields:
                        errors.append(
                            f"{node_path}.field: '{node.field}' is not a numeric field on the "
                            f"'{of_ref}' records; numeric fields available: {numeric_fields}"
                        )
                    else:
                        # Nothing to switch TO. The records carry no numbers at
                        # all, so the expression was never the thing that was
                        # wrong -- see FACTS_DEFECT_PREFIX.
                        present_keys = sorted({key for record in records for key in record})
                        errors.append(
                            f"{FACTS_DEFECT_PREFIX} '{of_ref}' has {len(records)} records and not one "
                            f"carries a numeric field, so op '{op}' has nothing to aggregate. Keys "
                            f"present on those records: {present_keys}. No edit to this expression can "
                            f"fix that -- '{node.field}' was never retrieved."
                        )
        if op in ("sum", "average") and not node.field:
            errors.append(f"{node_path}: 'field' is required for op '{op}'")
        return

    if op in _BINARY_ARITHMETIC_OPS:
        missing = [name for name, value in (("left", node.left), ("right", node.right)) if value is None]
        if missing:
            errors.append(f"{node_path}: {' and '.join(missing)} required for op '{op}'")
        if node.left is not None:
            _validate_node(
                node.left,
                facts=facts,
                path=f"{node_path}.left",
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                counter=counter,
                errors=errors,
            )
        if node.right is not None:
            _validate_node(
                node.right,
                facts=facts,
                path=f"{node_path}.right",
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                counter=counter,
                errors=errors,
            )
        return

    # op == "compare"
    missing = [name for name, value in (("left", node.left), ("right", node.right)) if value is None]
    if missing:
        errors.append(f"{node_path}: {' and '.join(missing)} required for op 'compare'")
    if node.comparator not in _COMPARATORS:
        errors.append(f"{node_path}: unknown comparator '{node.comparator}'")
    if node.left is not None:
        _validate_node(
            node.left,
            facts=facts,
            path=f"{node_path}.left",
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            counter=counter,
            errors=errors,
        )
    if node.right is not None:
        _validate_node(
            node.right,
            facts=facts,
            path=f"{node_path}.right",
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            counter=counter,
            errors=errors,
        )


def validate_expression_tree(
    node: ExpressionNode, *, facts: dict[str, Any], max_depth: int = 6, max_nodes: int = 30
) -> list[str]:
    """Pure, synchronous, no I/O. Returns a list of human-readable errors
    naming the exact node path (empty list = valid). Bounds depth/node
    count before ever evaluating the tree -- same "bound an LLM-controlled
    structure" instinct as the tool-loop round cap and the reasoning-call
    budget elsewhere in this codebase.
    """
    errors: list[str] = []
    counter = {"nodes": 0}
    _validate_node(
        node,
        facts=facts,
        path="root",
        depth=1,
        max_depth=max_depth,
        max_nodes=max_nodes,
        counter=counter,
        errors=errors,
    )
    # An expression that reads NONE of the facts it was handed is not a
    # calculation over that data -- it is a transcription of numbers the model
    # already had in mind, and the deterministic engine would rubber-stamp it.
    #
    # CAUGHT LIVE (2026-07-16, ise_correctness `credits_remaining`). Retrieval
    # smuggled an in-model sum (`total_credits_earned: 63.5`; the real total is
    # 62.5) out through an out-of-contract `metadata` key. The plausibility
    # checker then read that number, declared the engine's CORRECT 62.5
    # implausible, and its critique -- "the fix is to ... reach 63.5" -- reached
    # the Planner, which instructed "use the corrected value of 63.5". The next
    # step evaluated:
    #
    #     {"op": "subtract", "left": {"const": 155}, "right": {"const": 63.5}}
    #
    # ...which is arithmetically flawless and completely ungrounded. It laundered
    # the hallucination THROUGH the engine, so 91.5 emerged wearing the
    # calculator's authority and was published to the student as "verified and
    # confirmed". Every operand a literal, not one fact consulted.
    #
    # The plausibility contract already names this ("it hardcodes a `const` for a
    # quantity that should have been computed from a fact") and the checker still
    # passed it -- which is the whole lesson: this is decidable in code, so decide
    # it in code. Same instinct as `subagents/fact_projection.py` and the bounds
    # above.
    #
    # Only when `facts` is non-empty: a genuinely fact-free calculation has
    # nothing to ignore, so there is nothing to catch. Only on an otherwise-valid
    # tree, so a structural error is reported first and this never adds noise to
    # a tree that could not have run anyway.
    if not errors and facts and not _tree_has_ref(node):
        errors.append(
            "root: expression reads none of the supplied facts (every operand is a literal const). "
            "A calculation over the student's data must read that data with a ref -- a const is for a "
            "literal you were given, never for a total you worked out yourself. "
            f"Facts available: {sorted(facts.keys())}"
        )
    return errors


def _eval_node(node: ExpressionNode, facts: dict[str, Any], trace: list[str], errors: list[str]) -> Any:
    if errors:
        return None

    if node.const is not None:
        return node.const

    if node.ref is not None:
        if node.ref not in facts:
            errors.append(f"ref_not_found: {node.ref}")
            return None
        return facts[node.ref]

    op = node.op

    if op in _AGGREGATE_OPS:
        records = _eval_node(node.of, facts, trace, errors) if node.of is not None else None
        if errors:
            return None
        if not isinstance(records, list):
            errors.append(f"of_not_a_list: {_describe_leaf(node.of) if node.of is not None else 'missing'}")
            return None

        record_filter = node.filter or {}
        matched = [
            record for record in records if isinstance(record, dict) and _matches_filter(record, record_filter)
        ]
        source_label = _describe_leaf(node.of) if node.of is not None else "of"

        if op == "count":
            result = len(matched)
            trace.append(f"count({source_label}) = {result}")
            return result

        field = node.field
        total = 0
        for record in matched:
            value = record.get(field)
            if not _is_number(value):
                errors.append(f"non_numeric_field_value: {source_label}.{field}")
                return None
            total += value

        if op == "sum":
            trace.append(f"sum({source_label}.{field}) = {total}")
            return total

        # average
        if not matched:
            errors.append("average_of_empty_set")
            return None
        average = total / len(matched)
        trace.append(f"average({source_label}.{field}) = {average}")
        return average

    if op in _BINARY_ARITHMETIC_OPS:
        left = _eval_node(node.left, facts, trace, errors) if node.left is not None else None
        right = _eval_node(node.right, facts, trace, errors) if node.right is not None else None
        if errors:
            return None
        left_number = _as_arithmetic_number(left)
        right_number = _as_arithmetic_number(right)
        if left_number is None or right_number is None:
            errors.append(
                f"non_numeric_operand: {op} needs two numbers. "
                f"left: {_describe_operand(node.left, left)}. "
                f"right: {_describe_operand(node.right, right)}. "
                f"Facts available: {sorted(facts.keys())}"
            )
            return None
        left, right = left_number, right_number

        if op == "add":
            result, symbol = left + right, "+"
        elif op == "subtract":
            result, symbol = left - right, "-"
        elif op == "multiply":
            result, symbol = left * right, "*"
        else:  # divide
            if right == 0:
                errors.append("division_by_zero")
                return None
            result, symbol = left / right, "/"

        trace.append(f"{left} {symbol} {right} = {result}")
        return result

    if op == "compare":
        left = _eval_node(node.left, facts, trace, errors) if node.left is not None else None
        right = _eval_node(node.right, facts, trace, errors) if node.right is not None else None
        if errors:
            return None
        comparator_fn = _COMPARATORS.get(node.comparator)
        if comparator_fn is None:
            errors.append(f"unknown_comparator: {node.comparator}")
            return None
        result = comparator_fn(left, right)
        trace.append(f"{left} {node.comparator} {right} = {result}")
        return result

    errors.append(f"unknown_op: {op}")
    return None


def evaluate_expression(node: ExpressionNode, facts: dict[str, Any]) -> tuple[Any, list[str], list[str]]:
    """Recursive, fails closed exactly like `apply_deterministic_rule.py`'s
    existing handlers -- a non-numeric field value, missing facts key, etc.
    all become a real error string, never a guess. Returns
    `(value, trace_lines, errors)`; `trace_lines` is one human-readable line
    per evaluated op node, so Composition can cite the derivation instead of
    asserting a bare number.
    """
    trace: list[str] = []
    errors: list[str] = []
    value = _eval_node(node, facts, trace, errors)
    return value, trace, errors


__all__ = ["FACTS_DEFECT_PREFIX", "ExpressionNode", "validate_expression_tree", "evaluate_expression"]
