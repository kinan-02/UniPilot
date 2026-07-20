# Tools — Design & Implementation Plan

**Status:** design, not yet implemented. **Date:** 2026-07-19.

This is a from-scratch design of the agent's tool layer. It is not a migration of
the existing tools and it does not preserve their contracts. The rest of the
agent — loop, working set, answer boundary — is expected to be redesigned around
this, not the reverse.

---

## 0. Method, and what is *not* allowed to shape this design

The tool set is derived from two things only:

1. **The data that exists in the world** — Mongo records and the wiki prose
   corpus. This is the domain, not an implementation detail, and designing
   against imaginary data would be the deeper error.
2. **Computational classes** — what kinds of operation are irreducible to each
   other, on expressiveness grounds.

Explicitly **not** inputs:

- Observed questions. A set derived from questions we have run is adequate for
  those questions plus whatever we happened to generalise; question *n+1* breaks
  it and the fix is another tool. That is a treadmill, and it is the thing this
  design exists to get off.
- Registers of past failures. Same inductive error with a different source.
- What is currently implemented, and what previous documents concluded.

A capability earns a place here only if it cannot be expressed by the others.
"We saw a question that needed it" is not a justification. Neither is "it already
exists."

**Consequence to accept up front:** a complete basis will be *slower* on some
questions than a pre-solved shortcut, because a shortcut is one call and a
derivation is several operators. That trade is the point. Shortcuts are
reintroducible later as declared sugar (§3.8), never as new capability.

---

## 1. The data

Two kinds, and one derived kind:

| kind | shape | grounding |
|---|---|---|
| **records** | Mongo documents: students, courses, degree programs, semester plans. Nested objects and arrays. References between collections. | provenance — the record was read |
| **prose** | wiki pages: slug, title, content | citation — a passage was quoted |
| **hypothetical** | a record collection the user asked us to vary | simulated — derived under an assumption |

Everything else the agent knows is *derived* from these.

---

## 2. The derivation

A capability is primitive iff it is not expressible in the others. Each row below
names the boundary that makes it irreducible.

| primitive | boundary |
|---|---|
| `find` | The algebra is closed over facts; no operator produces a fact from nothing. Something must admit records. |
| `search_corpus` | Relevance ranking over natural-language text is not an algebraic operation over records. |
| `interpret` | Converting prose to a typed claim requires inference. No algebra maps text to a fact. |
| `compute` | The algebra itself (§3). |
| `traverse` | **Transitive closure is provably outside relational algebra.** This is a theorem, not a convenience — it is why SQL required `WITH RECURSIVE`. Prerequisite chains need it. |
| `optimize` | Constrained search over a solution space is not query evaluation. Plan generation cannot be expressed as a derivation over existing facts. |
| `forecast` | Projecting a time series forward with confidence is statistical inference, not evaluation. Counting past occurrences is algebra; extrapolating is not. |
| `propose` | An effect is not a derivation. The only tool that changes the world, and only as a human-gated proposal. |

Seven derivation-side primitives plus one effect. Nothing here is justified by a
question, a resource bound, or an audit convenience.

### 2.1 What deliberately does *not* exist

- **No identity-fetch primitive.** Fetching by id is `find` with the predicate
  `id == X`. A separate tool would be two admission paths for one operation.
- **No clock primitive.** "Now" is injected into turn context as a grounded
  fact. Spending a tool call and a turn to retrieve a constant is pure waste.
- **No counterfactual primitive.** "If I fail X" is
  `difference(completed, select(completed, id == X))` — already expressible.
  It needed a primitive only to stamp certainty, which §3.6 solves generally.
- **No answer-composition primitive.** Composing the answer is the loop's
  responsibility and is deterministic. It is not a capability the model selects.

---

## 3. `compute` — the algebra

The single most important component. If it is incomplete, capability must be
re-added as pre-solved shortcuts, and the treadmill restarts.

### 3.1 Types

```
Scalar     = Quantity | Identifier | Text | Bool | Date
Record     = { name -> Scalar | Record | Collection }
Collection = [Record] | [Scalar]
```

`Quantity` vs `Identifier` is a real distinction, not a formatting one: a course
code is an identifier that happens to be digits. Typing it prevents summing
course codes, and removes any need to infer intent from string shape.

Field references are **paths** (`profile.completedCourses.grade`), not flat
names, because the data is nested.

### 3.2 Operand positions

Grounding is enforced per operand slot, declared in the operator table:

| position | literals | rationale |
|---|---|---|
| **data** | forbidden — must be a ref | a literal here is a laundered computed value, the class of bug the grounding invariant exists to stop |
| **criterion** | allowed | `grade > 90` — the threshold comes from the question, not from the world |
| **structural** | required | `limit 1`, sort direction, field paths — not data at all |

A criterion that later *becomes* a claim is caught independently at the answer
boundary, which rejects ungrounded numbers in the answer. Two checks, neither
redundant.

### 3.3 Operators

Closed: every output type is a legal input type.

| operator | signature |
|---|---|
| `select` | Collection × Predicate → Collection |
| `project` | Collection × [Path] → Collection |
| `extend` | Collection × {name: ScalarExpr} → Collection |
| `join` | Collection × Collection × Path × Path → Collection |
| `union` | Collection × Collection → Collection |
| `difference` | Collection × Collection → Collection |
| `distinct` | Collection → Collection |
| `unnest` | Collection × Path → Collection |
| `group` | Collection × [Path] × {name: (agg, Path)} → Collection |
| `aggregate` | Collection × Path? × {count, sum, avg, min, max} → Scalar |
| `sort` | Collection × Path × dir → Collection |
| `limit` | Collection × Quantity → Collection |
| `arith` | Scalar × Scalar × {+, −, ×, ÷} → Scalar |
| `compare` | Scalar × Scalar × {=, ≠, <, ≤, >, ≥} → Bool |

**`extend` is load-bearing, not a convenience.** A `ScalarExpr` is a scalar tree
whose leaves are paths on the record being extended. Without it the basis has
collection operators and scalar operators and no way to compute *per record*, so
a credit-weighted average — `sum(grade × credits) ÷ sum(credits)` — is
inexpressible, because `aggregate` consumes a path and nothing produces the
product. This is relational algebra's *generalized projection*; omitting it was a
real hole in the first draft of this table, caught by hand-tracing §5.2.

`extend` is also what makes a computed `Bool` usable: a per-record predicate
result becomes a field, and `select` then filters on it. Without it, `compare`'s
output can only ever be a final answer, never an intermediate.

`aggregate`'s path is optional only for `count`, which counts records rather
than values.

**Relational completeness.** Codd's basis is selection, projection, product,
union, difference, rename.

- `select`, `project`, `union`, `difference` — present.
- **product** — `join` on a constant-true predicate. The predicate grammar
  (§3.4) must therefore admit a constant-true predicate, or the basis is
  incomplete. This is a requirement, not an observation.
- **rename** — `join` qualifies colliding field names as `left.x` / `right.x`.
  This is rename under another name and it is **required**, not optional: a
  self-join ("courses sharing a prerequisite with X") is unexpressible without
  it.

`group`, `aggregate`, `sort`, `limit` are the aggregation and ordering
extensions beyond relational algebra proper. `unnest` handles nesting, which
flat relational algebra does not model.

**`unnest` preserves parent fields.** It emits one record per element of the
named array, each carrying the fields of the record it came from — the semantics
of SQL's lateral unnest. Returning the bare inner array instead would discard
which parent each element belonged to, making any subsequent `group` or `join`
on parent identity impossible.

**Scope of the completeness claim.** This basis is *relationally complete plus
aggregation and ordering*. That explicitly does **not** mean it can express
anything — it provably cannot express transitive closure, which is why
`traverse` exists as a separate primitive. Any claim that the algebra is
"complete" without this qualifier is wrong.

### 3.4 Predicates

A closed grammar — no expression strings, no `eval`:

```
Predicate  = Comparison | And[Predicate] | Or[Predicate] | Not[Predicate] | True
Comparison = { path: Path, op: {=,≠,<,≤,>,≥,in,contains}, value: Criterion | Path }
```

`True` is mandatory: it is what makes `join` express Cartesian product (§3.3).

`value` admits a **Path** as well as a literal, so two fields of the same record
can be compared (`grade > passingGrade`). Restricting it to literals would make
every field-to-field comparison inexpressible.

The same grammar is evaluated in two places — pushed down to Mongo by `find`,
and in memory by `select`. **These must be tested for equivalence.** Two
implementations of one grammar will otherwise drift, and the drift will be
silent.

Because the grammar is closed and compiles structurally to a Mongo filter
document, push-down carries no operator-injection surface.

### 3.5 Shape: pipelines, not one tree

Collection operations chain linearly; only scalar arithmetic is genuinely
tree-shaped. So:

- a **pipeline** is a list of stages, each consuming the previous stage's output
- **scalar expressions** are small trees inside a stage

A flat list is far easier for a model to emit correctly than a deep nested union
type, and it produces vastly better errors: *"stage 3 expected Collection, got
Scalar"* is actionable in a way that a tree path is not.

### 3.6 One call, many pipelines

`compute` takes a **list of named pipelines**, each able to reference another's
result by name. Execution order is **derived by topological sort over the
declared references, not taken from the caller's ordering** — a model that lists
them in the wrong order should still succeed, since the dependencies are already
stated explicitly. A reference cycle is an expression defect.

This is the fix for composition cost. If one call yields one fact, an N-step
derivation costs N turns, each carrying rejection risk — which is precisely the
wandering behaviour that motivated this redesign. Under this design a multi-step
derivation is one turn.

**Failure is per-pipeline, never all-or-nothing.** If pipeline 3 of 5 fails,
1, 2, 4 and 5 still return as facts and the loop repairs one stage. Discarding
successful work because a sibling failed is how a repair loop burns its budget.

### 3.7 Certainty

Certainty travels with the **record's origin**, not with a field-name map. A
field-name-keyed map cannot represent a `union` of two collections where the
same field name carries different provenance on each side.

| operation | rule |
|---|---|
| collection ops (`select`, `project`, `join`, `union`, `difference`, `sort`, `limit`, `distinct`, `unnest`) | **preserve** per-record provenance; a joined record carries both origins |
| scalar-producing ops (`aggregate`, `arith`, `compare`) | **collapse** to the weakest basis among the values actually consumed |

Collapsing at collection level would degrade every field to the weakest source
the moment a record touched a wiki-derived one, and provenance would never
recover.

**Basis ordering, weakest last:**
`official_record` > `wiki_derived` > `llm_interpretation` > `predicted_pattern` > `simulated`

`simulated` being weakest is what makes hypotheticals work without a primitive:
inject a hypothesised record, and the weakest-input rule taints everything
derived from it automatically.

### 3.8 Sugar

Redundant operators are permitted **only** as declared sugar with a canonical
expansion to the basis — one evaluator implementation, no second code path.

- `intersection(A,B)` → `difference(A, difference(A,B))`
- `argmax(C, path)` → `limit(sort(C, path, desc), 1)`

This is the discipline that stops the operator list drifting back into fifteen
overlapping special cases. **A shortcut that cannot be expanded to the basis is
not sugar — it is new capability, and it means the basis was incomplete.** That
is a design bug to fix at the basis, never to paper over with another operator.

---

## 4. Cross-cutting rules

### 4.1 Completeness of collections

A collection is not merely a value; it carries whether it is **all** of what was
asked for. `count` over a truncated page returns a confidently wrong number, and
per-fact certainty cannot express that — the facts are individually perfect.

Every Collection carries `complete: bool` and `total: int`.

`find` establishes these at admission: a source-side count settles `total`, and
`complete` is true only when the returned records account for all of it. A
collection whose completeness cannot be established is `complete: false` — never
optimistically true, since the failure mode of guessing wrong is a confidently
wrong count rather than a visible error.

| operation | on incomplete input |
|---|---|
| `select`, `project`, `sort`, `distinct`, `unnest` | result is incomplete (monotone) |
| `join`, `union` | result is incomplete if either side is |
| `aggregate` | **fail closed** |
| `difference(A, B)` — **A** incomplete | result is incomplete |
| `difference(A, B)` — **B** incomplete | **fail closed** |

The `difference` asymmetry matters and is easy to get wrong. An incomplete
subtrahend does not produce a partial answer, it produces a **wrong** one: every
record missing from `B` is wrongly *retained* in the output. "Which requirements
remain" silently gains courses the student has already passed.

### 4.2 Null keys fail closed

A null or unresolvable value in a **key** position — join key, difference key,
group key — is an error, never a silently skipped record. Silently dropping
unresolvable records makes a set difference quietly wrong while every remaining
fact still reports full confidence.

### 4.3 Determinism

Two runs of the same pipeline over the same data must return the same answer.

- `limit` after a non-total `sort` must tiebreak on a stable key, or report the
  tie rather than picking arbitrarily.
- `find` with a `limit` and no explicit sort must apply a stable default
  ordering. Otherwise the *page itself* varies between runs, which is the same
  bug one level up from `argmax`.

### 4.4 Errors are for repair

An error's job is to let the next attempt succeed. Two categories, and they must
be distinguishable **in the type**, not by string matching:

- **expression defect** — the pipeline is wrong and an edit can fix it. The error
  names what was expected, what was found, and what is available to switch to.
- **data defect** — the facts lack what any correct pipeline would need. No edit
  can fix it, and a repair loop that retries burns its budget re-deriving a
  pipeline that was already right.

Because operators are typed (§3.3), the generic checker produces both from the
signature table plus observed types. This is a table lookup, not a hand-written
branch per operator — which is what keeps the basis extensible without the
validation surface growing with it.

---

## 5. Implementation plan

Each phase has a gate that must pass before the next begins.

| # | phase | gate |
|---|---|---|
| 1 | Types, envelope, certainty ordering, completeness flags | property tests: basis ordering is a total order; completeness propagates per §4.1 table |
| 2 | Predicate grammar + both evaluators (Mongo push-down, in-memory) | **equivalence test**: same predicate, same result, both backends, over generated data |
| 3 | Operator table, generic type checker, error taxonomy | **static closure test** (§5.1); every operator has a repair hint derived from its signature |
| 4 | Pipeline runner, multi-pipeline call, per-pipeline failure | a 5-stage derivation runs in one call; a mid-pipeline failure returns siblings intact |
| 5 | `find` (push-down + completeness reporting) | truncated fetch reports `complete=false`; `aggregate` over it fails closed |
| 6 | `search_corpus`, `interpret` (typed output feeding the algebra) | an interpreted `Quantity` is directly consumable by `arith` with no coercion |
| 7 | `traverse`, `forecast`, `optimize` | each returns typed facts the algebra can consume |
| 8 | `propose` | proposal only; no path writes without confirmation |
| 9 | Loop adaptation | out of scope for this document; named so it is not forgotten |

### 5.1 The completeness gate is static and free

Soundness is a property of the operator table, not of a model's behaviour. Two
distinct assertions, and passing only the first proves very little:

1. **Type closure** — every operator's output type appears as a legal input type
   of some operator, and every declared sugar expands to the basis.
2. **Relational completeness** — each of Codd's six (selection, projection,
   product, union, difference, rename) is exhibited as a concrete expression in
   this basis, plus generalized projection via `extend`.

Type closure alone is necessary but weak: a basis can be perfectly closed and
still unable to express a join. Both are unit tests over the table. **No LLM
spend is required to know whether the basis is sound.** Behavioural evaluation measures whether the model can
*drive* the algebra, which is a separate question and must not be conflated with
whether the algebra is complete.

### 5.2 Validation cases

Used to check the finished design expresses known-real things — **after** the
basis is fixed, never as input shaping it:

| case | expression | exercises |
|---|---|---|
| credit-weighted GPA | `extend(points = grade × credits)` then `arith(÷, aggregate(sum, points), aggregate(sum, credits))` | **generalized projection** — the case that exposed the missing `extend` |
| requirements remaining | `difference(required, completed)` | §4.1 subtrahend rule |
| most-offered course | `argmax` sugar | expansion + tie determinism |
| load by semester | `group(by=semester, agg={credits: (sum, credits)})` | grouping |
| courses sharing a prerequisite | self-`join` | rename/qualification (§3.3) |
| "if I fail X" | `difference` + hypothesis taint | §3.7 without a counterfactual primitive |

If any case is inexpressible, the **basis** is wrong. The fix is at the basis —
not a new operator for that case.

---

## 6. Open items

- ~~**Optimize's contract.**~~ **Settled (2026-07-19).** The vocabulary is
  items / slots / constraints / objective, with `Precedence`, `Capacity` and
  `Eligibility` as the constraint kinds and `Eligibility` reusing the ordinary
  predicate grammar. Nothing in it is academic — courses and semesters are items
  and slots — which is what stops it collapsing back into
  `generate_semester_plan(student, track)`.
- ~~**`propose`'s replay ledger is not durable.**~~ **Closed (2026-07-19).**
  `ConfirmationLedger` is now injected, with `MongoLedger` making the token the
  `_id` so spending is a single atomic insert — no read-then-write window for a
  double-submit to slip through. `execute` spends **before** applying: the other
  order leaves a window where the write has landed but the confirmation still
  looks unused, and a crash there permits replaying a real effect. This order
  costs a re-confirmation instead, which is the failure worth having.
- ~~**Cross-pipeline `arith`/`compare` is stubbed.**~~ **Closed (2026-07-19).**
  Scalar results are now published alongside collections, so one call can run
  two aggregates and compare them. `arith` refuses a literal operand (a number
  typed into an arithmetic slot is an ungrounded value wearing the shape of a
  result); `compare` admits one, because a threshold genuinely can come from the
  question.
- **Corpus retrieval quality** is out of scope; this document treats
  `search_corpus` as a boundary, not a ranking design.
- **Loop redesign** — turn budgets, tool-call caps, and working-set rendering
  were tuned against a different tool distribution and will need re-derivation
  once `compute` is the workhorse.
- **Tool-call observability.** Eval logs record turns, calls, and wall clock,
  but not which tools were selected. The tool layer cannot be evaluated without
  it, and it should land alongside phase 4.
