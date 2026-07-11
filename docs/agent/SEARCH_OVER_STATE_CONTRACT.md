# search_over_state contract

Defines `constraints`, `objective`, and the output shape for
`search_over_state(state, constraints, objective)`
([`AGENT_VISION.md` §5](AGENT_VISION.md), primitive 8; §3.3's "one engine for
plan generation, what-if simulation, and requirement-substitute search").
Like the other Group 2/3 contract docs, this is a from-scratch design with
no prior art — **update this doc whenever the constraint/objective
vocabulary or the search algorithm changes.**

## Design principle: generic engine, typed/extensible vocabulary — not one hardcoded scenario

**Confirmed with user** after an initial draft wrongly baked one scenario
(track-completion planning) directly into the tool's fixed fields
(`trackSlug`, `maxCreditsPerSemester` as named parameters) — exactly the
enumeration mistake AGENT_VISION §5 warns against. Corrected: `constraints`
is a `list[dict]`, each entry independently typed via its own `type`
discriminator (same pattern as `mutate_state.change["type"]` and
`apply_deterministic_rule.rule["type"]`) — a new constraint type is an
additive change, never a signature change. `objective` stays a plain `str`
discriminator (matching AGENT_VISION's own literal signature) rather than a
dict, since v1's only objective needs no extra parameters; a future
objective that needs its own parameters (e.g. `find_substitute` needing
"exclude this course") should take them via a new constraint type, not by
turning `objective` into something richer — keeps exactly one place
(`constraints`) where parameters live.

**Confirmed with user**: this tool is fully standalone, callable by the
agent at any time, with zero code dependency on `interpret_text` (Group 4)
or any other not-yet-built primitive. It composes only primitives that
already exist and are already tested (`get_entity`, `traverse_relationship`,
`extract_temporal_pattern`) plus one engine method with no primitive wrapper
yet (`AcademicGraphEngine.evaluate_eligibility` — see below). Anything it
can't derive itself (credit minimums, elective-bucket rules — currently only
wiki prose, no structured source) comes in as an explicit constraint value
from the caller; it never blocks on a future primitive to exist.

## `constraints` — `list[dict]`, each with its own `type`

| `type` | Fields | Effect |
|---|---|---|
| `courses_required` | `courses: [courseNumber, ...]` | Adds these course codes to the required set |
| `courses_required_by_track` | `trackSlug` | Resolves required courses via `traverse_relationship(trackSlug, "contains", "forward")` — real graph edges, not caller-guessed |
| `max_credits_per_semester` | `value: number` | Caps total credits scheduled per semester (existing `plannedSemesters` credits count toward the cap too) |
| `max_semesters` | `value: int` | Bounds how many future semesters the search considers (default `8` if not given — a search must be bounded; documented default, not silently unbounded) |
| `substitute_for` | `courseId, trackSlug` | Only valid with `objective="find_substitute"` — see that section below. Exactly one per call. |

Multiple `courses_required`/`courses_required_by_track` entries union
together. Multiple `max_credits_per_semester`/`max_semesters` entries use
the **minimum** (most restrictive) value — a deterministic, documented
tie-break, not "last one wins."

Prerequisite-respecting and offering-availability-respecting are **not**
constraint types — they're physical realities the search always enforces,
never optional.

## `objective` — `str`

- `"minimize_semesters"` — schedule every required-but-not-yet-satisfied
  course across the fewest future semesters possible, respecting all
  constraints.
- `"find_substitute"` — reuses the exact same forward-scheduling walk, but
  with the "required" set replaced by a **substitute candidate pool**
  instead of a caller-specified requirement list: every other course in the
  `substitute_for` constraint's `trackSlug`'s `contains` list (excluding
  `courseId` itself). Requires exactly one `substitute_for` constraint
  (`{"type": "substitute_for", "courseId": ..., "trackSlug": ...}`); other
  constraint types (`max_credits_per_semester`, `max_semesters`) still apply
  as bounds, but `courses_required`/`courses_required_by_track` are ignored
  for this objective (there is no separate "required" set — the candidate
  pool *is* the search target). A `substitute_for` constraint given with any
  other objective fails closed
  (`substitute_for_constraint_requires_find_substitute_objective`) rather
  than being silently ignored.

  **Known limitation, by design, not an oversight**: the graph has no
  explicit elective-bucket or substitutability structure — `contains` is a
  track's *entire* flat required-course list, required and elective mixed
  together with no sub-grouping. So a `find_substitute` candidate is
  "structurally plausible" (same track, not yet completed/planned, actually
  schedulable) — **not** a semantic claim that it fulfills the exact same
  requirement line `courseId` was filling. `find_requirement_substitutes`
  (the higher-level composite built on this objective,
  `docs/agent/HIGHER_LEVEL_TOOLS.md`) surfaces this caveat directly in its
  own output rather than hiding it.

Any other value fails closed (`unknown_objective`) — the vocabulary is open
for future objectives (e.g. `check_feasibility`) without changing the
tool's shape.

## Algorithm (v1 — greedy/topological, not a general CSP solver)

1. Resolve the required-course set: union of every `courses_required` list
   and every `courses_required_by_track`-resolved list.
2. `satisfied` = course numbers in `state.completedCourses` with
   `status == "completed"` (a `"failed"` entry does **not** satisfy the
   requirement — matches `mutate_state.fail_course`'s semantics and the
   fail-course-X worked example's whole premise).
3. `already_scheduled` = every course number already present in
   `state.plannedSemesters` (any semester) — treated as fixed, not
   rescheduled, but its credits still count toward that semester's cap.
4. `remaining = required - satisfied - already_scheduled`. Empty
   `remaining` is immediate success (0 additional semesters needed).
5. Walk forward semester-by-semester from the semester **after**
   `state.currentSemesterCode` (reusing `mutate_state`'s own
   `_advance_semester_code` helper — one source of truth for semester-code
   arithmetic, not reimplemented here), up to the resolved `max_semesters`
   cap. Each step, in deterministic course-code-sorted order (a documented
   greedy tie-break, not claimed optimal):
   - **Prerequisite check**: `AcademicGraphEngine.evaluate_eligibility(course, satisfied ∪ scheduled_so_far)` — the engine's own AST-aware (AND/OR) eligibility check, called directly rather than reimplemented. `traverse_relationship`'s `has_prerequisite` edges are deliberately **not** used for this — `build_graph()` flattens an OR-prerequisite AST into one flat edge set per course, which would incorrectly require every alternative rather than just one; `evaluate_eligibility` is the one place that already gets AND/OR right.
   - **Offering check**: `extract_temporal_pattern("course_offering", course)` — skip this semester for this course if the resolved term's bucket is `"never"`. If the primitive itself fails (`insufficient_history` — no data at all), schedule anyway but tag that entry's certainty as low/undetermined rather than blocking the plan on a data gap — a missing prediction is not the same as a negative prediction.
   - **Credit check**: this semester's already-assigned credits (existing `plannedSemesters` + newly scheduled this pass) + this course's credits (`get_entity(entity_type="course", ...)`) must not exceed the resolved `max_credits_per_semester`, if any was given.
   - If all three pass, schedule the course in this semester and remove it from `remaining`.
6. Stop when `remaining` is empty or `max_semesters` is exhausted. An
   exhausted search with courses still in `remaining` is **not** a failure
   (`ok=True`) — a partial plan plus an explicit `unscheduledCourses` list
   and a warning is still useful output; deciding what to do about it is
   the caller's job (Composition/the user), not this primitive's to hide or
   force a hard failure over.

## Output shape (`ToolOutputEnvelope.data`)

```json
{
  "objective": "minimize_semesters",
  "requiredCourses": ["00440105", "00440140", "00440148"],
  "satisfiedCourses": ["00440105"],
  "alreadyPlannedCourses": ["00440140"],
  "plan": {
    "2025-3": [{"courseNumber": "00440148", "credits": 3.5, "offeringCertainty": {"basis": "predicted_pattern", "confidence": 0.83}}]
  },
  "semestersUsed": 1,
  "unscheduledCourses": []
}
```

Every required course accounts for exactly one of `satisfiedCourses`
(already `completed`), `alreadyPlannedCourses` (already in
`plannedSemesters`, fixed, not rescheduled), scheduled somewhere in `plan`,
or `unscheduledCourses` — no required course silently disappears from the
output.

`ToolOutputEnvelope.certainty` is the **minimum-confidence** entry across
every scheduled course's `offeringCertainty` (a conservative aggregate —
one weak link determines how much to trust the whole plan), with
`basis="predicted_pattern"` if any entry relied on a future-semester
prediction, `"official_record"` only for the trivial all-already-satisfied
case (step 4, nothing left to predict).

## Fail-closed error vocabulary

- `objective_required` / `unknown_objective: <value>`
- `constraint_type_required` / `unknown_constraint_type: <type>` (per entry — the list/dict shape itself is already guaranteed by `SearchOverStateInput`'s own Pydantic schema, `list[dict[str, Any]]`, so only each entry's `type` value needs runtime validation)
- `<type>_requires_positive_numeric_value` — `max_credits_per_semester`/`max_semesters` given a non-numeric or non-positive `value` (fails closed rather than silently falling back to the default, which could produce a confusingly unbounded search when the caller thought they'd capped it)
- `courses_required_by_track_requires_trackSlug`
- `courses_required_by_track_failed: <slug>: <underlying traverse_relationship error>` — propagates the real reason (not found, graph unavailable, etc.) rather than collapsing every failure into one generic "not found" label
- `substitute_for_requires_courseId_and_trackSlug`
- `substitute_for_constraint_required` — `objective="find_substitute"` given with no `substitute_for` constraint
- `substitute_for_constraint_requires_find_substitute_objective` — a `substitute_for` constraint given with any other objective
- `substitute_for_constraint_must_be_singular` — more than one `substitute_for` constraint in one call
- `substitute_pool_unavailable: <trackSlug>: <underlying traverse_relationship error>` — `find_substitute`'s equivalent of `courses_required_by_track_failed`
- `academic_graph_not_configured` / `academic_graph_unavailable: <exc>`

## Status

- `search_over_state` (`services/ai/app/agent_core/tools/primitives/search_over_state.py`) — implements `objective="minimize_semesters"` and `objective="find_substitute"`. `check_feasibility` remains a possible future objective, not yet needed by anything built so far.
