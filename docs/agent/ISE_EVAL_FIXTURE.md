# ISE Correctness-Eval Fixture — verified ground truth

Working brief for turning the live eval from a **liveness check** into a
**correctness gate**. Every fact below was verified against the dev Mongo
catalog on 2026-07-15; nothing here is invented.

## Why this exists

The current live eval asserts only `in_scope` + `final_entry is not None` +
`"answer_text" in data`. That passes if the agent emits *any* string. Evidence
it is not measuring correctness: in the 2026-07-15 sweep, the two synthesis
attempts of `course_disruption_simulation` returned **contradictory** answers
(one said the student must retake 00440105, the other that they had already
passed it — the records say they passed it). Both contained `answer_text`; both
would have passed.

## The EE fixture is broken — and it probably faked an "agent bug"

`services/api`'s `student_user_context_service` resolves a transcript **only**
via `courseId` -> `courses._id`:

```
course_ids        = list(effective_completions.keys())
catalog_courses   = await find_courses_by_ids(database, course_ids)
completed_numbers = [number_by_id[cid] for cid in course_ids if cid in number_by_id]
unresolved_course_count = sum(1 for cid in set(course_ids) if cid not in number_by_id)
```

`metadata.courseNumber` is **never** read. An unresolvable `courseId` is dropped
silently and only bumps a data-quality warning.

**`test_full_agent_live_eval.py`'s EE fixture seeds `courseId=ObjectId()`** — a
random id matching nothing. That student's transcript therefore resolves to
**zero** completed courses.

=> Live-eval failures previously blamed on the orchestrator are likely fixture
artifacts, specifically:
- `calculation_validation_failed: ... ref 'completed_courses' not found in facts
  (available: [])` — the facts were empty because the transcript never resolved,
  **not** because the planner mis-wired `context_requirements`.
- `graduation_progress_audit` returning partial with unmet criteria.

**Treat the "planner does not wire calc-validation dependencies" diagnosis as
UNCONFIRMED** until re-measured against a fixture whose transcript resolves.
(The `strict=False` JSON fix and the fact-envelope unwrap are unaffected — both
were proven from captured raw payloads, not from this student.)

The ISE fixture resolves every `courseId` at seed time and **raises** on a miss;
`test_ise_student_fixture.py` asserts all 17 resolve (4/4 green).

## What the gate caught on its first live run (2026-07-15)

3 passed / 3 failed. Two of the failures were MY errors (phantom PE credit;
an assertion that guessed at RU behaviour) -- both fixed. The rest are real:

### FIXED -- composition discarded a CORRECT answer (`json_parse_failed`)

The model answered in **prose**, not JSON, twice:
`"Here is a list of your completed courses... includes 17 courses...
00940564: Grade 90..."` -- fully correct, our exact seeded values. No `{` at
all, so the `strict=False` control-character fix cannot help. The block failed;
the student got an EMPTY string. Structured output is **off** by default
(`agent_reasoning_structured_output_enabled: bool = False`), so nothing forces
JSON and a retry only re-rolls the dice.

**Fix:** `_invoke_llm(salvage_text_field=...)` (opt-in) rebuilds the payload from
prose when the schema is a single free-text field; composition opts in with
`answer_text` and warns `composition_salvaged_prose_answer`. Blank text is never
salvaged.

### FIXED -- `calculation_validation` failed on a repairable mistake

`of_not_a_list: ref:creditBreakdown` -- the model aggregated over the credit-
buckets DICT instead of the `completedCourses` list in the same facts.
`validate_expression_tree` only checked that `of` EXISTS, so this slipped through
validation and blew up at EVALUATION time inside the tool -- where the block
never retries a validated tree, so the step just died.

**Fix:** validation now rejects an aggregate whose `of` ref is not a list, and
names the list-valued facts so the bounded repair loop has somewhere to go.

### FIXED -- our schema contradicted our model, silently downgrading GOOD routes

**This was the worst bug of the session, and it was OURS, not the model's.**

An earlier revision of this doc blamed the planner/router and called it
unverifiable LLM behaviour. **Wrong -- retracted.** Reading the actual router
call showed it did its job perfectly:

```json
{"pipeline": [{
   "sub_step_id": "1e-0",
   "specialist": "calculation_validation",   <-- CORRECT
   "objective": "Sum all creditsEarned values from the completedCourses list fetched in step 1b.",
   "context_requirements": null              <-- schema says this is VALID
}]}
```

The contradiction, both in `specialist_router.py`:

```python
# _SUB_STEP_SCHEMA (what the MODEL is told to satisfy)
"context_requirements": {"type": ["array", "null"], ...}   # null ALLOWED
"specific_instructions": {"type": ["array", "null"], ...}  # null ALLOWED

# RoutedSubStep (what VALIDATES the response)
context_requirements: list[str] = Field(default_factory=list)   # null REJECTED
specific_instructions: list[str] = Field(default_factory=list)  # null REJECTED
```

The full chain:

```
router: specialist=calculation_validation, context_requirements=null   (schema-valid!)
  -> RoutedSubStep.model_validate() raises
  -> sub-step dropped  ("specialist_router_dropped_invalid_substep")
  -> pipeline empty -> _fallback_output -> _fail_closed_pipeline
  -> specialist = "retrieval", objective = "Calculate the total credits..."
  -> retrieval (no calculator, contractually barred from computing) does
     17-number mental math -> 63.0   (truth: 62.5)
  -> stamped certainty_basis="official_record", confidence=1.0
```

So a **correct** route to the deterministic calculator was thrown away because
the model obeyed our own schema, and the step silently degraded into LLM mental
arithmetic wearing an "official record" badge. Downstream nothing can tell that
apart from a real registrar fact.

**Fix:** a `mode="before"` field-validator on `RoutedSubStep` coerces `None ->
[]` for all four list fields, so the model accepts exactly what the schema
advertises.

**Scope -- this is not one case.** `specialist_router_dropped_invalid_substep`
fires throughout the live logs (3x in credits_remaining, 3x in
course_disruption_simulation, more in multi_prereq / track_gap). It was
dismissed as benign noise all session. Every occurrence is a correct specialist
route being discarded and downgraded to a blind retrieval fetch -- a plausible
cause of a large share of "the agent is dumb" behaviour, including
calculation_validation steps that never ran.

## Sources of truth (and their precedence)

1. **Wiki track page** — `services/data-engineering/data/catalog_valut/catalog_valut/wiki/entities/tracks/track-information-systems-engineering.md`
   Supplies the *Required Courses by Semester* breakdown. Cross-validates with
   Mongo `degree_programs`: programCode `009118-1-000`, 155 total credits,
   buckets 107.5 / 35.5 / 6.0 / 4.0 / 2.0 (matches all 5 `degree_requirements`).
2. **Mongo `courses`** — authoritative for code, credits, and name.

**Precedence rules learned the hard way:**
- Wiki **code + Hebrew title are authoritative**; its **wikilink filenames are
  NOT** (they are stale: `0940564` links to `senior-seminar` but is really
  "מבוא לניהול פיננסי"; `0970800` links to `final-project-iem-ise` but is really
  "עקרונות השיווק" — Mongo confirms the titles).
- Wiki **7-digit** codes map to Mongo **8-digit zero-padded** (`0940345` -> `00940345`).
- Where the wiki hedges, **Mongo wins** (`0940312`: wiki "3.5-4.0 uncertain" -> Mongo **4.0**).

## The student

A 2nd-year Information Systems Engineering student, currently in **semester 4**
(spring). Completed = semesters 1-3.

| Field | Value |
| --- | --- |
| `programSlug` | `track-information-systems-engineering` (one of only 7 real slugs in `student_profiles`) |
| `programType` | `undergraduate` |
| `catalogYear` | `2025` |
| `institutionId` | `technion` |
| `currentSemesterCode` | **OPEN** — format is `YYYY-N`; real profiles show `2026-1`. Pin this before writing assertions. |

Confusable sibling to keep in mind: `track-data-information-engineering` (DNE).

## Completed courses — semesters 1-3 (all 17 verified in Mongo)

| Sem | Code (Mongo) | Name | Credits |
| --- | --- | --- | --- |
| 1 | `00940345` | מתמטיקה דיסקרטית ת' | 4.0 |
| 1 | `00940704` | סדנת תכנות בשפת סי | 1.5 |
| 1 | `01040065` | אלגברה 1מ2 | 5.0 |
| 1 | `01040042` | חשבון דיפרנציאלי ואינטגרלי 1מ2 | 5.0 |
| 1 | `02340221` | מבוא למדעי המחשב נ' | 4.0 |
| 1 | — | Physical Education | 1.0 |
| 2 | `00940210` | ארגון המחשב ומערכות הפעלה | 3.5 |
| 2 | `00940219` | הנדסת תוכנה | 3.5 |
| 2 | `00940411` | הסתברות ת' | 4.0 |
| 2 | `00940202` | מבוא לניתוח נתונים | 3.5 |
| 2 | `01040044` | חשבון דיפרנציאלי ואינטגרלי 2מ2 | 5.0 |
| 2 | `03240033` | אנגלית טכנית-מתקדמים ב' | 3.0 |
| 3 | `00940224` | מבני נתונים ואלגוריתמים | 4.0 |
| 3 | `00940241` | ניהול מסדי נתונים | 3.0 |
| 3 | `00940312` | מודלים דטרמיניסטים בחקר ביצועים | 4.0 |
| 3 | `00940424` | סטטיסטיקה 1 | 3.5 |
| 3 | `00940564` | מבוא לניהול פיננסי | 2.5 |
| 3 | `00960570` | תורת המשחקים והתנהגות כלכלית | 3.5 |

**Credit reconciliation (independently matches the wiki's own semester totals):**

| Semester | Computed | Wiki |
| --- | --- | --- |
| 1 | 19.5 + 1.0 PE = **20.5** | 20.5 |
| 2 | **22.5** | 22.5 |
| 3 | **20.5** | ~20.5 |
| **Earned** | **63.5** | |

=> **Credits remaining = 155 - 63.5 = 91.5.** A hard, checkable assertion.

## Semester 4 — the current plan (has a real data gap)

| Code | Name | Credits | Status |
| --- | --- | --- | --- |
| `00940314` | מודלים סטוכסטיים בחקר בצועים | 3.5 | verified |
| `00950605` | מבוא לפסיכולוגיה | 2.5 | verified |
| `00960411` | למידה חישובית 1 | 3.5 | verified |
| `00970800` | עקרונות השיווק | 3.5 | verified |
| `01140051` | פיסיקה 1 | 2.5 | verified |
| `00960211` | מודלים למסחר אלקטרוני | 3.5 | verified — use THIS, not the stale `0960221` |

All six verified **offered in `2025-2`**. Credits: **19.0 + 1.0 PE = 20.0**,
matching the wiki's stated ~20.0.

Prereqs vs the completed set: `00950605` ✓, `00960211` ✓ (via `00940224`),
`00960411` ✓. **Unmet — same plan-vs-registrar pattern as sems 2/3:**
`00940314` (needs `01040019`/`01040016`, the `1מ2` issue again), `00970800`
(needs `00940594` — a **semester-5** course), `01140051` (needs `01130013`,
absent from the whole plan). These are current-plan items and do not touch the
completed set, but extend the scope limit: **do not assert prereq-eligibility on
`00940314`, `00970800`, or `01140051` either.**

**RESOLVED (2026-07-15): NOT a bug. `courses` is offerings-derived.**

An earlier revision of this doc called this an ingestion bug and told you to
file it. **That was wrong — retracted.** See "Two ingestion lineages" below.

The raw catalog PDF does contain `0960221` / `מודלים למסחר אלקטרוני` (confirmed
by the project owner). But `courses` is **not** built from the catalog PDF — it
is built from Technion's **semester-offerings** feed. And:

- `0960221` has **zero offerings** in `course_offerings` AND
  `staging_course_offerings` => never taught in 2023, 2024, or 2025.
- So an offerings-derived collection **correctly** omits it. The pipeline did
  the right thing.

=> **Do not "fix" this by inserting the course.** That would push data into a
collection its source does not contain, and the next promotion run would wipe it.

### RESOLVED by domain ruling (2026-07-15): use `00960211`

**`0960221` is a STALE CODE in the curated PDF. `00960211` is the same course,
and is what ISE students actually take today.** They are NOT two sibling
courses — the wiki's "0960221 (ISE) vs 0960211 (DNE)" note is wrong.

Verified: `00960211` is DDS faculty, 3.5cr, prereq `00940224 או 00940226` (our
student has `00940224` => **satisfied**), and offered **every spring** including
`2025-2`. Substituting it makes semester 4 total **19.0 + 1.0 PE = 20.0** —
exactly the wiki's stated ~20.0, an independent confirmation.

=> **Seed `00960211` in the semester-4 plan.** `0960221` appears nowhere in the
system and should not be used.

**RETRACTED — the "near-miss substitution" adversarial eval case.** An earlier
revision proposed asserting that the agent must NOT substitute `00960211` for
`0960221`. That test is invalid: they are the **same course**, so substituting
is correct, not a hallucination. Do not write that assertion.

## What the eval may and may not assert

**Grounded (usable):**
- Prerequisite satisfaction / eligibility (from the seeded completed set)
- Offering patterns (`course_offerings`, 6580 docs)
- Credit arithmetic (155 total; 63.5 earned; 91.5 remaining)
- Presupposition conflicts (highest-value adversarial case — see the disruption bug)
- Action-boundary and out-of-scope handling

**NOT grounded (do not assert):**
- "Am I on track with my track's required courses?" as a *catalog* question —
  Mongo `degree_requirements` has **0 `courseReferences`** for every ISE bucket,
  and `courses.tracks` is empty across all 2613 courses. The course->track
  mapping exists **only in the wiki page**, not in the structured catalog. This
  likely explains why `graduation_progress_audit` keeps returning partials.

## Design rules for the eval set

- Encode truth as **checkable claims**, not prose ("must identify X as the
  missing prereq"; "must not claim a retake of Y is needed"). Prose-vs-prose
  needs an LLM judge — fuzzy, costly, itself unverified.
- Give every item **provenance** (which record makes it true) so a catalog
  change tells us whether the eval or the agent broke.
- Include adversarial items deliberately: presupposition conflict, out-of-scope,
  action request, and the ISE/DNE track confusion.

## Semester codes — TWO INCOMPATIBLE TAXONOMIES (verified 2026-07-15)

The KB encodes "which semester" two different, non-joinable ways:

| Collection | Field(s) | Real values |
| --- | --- | --- |
| `student_profiles` | `currentSemesterCode` | `2025-1`, `2025-2`, `2025-3`, `2026-1` (`YYYY-N`) |
| `course_offerings` | `academicYear` + `semesterCode` | `200`, `201`, `202` (`semesterName: winter` for `200`) |

So offerings are keyed by **`academicYear` + a 3-digit code** (`200` winter =>
`201` spring, `202` summer), while profiles use **`YYYY-N`**. There is no shared
key: answering "is X offered next semester?" requires translating
`2025-2` -> `academicYear=2025, semesterCode=201`.

This is a real, testable behavior — and a likely cause of the offering-related
partials already seen live (`track_gap_analysis_filtered_by_offering` returned
"The list of course offerings for the next semester code is obtained" as UNMET).

### RESOLVED — the translation rule (verified 2026-07-15)

**Both offering fields are `int`, not string.** Querying them as strings
silently returns 0 matches (cost us a false "no data" scare — do not repeat):

```
academicYear = 2025   (int)
semesterCode = 200    (int)
```

Verified name mapping, and the rule:

| `semesterCode` | `semesterName` | offerings |
| --- | --- | --- |
| `200` | winter | 2482 |
| `201` | spring | 3891 |
| `202` | summer | 207 |

**`YYYY-N` -> `academicYear=YYYY (int)`, `semesterCode=200+(N-1) (int)`**
(`-1` winter, `-2` spring, `-3` summer).

### RESOLVED — `catalogYear` is a catalog EDITION, not an entry year

- `degree_programs`, `courses`, `degree_requirements` all have **exactly one**
  `catalogYear`: **2025**. Only one edition is ingested.
- Real profiles pair `catalogYear: 2025` with *every* semester: `2025-1` (511
  students), `2025-2` (423), `2025-3` (10), `2026-1` (1); one profile has
  `catalogYear: 2023` with `currentSemesterCode: 2025-2`.

=> `catalogYear` varies **independently** of `currentSemesterCode` and implies
nothing about entry. `catalogYear: 2025` is simply forced (only edition with
data). There was no real constraint here.

### RESOLVED — the student's semesters (all offerings verified)

| Semester | Code | Maps to | Offerings in term |
| --- | --- | --- | --- |
| 1 | `2024-1` winter | `academicYear=2024, semesterCode=200` | 1226 |
| 2 | `2024-2` spring | `academicYear=2024, semesterCode=201` | 1287 |
| 3 | `2025-1` winter | `academicYear=2025, semesterCode=200` | 1256 |
| **4 (current)** | **`2025-2` spring** | `academicYear=2025, semesterCode=201` | 1289 |

`currentSemesterCode = 2025-2` — chosen because it is spring, it is what **423
real students** currently have, and it makes the whole history land in terms
that have real offering data.

**Every one of the 17 completed courses was actually offered in the semester it
is assigned to: 5/5 (2024-1), 6/6 (2024-2), 6/6 (2025-1) — zero missing.** The
history is real, not merely plausible.

## Prerequisite chains — the wiki plan does NOT fully satisfy the catalog

Verified 2026-07-15 against `courses.prerequisitesText` (free text, Hebrew
`ו-` = AND, `או` = OR). Checking each course's prereqs against courses completed
in *earlier* semesters:

- **Semester 1** — all five have empty prereqs. Consistent.
- **Semester 2** — `00940210`, `00940219`, `00940202`, `01040044` all satisfied.
  **`00940411` (הסתברות) FAILS**: needs `01040195/01040018/01040017/01040031`;
  the plan gives `01040042`.
- **Semester 3** — `00940224`, `00940241`, `00940424`, `00960570` satisfied.
  **`00940312` FAILS**: needs `01040019` or `01040016` (with `02340221`); the
  plan gives `01040065`.

### RESOLVED by domain ruling (2026-07-15): the PLAN is authoritative

Confirmed by the project owner: **ISE students take `01040042` in semester 1 and
`01040044` in semester 2.** That is the real path. The catalog agrees on that
link (`01040044` accepts `01040042`).

=> The two "failures" below are **catalog data gaps, not student-path problems**.
Seed the plan exactly as the wiki documents it. **Do NOT substitute alternates**
— doing so would invent a student who does not exist in order to satisfy data
that is itself wrong. (An earlier proposal to swap algebra `01040065` ->
`01040016` was retracted for exactly this reason.)

### The two unmet prereqs are FAITHFUL DATA, not bugs (retraction)

An earlier revision called these "catalog data gaps" to file as ingestion bugs.
**Retracted.** Their `prerequisitesText` comes verbatim from Technion's own
course JSON (`sourceName: technion-course-json`) — our ingestion copied the
registrar's data correctly. The registrar's data genuinely omits the `1מ2`
variant.

| Course | `prerequisitesText` accepts | Plan gives | Verdict |
| --- | --- | --- | --- |
| `00940411` (הסתברות, sem 2) | `01040195`, `01040018`, `01040017`, `01040031` | `01040042` (1מ2) | faithful to source |
| `00940312` (מודלים דטרמיניסטים, sem 3) | `01040019`, `01040016` (w/ `02340221`) | `01040065` (1מ2) | faithful to source |

**Never "fix" these by adding `01040042`/`01040065` to the lists.** No source
states that rule; writing it would fabricate a prerequisite — the exact failure
this eval exists to catch — and the next promotion run would revert it anyway.

Note `01040018` — the wiki's stated alternate for `01040042` — has its own
prereq (`01030015`) and **0 offerings in winter 2024-1**, so it was never a real
option regardless.

### Two ingestion lineages (the root of all three false alarms)

| Collection | `sourceName` | `sourceType` | Really means |
| --- | --- | --- | --- |
| `courses`, `course_offerings` | `technion-course-json` | `technion_semester_offerings` | **what was TAUGHT** (2023-2025) |
| `degree_programs` | `technion-<faculty>-catalog` (17 faculties) | `<faculty>_catalog_curated_reviewed` | **the catalog PDFs** (program level only) |

The catalog PDFs *are* ingested — but only to **program** level (credits,
buckets). They are **never** ingested to course level.

=> **`courses` is not the catalog.** Asking "does course X exist?" against
`courses` actually asks **"was X taught in 2023-2025?"**. Every "data bug" in
this doc's earlier revisions came from conflating these two sources.

**Product gap worth a deliberate decision (not a data fix):** a student asking
about a real catalog course that is not currently offered gets "not found"
rather than "exists, not offered". Is ingesting the catalog PDFs to course level
a requirement?

**EVAL SCOPE LIMIT (still stands — but for a different reason):** do not write
assertions requiring the agent to derive `00940411` or `00940312` eligibility
from prereqs. Not because the data is "wrong" (it is faithful), but because the
seeded student's real path **does not satisfy the registrar's stated prereqs**
for those two. An agent reasoning correctly from the data it has would say "not
eligible", while the student demonstrably took them. Ground truth is genuinely
ambiguous there, so assert on other courses.

### Semester 4 plan also has unmet prereqs

- `00970800` needs `00940594` — which the wiki itself places in **semester 5**.
- `01140051` needs `01130013` — absent from the whole plan.

Both are current-plan items, so they do not corrupt the completed set, but the
"current plan" is not prereq-clean as documented.

## Open items

1. ~~Pin `currentSemesterCode`~~ — **DONE**: `2025-2` (see above).
2. ~~Resolve `00960221` vs `00960211`~~ — **DONE**: `0960221` is a stale PDF
   code; **`00960211` is the same course** and is what ISE students take today.
   Seed `00960211`. Not an ingestion bug.
3. ~~Verify prereq chains~~ — **DONE**. Resolved by domain ruling: seed the wiki
   plan verbatim (`01040042` -> `01040044`, keep `01040065`). The two unmet
   prereqs are catalog data gaps; see the scope limit above.
4. ~~Confirm each completed course was actually offered in its assigned
   semester~~ — **DONE**: 17/17 verified against `course_offerings`.
