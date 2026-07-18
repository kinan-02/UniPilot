# Temporal pattern contract

Defines the output shape and classification rules for
`extract_temporal_pattern(fact_type, entity)`
([`AGENT_VISION.md` §5](AGENT_VISION.md), primitive 5; §2.3's future-offering
prediction need). Like the other Group 2 contract docs, this is a from-
scratch design with no prior art in the codebase — **update this doc
whenever the vocabulary, bucket rules, or confidence formula changes.**

## Data availability (verified, not assumed)

`services/data-engineering/data/raw/technion/` has **7 real semester
catalog files**, not one: `courses_2023_201`, `courses_2024_{200,201,202}`,
`courses_2025_{200,201,202}` — 2 Winters (`200`), 3 Springs (`201`), 2
Summers (`202`). Checked real courses against this before designing
anything: course `00440148` is offered in all 7; courses `00440105`/
`00440140` are offered in all 5 Winter+Spring semesters and **zero** of the
2 Summers — a genuine "reliable in some terms, never in others" pattern,
not a hypothetical.

`AcademicGraphEngine` only ever loads **one** semester's catalog at a time
(`course_catalog` is replaced wholesale on each `load_semester_catalog`
call) — mining history across semesters requires independently reading
every raw JSON file via
`app.retrieval.graph_engine.semester_catalog.discover_semester_catalogs`,
not going through the engine's own single-semester state.

## `fact_type` vocabulary

Runtime-validated `str`, not `Literal` (same extensibility rationale as
every other primitive's vocabulary field). Only one implemented today:

- `course_offering` — `entity` is a course code. Mines every discoverable
  raw semester JSON file for whether that course code appears in it.

Any other `fact_type` fails closed (`unknown_fact_type`) rather than
guessing at a generalization no concrete need has justified yet.

## Per-term-type classification — 3 buckets, no invented percentage threshold

**Confirmed with user.** For each term-type (Winter/Spring/Summer,
`plan_term` 1/2/3 per `semester_catalog.OFFERING_LABELS`), compute
`observed / total` across every discovered semester of that term-type, then
classify from the *exact* ratio — no arbitrary "≥75%" cutoff, since the real
dataset only has 2–3 samples per term-type and a percentage threshold would
be unfalsifiable noise at that sample size:

| Ratio | Bucket |
|---|---|
| `1.0` (offered every time) | `"reliable"` |
| `0.0` (never offered) | `"never"` |
| anything in between | `"irregular"` |

Output is structured per-term-type data (`observed`/`total`/`label` per
term), **never a pre-baked English sentence** — turning this into prose
("usually offered in Winter and Spring...") is Composition's job per
AGENT_VISION §4, not this primitive's.

## `certainty.confidence` — sample-size-based, capped below 1.0

**Confirmed with user**, explicitly acknowledged as an invented heuristic
with no ground truth to validate against (no prior art, no way to check
against real advisor judgment):

```
confidence = min(0.95, 0.5 + 0.1 × totalSemestersInHistory)
```

Never reaches `1.0` — `certainty.basis` is always `"predicted_pattern"`
(the one `CertaintyBasis` value reserved for exactly this: a prediction, not
an observed fact), and a prediction should never claim full certainty
regardless of how much history backs it.

## Output shape (`ToolOutputEnvelope.data`)

```json
{
  "factType": "course_offering",
  "entity": "00440105",
  "termPatterns": {
    "1": {"label": "reliable", "observed": 2, "total": 2},
    "2": {"label": "reliable", "observed": 3, "total": 3},
    "3": {"label": "never", "observed": 0, "total": 2}
  },
  "termLabels": {"1": "reliable", "2": "reliable", "3": "never"},
  "semestersOffered": 5,
  "totalSemestersInHistory": 7
}
```

`termLabels` is a **scalar projection** of `termPatterns` (term → its `label`), added so a consumer
can surface `termLabels.<term>` directly instead of drilling into the term object. Both composites
that embed this output (`get_course_profile`, `check_eligibility`) inherit it, giving the offering
answer one consistent scalar grain regardless of which tool produced it.

`semestersOffered` is a second **scalar projection** — the sum of `observed` across every term-type,
i.e. the number of distinct semesters the course actually appeared in (always ≤ `totalSemestersInHistory`;
`5` here = `2 + 3 + 0`). Same grain principle as `termLabels`: it answers "in how many semesters has X
been offered?" as a single directly-surfaceable/comparable leaf, rather than a sum a consumer must
re-derive over the term objects. This is the grain the `map` primitive
([`AGENT_ARCHITECTURE_V2.md` §19](AGENT_ARCHITECTURE_V2.md)) reads when fanning this tool over many
course codes to find, in-code and grounded, which was offered most — instead of a per-course child loop.

An entity that never appears in any discovered semester file still returns
`ok=True` (all buckets `"never"`, `observed=0` everywhere) — mining a
history is this primitive's whole job; whether the entity is a *real* course
is `get_entity`'s concern, not this one's. Zero discoverable semester files
at all (raw data not configured, or genuinely no history) is the one real
failure case (`insufficient_history`) — no pattern can be mined from zero
data points.

## Fail-closed error vocabulary

- `fact_type_required` / `unknown_fact_type: <type>`
- `entity_required`
- `academic_raw_data_not_configured` / `academic_raw_data_unavailable: <exc>`
- `insufficient_history` — zero semester catalogs discovered

## Status

- `extract_temporal_pattern` (`services/ai/app/agent_core/tools/primitives/extract_temporal_pattern.py`) — implements `fact_type="course_offering"`.
