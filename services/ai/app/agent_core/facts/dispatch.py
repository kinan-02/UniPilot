"""Dispatch -- phase 9d of docs/agent/tools_implementation_plan.md.

Routes a parsed tool call to one of the eight primitives and admits what comes
back as a named fact.

The thing that makes the layer compose is that tool arguments name FACTS, not
data. `compute` reads pipelines whose sources are held facts, `traverse` walks a
held edge collection, `optimize` places held items into held slots. So the
working set is the only channel between tools, and no tool ever receives a
payload the model typed out -- which is what stops a model hand-copying a
transcript into an argument and reshaping it on the way.

Every tool call names its result with `as`, except `compute`, whose pipelines
name themselves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Union

from app.agent_core.facts.answer import HeldFact
from app.agent_core.facts.catalog import tool_names
from app.agent_core.facts.codec import ParseError, parse_pipelines, parse_predicate
from app.agent_core.facts.find import SourceSchema, find
from app.agent_core.facts.forecast import forecast
from app.agent_core.facts.operators import DataDefect, Defect, ExpressionDefect
from app.agent_core.facts.optimize import (
    Capacity,
    Eligibility,
    Infeasible,
    Item,
    Objective,
    Precedence,
    Slot,
    optimize,
)
from app.agent_core.facts.predicate import (
    Always,
    And,
    Comparison,
    FactRef,
    Not,
    Op,
    Or,
    Path,
    Predicate,
)
from app.agent_core.facts.propose import Proposal, propose
from app.agent_core.facts.prose import Passage, interpret, interpret_list, search_corpus
from app.agent_core.facts.runner import Blocked, Failed, Succeeded, run_pipelines
from app.agent_core.facts.traverse import traverse
from app.agent_core.facts.types import Basis, Collection, Scalar, ScalarKind


@dataclass
class DispatchContext:
    """Everything a tool might need, and the working set it reads and writes."""

    facts: dict[str, HeldFact] = field(default_factory=dict)
    schemas: Mapping[str, SourceSchema] = field(default_factory=dict)
    database: Any = None
    retriever: Any = None
    extractor: Any = None
    passages: dict[str, Passage] = field(default_factory=dict)
    obtainable: frozenset[str] = frozenset()
    """Input kinds the MODEL can obtain by calling tools -- e.g. "edges", "slots".

    A tool needing one it cannot get is not advertised. Empty by default,
    because the honest default is "this cannot be fed" rather than "assume it
    can": the first version assumed, and advertised two tools the model had no
    route to.
    """

    def collection(self, name: str) -> Union[Collection, ExpressionDefect]:
        held = self.facts.get(name)
        if held is None:
            return ExpressionDefect(0, f"no fact named '{name}'; held: {sorted(self.facts)}")
        if not isinstance(held.value, Collection):
            return ExpressionDefect(0, f"'{name}' is a scalar, but a collection is needed here")
        return held.value


@dataclass(frozen=True)
class Dispatched:
    """What a call produced: named facts, plus per-name defects.

    Both, not either. `compute` can succeed on four pipelines and fail on a
    fifth, and discarding the four would make the loop redo work that was
    already right.
    """

    facts: dict[str, HeldFact] = field(default_factory=dict)
    defects: dict[str, Defect] = field(default_factory=dict)
    proposal: Proposal | None = None


async def dispatch(call: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    tool = call.get("tool")
    if tool not in tool_names():
        return _defect(
            "call",
            ExpressionDefect(0, f"unknown tool {tool!r}; available: {sorted(tool_names())}"),
        )

    args = call.get("args") or {}
    name = call.get("as")

    if tool != "compute" and not name:
        return _defect(
            "call",
            ExpressionDefect(
                0,
                f"'{tool}' needs an 'as' naming its result, so later calls can refer to it. "
                "(Only 'compute' is exempt -- its pipelines name themselves.)",
            ),
        )

    try:
        handler = _HANDLERS[tool]
        return await handler(name, args, context)
    except ParseError as error:
        return _defect(name or "call", ExpressionDefect(0, str(error)))
    except Exception as error:  # noqa: BLE001 -- see below; this must not be narrowed
        # Defense in depth. A malformed tool request must come back as a DEFECT
        # the loop can report and the model can repair -- never as an exception
        # that ends the run.
        #
        # Live run, case 1: the model wrote `"start": {"fact": "course_number"}`,
        # generalising the `{"fact": ...}` idiom that works in every predicate
        # value. `traverse` did `seen = {start}` on a dict, and the resulting
        # `TypeError: unhashable type: 'dict'` unwound through the loop and
        # aborted the whole eval on question two of ten. One bad argument shape
        # cost nine questions.
        #
        # The specific shape is now accepted (`_literal` below), but the blanket
        # guard stays: the next unhandled shape must cost one defect, not a run.
        return _defect(
            name or "call",
            ExpressionDefect(
                0,
                f"'{tool}' could not run with those arguments -- "
                f"{type(error).__name__}: {error}. Check the argument shapes against the "
                "tool's example.",
            ),
        )


def _defect(name: str, defect: Defect) -> Dispatched:
    return Dispatched(defects={name: defect})


def _fact(
    name: str, value: Any, basis: Basis, citation: Any = None, derivation: str | None = None
) -> Dispatched:
    return Dispatched(
        facts={name: HeldFact(value=value, basis=basis, citation=citation, derivation=derivation)}
    )


def _resolve_fact_refs(
    predicate: Predicate, context: DispatchContext
) -> Union[Predicate, ExpressionDefect]:
    """Replace every `FactRef` with the value of the fact it names.

    Done here rather than in the grammar because the working set is only in
    scope at dispatch. An unresolvable reference is refused loudly: filtering by
    a fact that does not exist would otherwise match nothing and return a
    legitimate-looking empty result, which is the failure mode that cost several
    live turns.
    """
    if isinstance(predicate, Always):
        return predicate
    if isinstance(predicate, Not):
        inner = _resolve_fact_refs(predicate.term, context)
        return inner if isinstance(inner, ExpressionDefect) else Not(inner)
    if isinstance(predicate, (And, Or)):
        terms = []
        for term in predicate.terms:
            resolved = _resolve_fact_refs(term, context)
            if isinstance(resolved, ExpressionDefect):
                return resolved
            terms.append(resolved)
        return type(predicate)(tuple(terms))

    if not isinstance(predicate.value, FactRef):
        return predicate

    ref = predicate.value
    held = context.facts.get(ref.name)
    if held is None:
        return ExpressionDefect(
            0,
            f"the filter refers to fact '{ref.name}', which is not held. "
            f"Available: {sorted(context.facts)}.",
        )

    if ref.field is not None:
        # A field drawn from a held collection: the SET (with `in`, a semi-join)
        # or the SINGLE value (with `=`, one-record extraction). Both because the
        # model reaches for both.
        return _resolve_field_ref(predicate, ref, held)

    if not isinstance(held.value, Scalar):
        return ExpressionDefect(
            0,
            f"fact '{ref.name}' is a collection; a filter value must be a single value. To match "
            f'against a field of it, add "field": {{...}} for a set membership test, or aggregate '
            "it to one value first.",
        )
    return Comparison(predicate.path, predicate.op, held.value)


def _resolve_field_ref(
    predicate: Comparison, ref: FactRef, held: HeldFact
) -> Union[Comparison, ExpressionDefect]:
    """`FactRef(name, field)` -> the field's value(s) from a held collection.

    Two readings, chosen by the operator, because the model reaches for BOTH:
      - `in`  -> the SET of that field's values across the collection (semi-join)
      - `=`, `<`, ... -> the SINGLE value, when the collection holds exactly one
        record. This is the same one-record extraction `only` does, and a live
        run hit the wall without it: the model held one course in `next_course`
        and wrote `course = {"fact": "next_course", "field": "courseNumber"}`
        turn after turn, which is exactly right and used to be refused.
    """
    if not isinstance(held.value, Collection):
        return ExpressionDefect(
            0, f"fact '{ref.name}' is a single value, so it has no field '{ref.field}' to draw from."
        )

    path = Path.parse(ref.field)
    values: list[Scalar] = []
    seen: set = set()
    for record in held.value.records:
        resolved = path.resolve(record)
        if not isinstance(resolved, Scalar):
            return ExpressionDefect(
                0,
                f"'{ref.field}' is missing on a record of '{ref.name}', so the value would be "
                "silently omitted. Every record must carry the field a fact-reference draws on.",
            )
        if resolved.value not in seen:
            seen.add(resolved.value)
            values.append(resolved)

    if predicate.op is Op.IN:
        return Comparison(predicate.path, predicate.op, tuple(values))

    # A scalar operator wants ONE value.
    if len(values) != 1:
        return ExpressionDefect(
            0,
            f"'{ref.name}.{ref.field}' has {len(values)} distinct values, but '{predicate.op.value}' "
            "compares against one. Use 'in' to match the whole set, or filter the fact to a single "
            "record first.",
        )
    return Comparison(predicate.path, predicate.op, values[0])


async def _find(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    source = args.get("source")
    schema = context.schemas.get(source)
    if schema is None:
        return _defect(name, ExpressionDefect(0, f"unknown source {source!r}; available: {sorted(context.schemas)}"))

    predicate = parse_predicate(args["predicate"]) if args.get("predicate") else None
    if predicate is not None:
        predicate = _resolve_fact_refs(predicate, context)
        if isinstance(predicate, ExpressionDefect):
            return _defect(name, predicate)
    result = await find(context.database, schema, predicate=predicate, limit=args.get("limit", 200))
    if isinstance(result, (ExpressionDefect, DataDefect)):
        return _defect(name, result)
    filtered = " matching a filter" if predicate is not None else ""
    return _fact(name, result, schema.basis, derivation=f"read from {schema.collection}{filtered}")


async def _search_corpus(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    if context.retriever is None:
        return _defect(name, ExpressionDefect(0, "no corpus is configured, so prose cannot be searched here"))
    hits = await search_corpus(context.retriever, args.get("query", ""), limit=args.get("limit", 5))
    # Remember the passages so `interpret`/`extract_list` can be handed one by
    # slug rather than having the model retype its text -- retyped prose is prose
    # that can drift.
    #
    # ACCUMULATE per slug, do not overwrite. The wiki is heading-segmented, so one
    # page comes back as several chunks that all share its slug; keyed by slug
    # alone, the last chunk clobbered the rest, and `extract_list("track-ise")`
    # then saw only the final section. A live plan lost the whole Faculty-Elective
    # course list exactly this way -- the electives chunk was overwritten by a
    # later one, so the set came back with a single code. Concatenating every
    # retrieved chunk of a page (capped) means the slug names the page's content,
    # which is what the model reasonably expects.
    for record in hits.records:
        slug = record.fields["slug"].value
        excerpt = record.fields["excerpt"].value
        prior = context.passages.get(slug)
        if prior is not None and excerpt not in prior.excerpt:
            excerpt = f"{prior.excerpt}\n\n{excerpt}"[:_PASSAGE_STASH_CAP]
        context.passages[slug] = Passage(
            slug=slug,
            title=record.fields["title"].value,
            excerpt=excerpt,
            score=record.fields["score"].value,
        )
    return _fact(name, hits, Basis.WIKI_DERIVED)


_PASSAGE_STASH_CAP = 8000
"""How much of a page's concatenated chunks the stash keeps for a later
`interpret`/`extract_list`. Room for several sections (a track's required list
AND its electives), short of an unbounded prompt."""


async def _interpret(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    if context.extractor is None:
        return _defect(name, ExpressionDefect(0, "no interpreter is configured, so prose cannot be read here"))
    slug = _literal(args, "slug", context)
    if isinstance(slug, ExpressionDefect):
        return _defect(name, slug)
    passage = context.passages.get(slug)
    if passage is None:
        return _defect(
            name,
            ExpressionDefect(0, f"no retrieved passage '{slug}'; search first. Retrieved: {sorted(context.passages)}"),
        )

    expect = args.get("expect", "text")
    kinds = {kind.value: kind for kind in ScalarKind}
    if expect not in kinds:
        return _defect(name, ExpressionDefect(0, f"unknown expect {expect!r}; available: {sorted(kinds)}"))

    result = await interpret(context.extractor, passage, args.get("question", ""), expect=kinds[expect])
    if isinstance(result, DataDefect):
        return _defect(name, result)
    return _fact(name, result.value, result.basis, citation=result.citation)


async def _extract_list(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    """The plural of `interpret`: the SET of values a retrieved passage lists.

    Same shape as `_interpret` -- a passage is named by the slug `search_corpus`
    already stashed -- but the result is a COLLECTION (records with one `value`
    field) so the model can `select ... in {this, field: "value"}` to classify a
    set of records against what the wiki enumerates, instead of one model call
    per candidate.
    """
    if context.extractor is None:
        return _defect(name, ExpressionDefect(0, "no interpreter is configured, so prose cannot be read here"))
    slug = _literal(args, "slug", context)
    if isinstance(slug, ExpressionDefect):
        return _defect(name, slug)
    passage = context.passages.get(slug)
    if passage is None:
        return _defect(
            name,
            ExpressionDefect(0, f"no retrieved passage '{slug}'; search first. Retrieved: {sorted(context.passages)}"),
        )

    expect = args.get("expect", "identifier")
    kinds = {kind.value: kind for kind in ScalarKind}
    if expect not in kinds:
        return _defect(name, ExpressionDefect(0, f"unknown expect {expect!r}; available: {sorted(kinds)}"))

    result = await interpret_list(context.extractor, passage, args.get("question", ""), expect=kinds[expect])
    if isinstance(result, DataDefect):
        return _defect(name, result)
    return _fact(name, result.value, result.basis, citation=result.citation)


async def _compute(_name: Any, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    pipelines = parse_pipelines(args.get("pipelines", []))
    # `select` inside a pipeline gets the same treatment as `find`'s predicate.
    for pipeline in pipelines:
        for stage in pipeline.stages:
            if "predicate" in stage.args:
                resolved = _resolve_fact_refs(stage.args["predicate"], context)
                if isinstance(resolved, ExpressionDefect):
                    return Dispatched(defects={pipeline.name: resolved})
                stage.args["predicate"] = resolved
    # EVERY held fact, scalars included. The runner publishes and consumes
    # scalars deliberately -- that is how "spring total vs autumn total" works --
    # and filtering them out here made a computed value unreferenceable by the
    # very next pipeline. A live run held both operands of a subtraction and
    # could not express it.
    env = {name: held.value for name, held in context.facts.items()}

    outcomes = run_pipelines(pipelines, env)

    produced: dict[str, HeldFact] = {}
    defects: dict[str, Defect] = {}
    for name, outcome in outcomes.items():
        if isinstance(outcome, Succeeded):
            pipeline = next((p for p in pipelines if p.name == name), None)
            produced[name] = HeldFact(
                value=outcome.value,
                basis=outcome.basis,
                derivation=_describe_pipeline(pipeline) if pipeline else None,
            )
        elif isinstance(outcome, Failed):
            defects[name] = outcome.defect
        elif isinstance(outcome, Blocked):
            defects[name] = ExpressionDefect(0, f"not run: it depends on '{outcome.waiting_on}', which failed")
    return Dispatched(facts=produced, defects=defects)


def _describe_pipeline(pipeline: Any) -> str:
    """A one-line account of how a pipeline's result was produced.

    Deliberately mechanical -- the stage names and the fields they touched --
    because the point is to show what the value IS, independently of what the
    model chose to call it.
    """
    steps = []
    for stage in pipeline.stages:
        detail = stage.args.get("path") or stage.args.get("on") or stage.args.get("other")
        function = stage.args.get("op")
        label = stage.op
        if function is not None and stage.op in ("aggregate", "arith", "compare"):
            label = f"{stage.op}:{getattr(function, 'value', function)}"
        steps.append(f"{label}({getattr(detail, 'dotted', detail)})" if detail else label)
    return f"{pipeline.source} -> " + " -> ".join(steps) if steps else pipeline.source


def _literal(
    args: Mapping[str, Any], key: str, context: DispatchContext, default: str = ""
) -> Union[str, ExpressionDefect]:
    """A model-supplied scalar argument, accepting the `{"fact": name}` idiom.

    The model generalised that idiom here from predicate values, where it is
    required, and it was right to: `traverse`'s start course is exactly the kind
    of value that should come from a fact rather than be retyped. Retyping it is
    how a computed identifier gets laundered into a literal.

    So the instinct is honoured rather than corrected -- but a name that does not
    resolve is refused loudly, because a `start` that silently became the string
    "{'fact': 'x'}" would traverse from a node that does not exist and return an
    empty result that looks like "nothing is required".
    """
    value = args.get(key, default)
    if not isinstance(value, Mapping):
        return str(value)

    if "fact" not in value:
        return ExpressionDefect(
            0, f"'{key}' must be a value or {{\"fact\": \"name\"}}; got an object with {sorted(value)}"
        )
    held = context.facts.get(value["fact"])
    if held is None:
        return ExpressionDefect(
            0,
            f"'{key}' refers to fact '{value['fact']}', which is not held. "
            f"Available: {sorted(context.facts)}.",
        )
    if not isinstance(held.value, Scalar):
        return ExpressionDefect(
            0, f"'{key}' refers to '{value['fact']}', which is a collection; a single value is needed."
        )
    return str(held.value.value)


async def _traverse(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    edges = context.collection(args.get("edges", ""))
    if isinstance(edges, ExpressionDefect):
        return _defect(name, edges)
    start = _literal(args, "start", context)
    if isinstance(start, ExpressionDefect):
        return _defect(name, start)
    reached = traverse(
        edges,
        start=start,
        from_path=Path.parse(args.get("from", "from")),
        to_path=Path.parse(args.get("to", "to")),
        max_depth=args.get("max_depth", 10),
        carry=tuple(args.get("carry", ())),
    )
    basis = min((r.basis for r in reached.records), key=lambda b: b.strength, default=Basis.OFFICIAL_RECORD)
    return _fact(name, reached, basis)


async def _forecast(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    observations = context.collection(args.get("observations", ""))
    if isinstance(observations, ExpressionDefect):
        return _defect(name, observations)
    target = _literal(args, "target", context)
    if isinstance(target, ExpressionDefect):
        return _defect(name, target)
    result = forecast(
        observations,
        period_path=Path.parse(args.get("period_path", "period")),
        target=target,
    )
    if isinstance(result, DataDefect):
        return _defect(name, result)
    return _fact(name, result.value, result.basis)


async def _optimize(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    items_source = context.collection(args.get("items", ""))
    if isinstance(items_source, ExpressionDefect):
        return _defect(name, items_source)
    slots_source = context.collection(args.get("slots", ""))
    if isinstance(slots_source, ExpressionDefect):
        return _defect(name, slots_source)

    # Identity is NAMED, never guessed. The first version scanned for the first
    # field called id/item/slot/courseNumber/node and fell back to "whatever
    # scalar came first" -- which, on real slots produced by unnesting a plan's
    # semesters, handed every slot the parent plan's `_id`. Slots sharing an id
    # silently pool their capacity, so the solver would return a plan that
    # violates the very limit it was given, and nothing would say so.
    # ITEMS are de-duplicated by their id, keeping the first occurrence. A course
    # offered in two semesters is still ONE course to place, and the natural way
    # to build items -- join the remaining courses to their offerings -- yields
    # one row per offering, so the same course appears twice. Rejecting that sent
    # the model into a dedup fight it kept losing on the last mile of a plan.
    # SLOTS stay strict: two slots sharing an id silently pool capacity, which is
    # the bug the uniqueness check was added for, so that one is not relaxed.
    item_records = _dedup_by(items_source.records, args.get("item_id"))
    if isinstance(item_records, ExpressionDefect):
        return _defect(name, item_records)
    item_ids = _identify(item_records, args.get("item_id"), "item_id", "items")
    if isinstance(item_ids, ExpressionDefect):
        return _defect(name, item_ids)
    slot_ids = _identify(slots_source.records, args.get("slot_id"), "slot_id", "slots")
    if isinstance(slot_ids, ExpressionDefect):
        return _defect(name, slot_ids)

    items = tuple(
        Item(id=identity, attributes={k: v for k, v in record.fields.items() if isinstance(v, Scalar)})
        for identity, record in zip(item_ids, item_records)
    )

    index_path = args.get("slot_index")
    slots = tuple(
        Slot(
            id=identity,
            # Position is the honest default: `find` sorts by key and `unnest`
            # preserves array order, so the sequence is already deterministic.
            index=int(_quantity(record, index_path, default=position)) if index_path else position,
            attributes={k: v for k, v in record.fields.items() if isinstance(v, Scalar)},
        )
        for position, (identity, record) in enumerate(zip(slot_ids, slots_source.records))
    )

    constraints = []
    for raw in args.get("constraints", ()):
        kind = raw.get("kind")
        if kind == "precedence":
            constraints.append(Precedence(before=raw["before"], after=raw["after"]))
        elif kind == "capacity":
            constraints.append(Capacity(attribute=raw["attribute"], limit=float(raw["limit"])))
        elif kind == "eligibility":
            constraints.append(Eligibility(item=raw["item"], slot_predicate=parse_predicate(raw["slot"])))
        else:
            return _defect(
                name,
                ExpressionDefect(0, f"unknown constraint kind {kind!r}; available: precedence, capacity, eligibility"),
            )

    objectives = {o.value: o for o in Objective}
    objective = objectives.get(args.get("objective", "minimize_slots"))
    if objective is None:
        return _defect(name, ExpressionDefect(0, f"unknown objective; available: {sorted(objectives)}"))

    result = optimize(items=items, slots=slots, constraints=tuple(constraints), objective=objective)
    if isinstance(result, Infeasible):
        return _defect(name, DataDefect(0, result.reason))
    return _fact(name, result.assignment, Basis.SIMULATED)


async def _propose(name: str, args: Mapping[str, Any], context: DispatchContext) -> Dispatched:
    grounds = tuple(args.get("grounds", ()))
    missing = [g for g in grounds if g not in context.facts]
    if missing:
        return _defect(
            name,
            ExpressionDefect(0, f"grounds name facts that are not held: {missing}. Held: {sorted(context.facts)}"),
        )

    action = _literal(args, "action", context)
    target = _literal(args, "target", context)
    for resolved in (action, target):
        if isinstance(resolved, ExpressionDefect):
            return _defect(name, resolved)

    try:
        proposal = propose(
            action=action,
            target=target,
            payload={k: Scalar(ScalarKind.IDENTIFIER, str(v)) for k, v in (args.get("payload") or {}).items()},
            grounds=grounds,
            # A proposal is only as sound as the weakest thing behind it.
            basis=min((context.facts[g].basis for g in grounds), key=lambda b: b.strength),
        )
    except ValueError as error:
        return _defect(name, ExpressionDefect(0, str(error)))

    return Dispatched(proposal=proposal)


def _dedup_by(records: Sequence[Any], path: Any) -> Union[tuple[Any, ...], ExpressionDefect]:
    """Records with a unique value at `path`, keeping the FIRST of each.

    So the same course reached through two offerings collapses to one item. The
    first occurrence wins, which keeps the result deterministic (`find` and
    `unnest` both preserve a stable order).
    """
    if not path:
        return ExpressionDefect(
            0,
            "'item_id' is required: name the field that identifies each item, so duplicates from a "
            "join can be collapsed to one.",
        )
    resolved = Path.parse(getattr(path, "dotted", str(path)))
    seen: set = set()
    kept: list[Any] = []
    for record in records:
        value = resolved.resolve(record)
        key = value.value if isinstance(value, Scalar) else None
        if key is not None and key not in seen:
            seen.add(key)
            kept.append(record)
    return tuple(kept)


def _identify(
    records: Sequence[Any], path: Any, argument: str, what: str
) -> Union[tuple[str, ...], ExpressionDefect]:
    """The identity of every record, read from a named field.

    Refuses three things a guess would have swallowed: no field named, the
    field missing on a record, and two records sharing an identity. The last
    matters most -- `optimize` keys placement and capacity by id, so duplicates
    do not collide loudly, they merge: two semesters become one slot with twice
    the room, or one course silently replaces another in the plan.
    """
    if not path:
        return ExpressionDefect(
            0,
            f"'{argument}' is required: name the field that identifies each of the {what}, e.g. "
            f'"{argument}": "courseNumber". It is not guessed, because guessing wrong produces a '
            "plan that looks valid and is not.",
        )

    dotted = getattr(path, "dotted", str(path))
    resolved = Path.parse(dotted)
    identities: list[str] = []
    for record in records:
        value = resolved.resolve(record)
        if not isinstance(value, Scalar):
            return ExpressionDefect(
                0,
                f"a record in {what} has no '{dotted}' to identify it. Available fields: "
                f"{sorted(record.fields)}.",
            )
        identities.append(str(value.value))

    duplicates = sorted({name for name in identities if identities.count(name) > 1})
    if duplicates:
        return ExpressionDefect(
            0,
            f"'{dotted}' is not unique across {what}: {duplicates[:5]} appear more than once. "
            "Identities are pooled, so duplicates would quietly merge two of them into one.",
        )
    return tuple(identities)


def _quantity(record: Any, path: Any, default: float) -> float:
    dotted = getattr(path, "dotted", str(path))
    value = Path.parse(dotted).resolve(record)
    return float(value.value) if isinstance(value, Scalar) and value.is_quantity else default


_HANDLERS = {
    "find": _find,
    "search_corpus": _search_corpus,
    "interpret": _interpret,
    "extract_list": _extract_list,
    "compute": _compute,
    "traverse": _traverse,
    "forecast": _forecast,
    "optimize": _optimize,
    "propose": _propose,
}


__all__ = ["DispatchContext", "Dispatched", "dispatch"]
