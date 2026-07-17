"""Fact admission -- the three grounding paths in code (Invariant A, §3.2).

A fact can only be born here, by one of:
  - surface_fact -- FETCH: a selector into a recorded tool envelope
    (`project_facts` reads the value; the model cannot type it).
  - compute      -- COMPUTE: an `expression_tree` over refs to existing facts,
    with the const-block that closes the laundering seam (§16.3).
  - select       -- COMPUTE (over a fact): filter a list-valued fact by a field
    match and read a record or one of its fields (§16.7). The capability the
    presupposition case needed and neither a path-selector nor `expression_tree`
    could provide: "the record where courseNumber == X, read its grade".

Each handler mutates the working set (admits facts, appends observations). The
pure decision cores -- `numeric_const_operands`, `filter_records` -- are factored
out so they can be unit-tested without an LLM or the substrate.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent_core.loop.working_set import Fact, WorkingSet, summarize_value
from app.agent_core.subagents.fact_projection import project_facts
from app.agent_core.tools.primitives.expression_tree import (
    ExpressionNode,
    evaluate_expression,
    validate_expression_tree,
)

_ARITHMETIC_OPS = frozenset({"add", "subtract", "multiply", "divide"})


def _basis_by_handle(ws: WorkingSet) -> dict[str, str]:
    """The certainty basis of each recorded call, keyed by its handle -- so a
    surfaced fact inherits its source call's basis rather than a guessed one."""
    out: dict[str, str] = {}
    for handle, key in ws.handles.items():
        certainty = (ws.tool_results.get(key) or {}).get("certainty") or {}
        out[handle] = certainty.get("basis", "unknown")
    return out


def apply_surface(ws: WorkingSet, args: dict[str, Any]) -> int:
    """FETCH. Promote value(s) from recorded tool result(s) into named facts via
    `project_facts` (which reads by path -- the model never types the value).
    Returns the count of genuinely-new facts admitted (no-progress signal)."""
    selectors = args.get("selectors")
    if selectors is None:  # single-selector shorthand
        selectors = [{"key": args.get("key"), "from": args.get("from"), "path": args.get("path")}]
    outcome = project_facts(selectors, ws.tool_results, ws.handles)
    basis_by_handle = _basis_by_handle(ws)
    selector_basis = {
        s.get("key"): basis_by_handle.get(s.get("from"), "unknown")
        for s in selectors
        if isinstance(s, dict)
    }
    new_facts = 0
    for key, fact in outcome.facts.items():
        admitted = ws.add_fact(
            key, Fact(fact["value"], fact["source"], selector_basis.get(key, "unknown"), fact["confidence"])
        )
        new_facts += int(admitted)
        ws.observe(f"surfaced fact '{key}' = {summarize_value(fact['value'])}")
    for err in outcome.errors:
        ws.observe(f"surface_fact error: {err}")
    return new_facts


def numeric_const_operands(node: ExpressionNode) -> list[Any]:
    """Numeric `const` leaves used as an operand of binary arithmetic (§16.3).

    The spike caught the const-laundering seam: the model typed `{"const": 155}`
    for the degree total and subtracted the grounded earned credits, shipping a
    number whose provenance was the model's own head. An arithmetic operand that
    produces an answer number must be a REF to a grounded fact, never a literal.
    A genuinely user-given literal is a separate later concern; neither eval case
    needs one, so blocking numeric consts in arithmetic outright is safe here.
    """
    found: list[Any] = []
    if node.op in _ARITHMETIC_OPS:
        for child in (node.left, node.right):
            if (
                child is not None
                and child.const is not None
                and isinstance(child.const, (int, float))
                and not isinstance(child.const, bool)
            ):
                found.append(child.const)
    for child in (node.of, node.left, node.right):
        if child is not None:
            found.extend(numeric_const_operands(child))
    return found


def apply_compute(ws: WorkingSet, args: dict[str, Any]) -> int:
    """COMPUTE. Evaluate an expression over existing facts, after the const-block
    and the tree's own validation. Returns 1 if a new fact was admitted."""
    key = args.get("key")
    raw_expr = args.get("expression")
    if not key or raw_expr is None:
        ws.observe("compute error: missing 'key' or 'expression'")
        return 0
    try:
        node = ExpressionNode(**raw_expr)
    except Exception as exc:  # noqa: BLE001 -- a malformed expression is an observation, not a crash
        ws.observe(f"compute error: malformed expression: {exc}")
        return 0

    laundered = numeric_const_operands(node)
    if laundered:
        ws.observe(
            f"compute '{key}' REJECTED: arithmetic operand(s) {laundered} are typed literals, not "
            f"grounded facts. A number like this must be FETCHED or INTERPRETED first (e.g. "
            f"interpret_text on the track wiki slug for total required credits), surfaced as a fact, "
            f"then referenced with a ref -- never typed as a const."
        )
        return 0

    facts_values = {k: f.value for k, f in ws.facts.items()}
    errors = validate_expression_tree(node, facts=facts_values)
    if errors:
        ws.observe(f"compute '{key}' rejected: {errors}")
        return 0
    value, trace, eval_errors = evaluate_expression(node, facts_values)
    if eval_errors:
        ws.observe(f"compute '{key}' failed: {eval_errors}")
        return 0

    refs_used = {k for k in ws.facts if f'"{k}"' in json.dumps(raw_expr)}
    confidence = min((ws.facts[r].confidence for r in refs_used), default=1.0)
    admitted = ws.add_fact(key, Fact(value, f"compute({'; '.join(trace)})", "computed", confidence))
    ws.observe(f"computed '{key}' = {value}  [{'; '.join(trace)}]")
    return int(admitted)


def filter_records(
    records: list[Any], where: dict[str, Any], field: str | None
) -> tuple[Any, int]:
    """Pure select core: filter a list of records by an all-equal `where` match,
    then read `field` (or the whole record). Returns (value, match_count).

    A single match yields the scalar/record directly; zero or several yield a
    list -- an empty list is a real, grounded answer ("not in that list"), not a
    failure. Comparison is stringified so "00940224" matches an int/str alike.
    """
    matched = [
        r
        for r in records
        if isinstance(r, dict) and all(str(r.get(k)) == str(v) for k, v in where.items())
    ]
    if field is not None:
        picked = [r.get(field) for r in matched]
        value: Any = picked[0] if len(picked) == 1 else picked
    else:
        value = matched[0] if len(matched) == 1 else matched
    return value, len(matched)


def apply_select(ws: WorkingSet, args: dict[str, Any]) -> int:
    """SELECT. Filter a list-valued fact by a field match and read a record or
    one field. Deterministic over an already-grounded fact, so the result
    inherits that fact's basis/confidence. Returns 1 if a new fact was admitted."""
    key = args.get("key")
    from_fact = args.get("from_fact")
    where = args.get("where") or {}
    field = args.get("field")
    if not key or not from_fact:
        ws.observe("select error: missing 'key' or 'from_fact'")
        return 0
    if from_fact not in ws.facts:
        ws.observe(f"select error: no fact named '{from_fact}' (available: {sorted(ws.facts)})")
        return 0
    source = ws.facts[from_fact]
    if not isinstance(source.value, list):
        ws.observe(
            f"select error: fact '{from_fact}' is not a list (it is {type(source.value).__name__})"
        )
        return 0

    value, match_count = filter_records(source.value, where, field)
    label = f"select({from_fact} where {where}" + (f").{field}" if field else ")")
    admitted = ws.add_fact(key, Fact(value, label, source.basis, source.confidence))
    ws.observe(f"selected '{key}' = {summarize_value(value)} ({match_count} match(es))")
    return int(admitted)


__all__ = [
    "apply_surface",
    "apply_compute",
    "apply_select",
    "numeric_const_operands",
    "filter_records",
]
