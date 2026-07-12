"""A small, closed, composable expression-tree vocabulary for
`apply_deterministic_rule`'s `"expression"` rule type
(docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 1).

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


class ExpressionNode(BaseModel):
    """Exactly one of `const`/`ref`/`op` is set per node. Which other fields
    apply depends on `op` (see the operator table in
    CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md 1.1) -- those op-specific
    requirements are checked by `validate_expression_tree`, not here, so the
    error messages can name the exact node and be human-readable rather than
    raw jsonschema output.
    """

    const: float | int | None = None
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


def _matches_filter(record: dict[str, Any], record_filter: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in record_filter.items())


def _describe_leaf(node: ExpressionNode) -> str:
    if node.const is not None:
        return "const"
    if node.ref is not None:
        return f"ref:{node.ref}"
    return f"op:{node.op}"


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
        if not _is_number(left) or not _is_number(right):
            errors.append(f"non_numeric_operand: {op}")
            return None

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


__all__ = ["ExpressionNode", "validate_expression_tree", "evaluate_expression"]
