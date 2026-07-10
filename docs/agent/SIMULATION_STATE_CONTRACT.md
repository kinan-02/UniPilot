# Simulation state contract

Defines `base_state` — the plain-dict shape `mutate_state` transforms and
`search_over_state` (Group 3, not yet implemented) will search over. Per
[`AGENT_VISION.md` §3.3](AGENT_VISION.md), a what-if simulation and semester-
plan generation are the same engine, parameterized only by whether the
starting state is the student's real current state or a hypothetically-
perturbed one — this contract is that starting state's shape.

**Nothing else in the codebase defines this shape.** `get_entity` returns raw
records (a Mongo document, a `{completedCourses: [...]}` wrapper, etc.) —
assembling those into one `base_state` object is the caller's job (a future
Simulation/Planning specialist subagent), not `mutate_state`'s. This doc is
the single source of truth for the shape; **update it whenever a primitive
adds, renames, or relies on a new `base_state` key or `change_type`.**

## `base_state` shape

```json
{
  "completedCourses": [
    {"courseNumber": "00440105", "semester": "2024-1", "status": "completed"}
  ],
  "plannedSemesters": {
    "2025-2": ["00440148"]
  },
  "currentSemesterCode": "2025-2",
  "trackSlug": "track-biomedical-engineering"
}
```

- All four top-level keys are optional — a caller may pass a partial state;
  every primitive that reads `base_state` treats a missing key as empty
  (`[]`/`{}`/`None`) rather than raising.
- `completedCourses[].status` is one of `"completed"` or `"failed"` (no
  other value is written by `mutate_state` today — a caller-supplied state
  may carry other values, which primitives must pass through unchanged
  rather than reject).
- `plannedSemesters` maps a semester code to a list of course numbers
  planned for that semester (not yet completed).
- `currentSemesterCode` and semester codes anywhere else in this shape use
  the existing `"YYYY-N"` format (`N` ∈ {1, 2, 3} for Winter/Spring/Summer)
  already produced by `app.retrieval.graph_engine.semester_catalog` — not a
  new format invented for this contract.
- `trackSlug` is a wiki slug in the `track-*` namespace (see `get_entity`'s
  `track` entity type).

## `change_type` vocabulary (for `mutate_state`)

`mutate_state(base_state, change)`'s `change` argument is one dict carrying
its own discriminator: `change["type"]` (a runtime-validated `str`, not a
Pydantic `Literal` — same extensibility rationale as
`get_entity.entity_type`/`traverse_relationship.relation`: a new change type
is meant to be an additive change, not a schema/tool-surface change) plus
whatever payload fields that type needs, e.g.
`{"type": "fail_course", "courseNumber": "00440105", "semester": "2025-2"}`.

| `change["type"]` | Remaining `change` fields | Effect |
|---|---|---|
| `fail_course` | `courseNumber, semester` | Adds or updates a `completedCourses` entry for that course/semester with `status="failed"` |
| `drop_course` | `courseNumber, semester` | Removes that course number from `plannedSemesters[semester]` |
| `retake_course` | `courseNumber, targetSemester` | Adds that course number to `plannedSemesters[targetSemester]` (deduplicated) |
| `delay_semester` | `count` | Advances `currentSemesterCode` forward by `count` semester slots (`"YYYY-N"`, `N` wraps at 3, year increments on wrap) |
| `change_track` | `trackSlug` | Replaces `trackSlug` |

Every transform returns a **new** state dict (`base_state` is never mutated
in place, per this codebase's immutability rule) and fails closed
(`ok=False`) on an unknown `change_type` or a payload missing a required
field — never a best-guess default.

## Status

- `mutate_state` (`services/ai/app/agent_core/tools/primitives/mutate_state.py`) — implements all 5 change types above.
- `search_over_state` — not yet implemented (Group 3). Will consume `base_state` as its `state` input; update this doc with any additional keys it needs once designed.
