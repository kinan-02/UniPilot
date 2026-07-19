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

from app.agent_core.loop.working_set import AUTHORITATIVE_BASES, Fact, WorkingSet, summarize_value
from app.agent_core.subagents.fact_projection import project_facts, resolve_path
from app.agent_core.tools.primitives.expression_tree import (
    ExpressionNode,
    evaluate_expression,
    validate_expression_tree,
)

_ARITHMETIC_OPS = frozenset({"add", "subtract", "multiply", "divide"})


def _resolve_field_certainty(
    path: str | None, field_certainty: Any, default_basis: str, default_confidence: float
) -> tuple[str, float]:
    """Per-field certainty (§4.2). One tool envelope can hold fields of different
    provenance -- check_eligibility's `eligible` is an official record but its
    `schedulable` depends on an offering PREDICTION. `field_certainty` maps a
    data-relative path (or a prefix of one) to that field's basis/confidence; the
    longest matching prefix wins, else the envelope's default certainty applies.
    So surfacing `data.schedulable` yields predicted_pattern while `data.eligible`
    stays official -- a prediction can no longer be laundered into a flat fact."""
    if not isinstance(field_certainty, dict) or not path:
        return default_basis, default_confidence
    segments = path.split(".")
    if segments and segments[0] == "data":
        segments = segments[1:]
    best_tag: dict[str, Any] | None = None
    best_len = -1
    for raw_key, tag in field_certainty.items():
        if not isinstance(tag, dict):
            continue
        key_segments = str(raw_key).split(".")
        if segments[: len(key_segments)] == key_segments and len(key_segments) > best_len:
            best_tag, best_len = tag, len(key_segments)
    if best_tag is None:
        return default_basis, default_confidence
    return best_tag.get("basis", default_basis), best_tag.get("confidence", default_confidence)


def _envelope_field_certainty(
    envelope: Any, path: str | None, fallback_confidence: float
) -> tuple[str, float]:
    """The (basis, confidence) a value projected at `path` inherits from its
    source ENVELOPE, resolved PER FIELD (§4.2). Shared by surface_fact (through
    `_selector_certainty`) and `map` -- both read a scalar out of a recorded tool
    result and must attribute its provenance identically."""
    default_certainty = (envelope or {}).get("certainty") or {}
    default_basis = default_certainty.get("basis", "unknown")
    default_confidence = default_certainty.get("confidence", fallback_confidence)
    return _resolve_field_certainty(
        path, (envelope or {}).get("field_certainty"), default_basis, default_confidence
    )


def _selector_certainty(
    ws: WorkingSet, selector: dict[str, Any], fallback_confidence: float
) -> tuple[str, float]:
    """The (basis, confidence) a surfaced fact inherits from its source call --
    resolved PER FIELD, not per envelope, so a mixed-provenance result attributes
    each field correctly rather than stamping them all with the envelope's basis."""
    envelope = ws.tool_results.get(ws.handles.get(selector.get("from"), "")) or {}
    return _envelope_field_certainty(envelope, selector.get("path"), fallback_confidence)


def _grain_hint(path: str | None, value: Any) -> str:
    """A deterministic nudge appended to a surface observation when the value is
    NOT directly answer-usable -- an object or a list of records, from which the
    answer needs a scalar leaf. Names the exact leaf to surface next.

    The live eval (2026-07-18, offering_pattern) showed the loop surface an object
    (an offering pattern's term dict) and then re-surface the SAME path four times
    without drilling in -- a no-progress spin straight to budget exhaustion. The
    grounding substrate already made fabrication impossible; this makes a known
    dead-end self-healing, turning "stuck" into a guided next step, in code rather
    than by prompt-tuning the model's choices.

    The same run showed the opposite failure, though: presupposition_conflict
    surfaced a MUTATED STATE object -- whose entire purpose is to be passed whole
    into `check_eligibility(state={"ref": ...})` -- and the flat "do NOT
    re-surface the object itself" told it not to. It spent five turns trying
    other shapes. So the hint steers ANSWER use toward a scalar leaf while
    naming the tool-input use it must not block."""
    if isinstance(value, dict) and value:
        leaf = f"{path}.{sorted(value)[0]}" if path else "one of its fields"
        return (
            f" -- OBJECT: not directly usable IN AN ANSWER. To state a value from it, "
            f"surface a scalar leaf (e.g. path '{leaf}') rather than this object again. "
            f"Passing it whole as a tool argument (e.g. a state) is fine as-is"
        )
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return (
            " -- LIST OF RECORDS: use `select` (a `where` to pick one, or a `field` to "
            "enumerate) to read scalar values from it"
        )
    return ""


def apply_surface(ws: WorkingSet, args: dict[str, Any]) -> int:
    """FETCH. Promote value(s) from recorded tool result(s) into named facts via
    `project_facts` (which reads by path -- the model never types the value). Each
    fact inherits its source call's certainty, resolved PER FIELD (§4.2). Returns
    the count of genuinely-new facts admitted (no-progress signal)."""
    selectors = args.get("selectors")
    if selectors is None:  # single-selector shorthand
        selectors = [{"key": args.get("key"), "from": args.get("from"), "path": args.get("path")}]
    # `field` collapses the corpus's most common two-turn shape. Over 36 live
    # case-runs, turn 1 was `get_entity` 39 times and turn 2 `surface_fact` 51
    # times, with `select` following it 17 more -- surfacing a record list only to
    # project one field out of it next turn. Doing it here costs no extra turn and
    # keeps the same provenance: the list is still READ BY PATH, and the field is
    # read off each record exactly as `select` reads it.
    field = args.get("field") if args.get("selectors") is None else None
    outcome = project_facts(selectors, ws.tool_results, ws.handles)
    selector_by_key = {s.get("key"): s for s in selectors if isinstance(s, dict)}
    new_facts = 0
    for key, fact in outcome.facts.items():
        selector = selector_by_key.get(key, {})
        if field:
            source_records = fact["value"]
            if not isinstance(source_records, list):
                ws.observe(
                    f"surface_fact error: 'field' needs a list at '{selector.get('path')}', "
                    f"got {type(source_records).__name__}"
                )
                continue
            projected = [
                record[field]
                for record in source_records
                if isinstance(record, dict) and field in record
            ]
            if not projected:
                # An empty list would be admitted as a grounded "none" -- exactly
                # how a typo becomes a confident wrong answer.
                ws.observe(
                    f"surface_fact error: no record at '{selector.get('path')}' has field "
                    f"'{field}' (fields: {sorted(source_records[0]) if source_records and isinstance(source_records[0], dict) else 'n/a'})"
                )
                continue
            fact = {**fact, "value": projected}
        signature = f"surface:{selector.get('from')}:{selector.get('path')}:{field or ''}"
        basis, confidence = _selector_certainty(ws, selector, fact["confidence"])
        admitted = ws.admit_derivation(key, Fact(fact["value"], fact["source"], basis, confidence), signature)
        new_facts += int(admitted)
        suffix = "" if admitted else " (already derived; no new info)"
        hint = _grain_hint(selector.get("path"), fact["value"])
        ws.observe(f"surfaced fact '{key}' = {summarize_value(fact['value'])}{suffix}{hint}")
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
            f"grounded facts. Get the number from the data first, then reference it with a ref -- "
            f"never type it as a const. If it is something you can COUNT (how many semesters you "
            f"have completed, how many courses are in a list), use `compute` with op 'count' over "
            f"the relevant list. If it is stated in catalog/wiki prose, interpret_text it and "
            f"surface the result."
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
    # A computed value is only as authoritative as its weakest input: if any ref
    # is qualified (interpreted / predicted / simulated), inherit that basis so
    # the answer renders the result hedged, not as a flat official number (§4.2).
    qualified_refs = [r for r in refs_used if ws.facts[r].basis not in AUTHORITATIVE_BASES]
    basis = ws.facts[min(qualified_refs, key=lambda r: ws.facts[r].confidence)].basis if qualified_refs else "computed"
    signature = f"compute:{json.dumps(raw_expr, sort_keys=True, default=str)}"
    admitted = ws.admit_derivation(key, Fact(value, f"compute({'; '.join(trace)})", basis, confidence), signature)
    suffix = "" if admitted else "  (already computed; no new info)"
    ws.observe(f"computed '{key}' = {value}  [{'; '.join(trace)}]{suffix}")
    return int(admitted)


_COMPARATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def _to_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matches_condition(record_value: Any, condition: Any) -> bool:
    """One field's match test for `select`'s `where`. A scalar condition is
    equality (stringified, so "111" matches int 111 alike); a single-key dict
    like {"gt": 85} or {">": 85} is a numeric comparison that fails closed when
    either side is non-numeric. Supports eq/ne and gt/gte/lt/lte (word or symbol)
    -- the comparison filtering `expression_tree` and a plain equality could not
    express ("which courses did I score above 85 in?")."""
    if isinstance(condition, dict) and len(condition) == 1:
        ((op, threshold),) = condition.items()
        if op in ("eq", "=="):
            return str(record_value) == str(threshold)
        if op in ("ne", "!="):
            return str(record_value) != str(threshold)
        comparator = _COMPARATORS.get(op)
        if comparator is None:
            return False
        left, right = _to_number(record_value), _to_number(threshold)
        return left is not None and right is not None and comparator(left, right)
    return str(record_value) == str(condition)


_REDUCERS = frozenset({"max", "min"})


def _normalize_by(raw: Any) -> tuple[dict[str, str] | None, str | None]:
    """Validate select's optional `by` argmax/argmin reducer. Returns (by, error):
    a clean single-key {"max"|"min": field}, or (None, None) when absent, or
    (None, message) when malformed -- fail closed, never silently ignore a `by`
    the model meant."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict) or len(raw) != 1:
        return None, '"by" must be a single-key object like {"max": "value"} or {"min": "value"}'
    ((direction, by_field),) = raw.items()
    if direction not in _REDUCERS or not isinstance(by_field, str) or not by_field:
        return None, '"by" direction must be "max" or "min" with a field name, e.g. {"max": "value"}'
    return {direction: by_field}, None


def _read_field_path(record: Any, field: str) -> Any:
    """Read `field` off a record, walking dots and flattening lists on the way.

    A semester plan nests `plans[].semesters[].plannedCourses[].courseNumber`, and
    one `select` per level meant `plan_eligibility_sweep` spent four of its eight
    turns navigating -- re-issuing the same three selects on the last two. A
    dotted path collapses that into one call.

    Reading THROUGH a list flattens it, because that is the only sensible reading
    of "the courseNumbers under these semesters". A segment that is absent yields
    nothing rather than a partial value, so a mistyped path is visibly empty
    instead of quietly wrong.
    """
    current: Any = record
    for segment in field.split("."):
        if isinstance(current, list):
            nested = [item.get(segment) for item in current if isinstance(item, dict)]
            current = [item for item in nested if item is not None]
            # Flatten one level per hop, so a list of lists does not compound.
            if any(isinstance(item, list) for item in current):
                current = [leaf for item in current for leaf in (item if isinstance(item, list) else [item])]
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
        if current is None:
            return None
    return current


def filter_records(
    records: list[Any], where: dict[str, Any], field: str | None, by: dict[str, str] | None = None
) -> tuple[Any, int]:
    """Pure select core: filter a list of records by an all-match `where`,
    optionally pick the argmax/argmin record by a field (`by`), then read `field`
    (or the whole record). Returns (value, match_count).

    A single match yields the scalar/record directly; zero or several yield a
    list -- an empty list is a real, grounded answer ("not in that list"), not a
    failure. Each `where` value is an exact match (stringified, so "00940224"
    matches an int/str alike) or a comparison dict like {"gt": 85} (see
    `_matches_condition`).

    `by` is a single-key {"max"|"min": fieldName} reducer -- the grounded ARGMAX a
    `map` result feeds into ("which course was offered in the most semesters" =
    the record maximizing `value`). It collapses the matched set to the single
    extremal record; records whose by-field is non-numeric are ignored, and with
    no numeric candidate it selects nothing (empty result -- itself grounded).
    """
    # A DOTTED field walks inward, so `where` has to travel with it -- otherwise
    # the filter tests the outer records for a field that only exists on the
    # nested ones, matches nothing, and returns an empty list the substrate reads
    # as a grounded "not there". That shipped: "I could not find it in your
    # spring plan either", about a course that was in the plan (2026-07-19).
    #
    # So for a dotted path, walk FIRST and filter the records it lands on. The
    # leaf field (if the path ends at one) is read after filtering. A plain field
    # keeps filtering the outer records, exactly as every existing caller expects.
    def _apply_where(rows: list[Any]) -> list[Any]:
        return [
            r
            for r in rows
            if isinstance(r, dict) and all(_matches_condition(r.get(k), cond) for k, cond in where.items())
        ]

    matched = _apply_where(records)
    if where and not matched and field is not None and "." in field:
        # The filter named a field that lives on the NESTED records, not these --
        # so it matched nothing and returned [], which the substrate reads as a
        # grounded "not there". That shipped: "I could not find it in your spring
        # plan either", about a course that was in the plan (2026-07-19).
        #
        # Only reached when the outer filter found NOTHING, so a `where` that
        # legitimately describes the outer record keeps its existing meaning.
        # Two depths can hold the filtered records: the path's own end (
        # "semesters.plannedCourses" filtered by courseNumber) or its parent (
        # "...plannedCourses.credits", where the filter names a sibling of the
        # leaf). Try the end first, then the parent; the leaf is read after.
        head, _, leaf = field.rpartition(".")
        for path, remaining_field in ((field, None), (head, leaf)):
            if not path:
                continue
            reached = _read_field_path({"_": records}, f"_.{path}")
            candidates = reached if isinstance(reached, list) else [reached]
            deeper = _apply_where(candidates)
            if deeper:
                matched, field = deeper, remaining_field
                break
    if by is not None:
        ((direction, by_field),) = by.items()
        keyed = [(r, _to_number(r.get(by_field))) for r in matched]
        keyed = [(record, number) for record, number in keyed if number is not None]
        if keyed:
            extremum = max if direction == "max" else min
            matched = [extremum(keyed, key=lambda pair: pair[1])[0]]
        else:
            matched = []
    if field is not None:
        picked = [_read_field_path(r, field) for r in matched]
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
    by, by_error = _normalize_by(args.get("by"))
    if by_error:
        ws.observe(f"select error: {by_error}")
        return 0
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

    value, match_count = filter_records(source.value, where, field, by)
    by_label = f" {next(iter(by))} by {next(iter(by.values()))}" if by else ""
    label = f"select({from_fact} where {where}{by_label}" + (f").{field}" if field else ")")
    signature = (
        f"select:{from_fact}:{json.dumps(where, sort_keys=True, default=str)}:{field}"
        f":{json.dumps(by, sort_keys=True, default=str)}"
    )
    admitted = ws.admit_derivation(key, Fact(value, label, source.basis, source.confidence), signature)
    suffix = "" if admitted else " (already selected; no new info)"
    ws.observe(f"selected '{key}' = {summarize_value(value)} ({match_count} match(es)){suffix}")
    return int(admitted)


def project_mapped_records(
    elements: list[Any], envelopes: list[Any], select_path: str | None
) -> tuple[list[dict[str, Any]], str, float, list[str]]:
    """Pure core of `map` (§19): given the source `elements` and their per-element
    result `envelopes` (aligned by index), project `select_path` out of each OK
    envelope and build grounded `{"entity": element, "value": projected}` records.
    Returns (records, basis, confidence, errors).

    The value is READ from the envelope by path -- never typed -- so each record
    is grounded exactly as surface_fact's facts are. Certainty follows the WEAKEST
    input, like `apply_compute`: any qualified element (predicted/interpreted/
    simulated) makes the whole collected list qualified, so an argmax over it
    renders hedged rather than as a flat official number. A failed call or a
    missing path is skipped with a repairable error, never guessed."""
    records: list[dict[str, Any]] = []
    pairs: list[tuple[str, float]] = []
    errors: list[str] = []
    for element, envelope in zip(elements, envelopes):
        if not isinstance(envelope, dict) or not envelope.get("ok"):
            reason = envelope.get("error") if isinstance(envelope, dict) else "no result"
            errors.append(f"{element}: {reason}")
            continue
        if select_path:
            value, found = resolve_path(envelope, select_path)
            if not found:
                errors.append(f"{element}: path '{select_path}' not found")
                continue
        else:
            value = envelope.get("data")
        records.append({"entity": element, "value": value})
        pairs.append(_envelope_field_certainty(envelope, select_path, 0.5))
    confidence = min((conf for _, conf in pairs), default=1.0)
    qualified = [(basis, conf) for basis, conf in pairs if basis not in AUTHORITATIVE_BASES]
    basis = min(qualified, key=lambda pair: pair[1])[0] if qualified else "computed"
    return records, basis, confidence, errors


__all__ = [
    "apply_surface",
    "apply_compute",
    "apply_select",
    "numeric_const_operands",
    "filter_records",
    "project_mapped_records",
]
