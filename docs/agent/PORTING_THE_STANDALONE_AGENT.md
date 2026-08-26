# Porting the standalone agent into `services/ai`

How to make UniPilot's agent behave exactly like the one in
[`unipilot-agent`](https://github.com/TymorIbrahim/unipilot-agent).

This is not a migration guide written from the outside. Roughly half of it has
been done and verified, and every trap listed below was hit rather than
imagined. Where a step says something will fail, it failed.

---

## 0. The one thing to understand first

**The two codebases are the same lineage.** `unipilot-agent` was extracted from
`services/ai`, then diverged. They still share:

- the same package root — `app.agent_core.facts.*` in both, so imports are
  identical and files can be moved without rewriting them;
- the same module names, file for file;
- the same entry contract — `/advise` already calls `run_advice`, `to_advice`
  and `LoopResult`.

So this is **not** "add a new agent". It is "fast-forward the one that is
already wired in". Nothing in `services/api`, the SSE handler, or the frontend
advisor shape needs to change.

What diverged is size:

| module | `services/ai` | `unipilot-agent` |
|---|---|---|
| `postconditions.py` | 210 | **1106** |
| `answer.py` | 354 | **871** |
| `loop.py` | 391 | **763** |
| `service.py` | 216 | **610** |
| `answer_verify.py` | 173 | **492** |
| `sources.py` | 227 | **545** |

---

## 1. The boundary that decides everything

`unipilot-agent` reads **Supabase/Postgres**. `services/ai` reads **MongoDB**.
Every file falls into one of three tiers, and putting a file in the wrong tier
is how you break `/advise`.

### Tier A — data-agnostic. Copy verbatim.

Pure functions over text, numbers and typed facts. No knowledge of where a
record came from.

```
postconditions.py   answer.py      answer_verify.py   codec.py
operators.py        prose.py       forecast.py        runner.py
```

Already identical in both repos, nothing to do:

```
types.py   presentation.py   propose.py   traverse.py   optimize.py
```

### Tier B — data-coupled. Do NOT copy.

| file | why |
|---|---|
| `predicate.py` | agent has `compile_to_sql`; UniPilot has `compile_to_mongo` |
| `conversation.py` | `SupabaseConversations` vs `MongoConversations` |
| `ledger.py` | `SupabaseLedger` vs `MongoLedger` |
| `sources.py` | the schema registry itself |
| `find.py`, `wiring.py`, `dispatch.py`, `service.py` | query building, context assembly, SQL |

`catalog.py` was on this list and has since been **copied whole** — it names
sources, and once all four existed there was nothing left in it that lied. See
§4 and §5.

> **Trap.** `conversation.py` and `ledger.py` have **no `app.*` imports at all**
> and are among the most data-coupled files in the tree. An import graph will
> tell you they are safe to copy. They are not. Check the class names.

### Tier C — the system prompt.

`adapter.py` is prose, but it *names sources*. It teaches the model to use
`prerequisite_edges` and `remaining_courses`. Porting it before step 4 tells the
model to use tools that do not exist — the exact "advertise a capability you do
not have" failure this codebase is built to prevent.

---

## 2. Environment, and a trap that costs money

`services/ai` needs `motor` and `networkx`. The agent repo **deliberately
dropped both**, so its virtualenv cannot run these tests.

```bash
cd services/ai
.venv/bin/python -c "import motor, networkx"   # must succeed
```

Run the suite with:

```bash
.venv/bin/python -m pytest tests/agent_core -q -o addopts="" -m "not live"
```

> **Trap — this one bills you.** `pytest.ini` sets
> `addopts = --cov=app --cov-report=... -m "not live"`. The coverage flags and
> the live-test exclusion are in the *same* string. Passing `-o addopts=""` to
> silence coverage **also drops `-m "not live"`** and runs the tests that make
> real LLM calls. Always re-add the marker explicitly, as above.

**Baseline before you start: 533 passing, 6 deselected.**

---

## 3. Port Tier A

Do these one at a time and run the suite after each. Everything is recoverable —
copy the file you are replacing first.

```bash
AGENT=/path/to/unipilot-agent/app/agent_core/facts
AI=services/ai/app/agent_core/facts
mkdir -p /tmp/port-backup

for f in postconditions.py answer_verify.py answer.py \
         operators.py prose.py codec.py forecast.py runner.py; do
  cp $AI/$f /tmp/port-backup/$f 2>/dev/null
  cp $AGENT/$f $AI/$f
done
```

### Before overwriting anything, prove the agent's version is a superset

`services/ai` may hold work the agent lacks. Check, do not assume:

```bash
comm -13 <(grep -oE "^(def|class) [A-Za-z_]+" $AGENT/postconditions.py | sort -u) \
         <(grep -oE "^(def|class) [A-Za-z_]+" $AI/postconditions.py   | sort -u)
```

Empty output means the agent has everything. **Non-empty means merge, not copy.**

### Expected failures, and what they mean

Porting `answer.py` breaks four tests. This is correct — they assert the *old*
rendering contract:

| test | why it fails |
|---|---|
| `test_it_lists_every_field_per_record` | labels are now readable (`courseNumber` → `course number`) |
| `test_one_line_per_record` | same |
| `test_it_drops_object_ids...` | a one-record `:detail` no longer carries a list bullet |
| `test_loop.py::test_an_unsound_plan_is_sent_back...` | asserts the old string exactly |

Fix by porting the agent's `tests/agent_core/facts/test_answer.py` (a strict
superset — 71 tests vs 41), and by editing the single assertion in `test_loop.py`
to:

```python
assert result.answer.text == (
    "Winter plan: number 00940412 · credits 4 · min grade 19.25"
)
```

> Do **not** overwrite `test_loop.py` wholesale. It contains
> `test_the_prompt_carries_the_catalog_and_the_facts`, which the agent does not
> have.

### Port the tests whose dependencies are satisfied

Only copy a test file if every `app.agent_core.facts.*` module it imports has
already been ported. This script selects them:

```bash
PORTED="postconditions|answer|answer_verify|types|prose|predicate|operators|codec|forecast|runner"
for f in $(comm -23 <(ls $AGENT_TESTS/*.py | xargs -n1 basename | sort) \
                    <(ls $AI_TESTS/*.py    | xargs -n1 basename | sort)); do
  deps=$(grep -oE "from app\.agent_core\.facts\.[a-z_]+" $AGENT_TESTS/$f | sed 's/.*\.//' | sort -u)
  [ -z "$(echo "$deps" | grep -vE "^($PORTED)$")" ] && cp $AGENT_TESTS/$f $AI_TESTS/$f
done
```

One ported test must be **deleted**, not fixed:
`test_group_identifier_guard.py::TestTheScorerDoesNotCreditAnEdgeDump` imports
`evaluation/checks.py` from the agent repo. It tests the *measurement harness*,
not the agent, and that harness does not exist here.

**After Tier A: 1554 passing, 0 failing.** `/advise` now runs behind 20 wired
post-conditions instead of 5.

---

## 4. The four sources — DONE

> **This section was wrong when it was written, and the correction is the most
> useful thing in it.** It claimed `services/ai` had none of the four. Two were
> already here and working: `wiring.build_wiring` derives `prerequisite_edges`
> (2,919 edges) and `track_courses` (2,944 memberships) live from the graph, and
> the `engine._built` gate they sit behind was genuinely passing. **Measure
> before believing an inventory, including this one.**

| source | what it is | how `services/ai` gets it |
|---|---|---|
| `prerequisite_edges` | one row per edge, carrying a `group` | **already existed** — derived from the graph |
| `track_courses` | every course in a degree track | **already existed**, but had no `category` |
| `passed_courses` | transcript rows where `passed` is true, joined to course codes | `ViewSchema` in `facts/views.py` |
| `remaining_courses` | track courses the student has not passed | `ViewSchema` in `facts/views.py` |

The real gap was underneath all four: **Mongo stores no `passed` and no
`creditsCounted`**. In `unipilot-agent` those are generated columns; here
`completed_courses` has `grade` and `creditsEarned` and nothing that says whether
a course counts. Live, 28 of 554 rows are below the pass mark and one of them is
graded 32 while still carrying its full 5.5 credits — summing the obvious column
gives 1824.0 where the answer is 1792.5.

### What was built

**`SourceSchema.computed`** — derived fields as Mongo aggregation expressions,
applied in `$addFields` **before** `$match`. That ordering is the whole point: it
makes `passed` an ordinary field the model can filter, group and sort on. Compute
it after the fetch instead and `passed = true` filters on a field that does not
exist yet — matching nothing, and reporting an empty transcript as *complete*.

**`ViewSchema`** — an async, database-aware source. `remaining_courses` needs it
because its two halves live in different stores: the curriculum is a networkx
edge set in memory, the transcript is in Mongo, and no `$lookup` spans those.
Everything after the fetch is the `DerivedSchema` contract unchanged.

**`field_notes` and `order_tiebreak`** — both were missing from the schema types
here, so the ported notes had nowhere to render. Notes appear beside the field
they qualify in `_render_sources`, which is where the column actually gets
chosen.

**`track_courses.category`** — read back off the track page's section headings
(`views.track_categories`), since the graph records the wikilink and drops the
section. 85.7% of links classify; the rest are left **absent rather than
guessed**. Test the elective pattern *before* the mandatory one: a heading like
`קורסי בחירה לפי סמסטר` contains the semester word, and checking mandatory first
types every elective under it as required.

### Two things the data itself will not give you

**28% of transcript rows cannot reach a course code.** Only 105 of 243 distinct
`completed_courses.courseId` values exist in `courses` — the catalog was
re-promoted and the `_id`s rotated while transcripts kept the old ones. There is
no second route: `courseOfferingId` is null on all 554 rows, and
`staging_courses` matches none of them. So `passed_courses.courseNumber` is
absent on 28% of rows, and `remaining_courses` under-subtracts for those
students. This is a data-integrity problem, not a porting one, and it is the
single biggest limit on how well the ported layer can work here.

**`programSlug` and the graph disagree on track names.** The graph slugs all 52
tracks `track-<name>`; some profiles store the bare `<name>`. That mismatch does
not fail — it returns an *empty curriculum*, which reads as "you have nothing
left to take". `_resolve_track` tries exact, then prefixed, and returns `None`
rather than fuzzy-matching: declining to plan beats planning someone else's
degree.

### The two views are plain derivations

`passed_courses` (Postgres, for reference):

```sql
select cc."courseId", cc."userId", c."courseNumber", c."title",
       cc."grade", cc."creditsEarned", cc."creditsCounted",
       cc."semesterCode", cc."attempt"
from completed_courses cc
left join courses c on c."_id" = cc."courseId"
where cc."passed";
```

`remaining_courses`:

```sql
select p."userId", tc."course" as "courseNumber", c."title",
       c."credits", tc."category", tc."track"
from student_profiles p
join track_courses tc on tc."track" = p."programSlug"
left join courses c on c."courseNumber" = tc."course"
where not exists (
    select 1 from passed_courses pc
    where pc."userId" = p."userId" and pc."courseNumber" = tc."course"
);
```

> **Note the `not exists`.** It is not `not in`. Some `courseNumber` values are
> null, and `not in` with a null in the subquery returns no rows at all —
> silently reporting that the student has nothing left to take.

### Implementing them on Mongo

For each source, add a `SourceSchema` to `services/ai/app/agent_core/facts/sources.py`
following the existing `COMPLETED_COURSES` pattern — `collection`, `key`,
`fields`, `basis`, `joins`, `object_id_fields`. Copy the field types from the
agent's `sources.py`; copy the **field notes** too, since several of them record
bugs that cost real debugging (`track_courses.course` is a course NUMBER not an
id; `student_profiles.maxCreditsPerSemester` is the student's own cap and *not*
the institutional rule).

Two implementation routes:

1. **Aggregation pipelines** — express each view as a `$lookup`/`$match`
   pipeline. No new storage, always current, costs a join per query.
2. **Materialised collections** — build them in the seed/worker job like the
   agent does. Faster reads, needs invalidation when a transcript changes.

Whichever you choose, `find.py` must be able to reach them through
`compile_to_mongo`. **Do not port the agent's `find.py`** — it builds SQL.

### Verify with the reachability test

`services/ai` has a reachability suite. After adding each source, confirm the
model can actually route to it — a source that exists but cannot be reached from
any advertised tool is invisible, and unit tests cannot see the difference.

```bash
.venv/bin/python -m pytest tests/agent_core/facts/test_reachability.py \
  -q -o addopts="" -m "not live"
```

---

## 5. Then, and only then, port Tier C

Once the four sources exist and are reachable:

```bash
cp $AGENT/catalog.py $AI/catalog.py
cp $AGENT/adapter.py $AI/adapter.py
```

`test_catalog.py::TestNoDrift::test_the_catalog_mentions_no_tool_that_does_not_exist`
is the gate. It failed on the first attempt with:

```
assert not {'all_groups', 'cycle_path', 'met_groups', 'remaining_courses'}
```

It failed again on exactly those four after step 4 was complete. Three
(`all_groups`, `met_groups`, `cycle_path`) are illustrative fact names and a
`forecast` argument, and were added to `known_vocabulary`. The fourth,
`remaining_courses`, was a **real reference to a source that did not exist** the
first time, and the test was right to stop it — by the second attempt the source
existed and the test simply did not know about it.

That is the fix worth copying: `known_vocabulary` now **derives** the source
names by calling the same constructors production uses (`_source_names`, with a
stub engine so no graph is built) rather than listing them. A hand-written list
would either omit the graph-derived sources — failing the catalog for naming
things that DO exist — or list them and keep approving them after removal.
`test_the_source_vocabulary_is_derived_not_transcribed` pins that.

Keep the test strict. It is the thing standing between the model and being told
to use a tool that is not there.

---

## 6. Remaining modules

`loop.py`, `dispatch.py`, `service.py` and `wiring.py` all carry improvements and
all touch the data layer to some degree.

All done except `wiring.py`, which must never be copied.

- **`dispatch.py`** — **copied whole.** It has *zero* SQL references and imports
  only from `facts/*`, `loop/course_names` and `clients/internal_api_client`,
  all of which match. The "port incrementally, tool by tool" advice this section
  used to give was unnecessary. One signature changed:
  `_resolve_fact_refs(predicate, facts)` now takes the facts mapping rather than
  the whole context — a deliberate narrowing; update the four call sites in
  `test_sources.py`.
- **`loop.py`** — **copied whole**, after `dispatch.py`. Two things to know:
  - It renames `_render_sources` to `render_sources`, and **the ported
    `adapter.py` already imports the public name.** Port `adapter.py` without
    `loop.py` and `build_system_prompt` raises `ImportError` at call time — a
    function-local import, so the whole suite stays green while the agent cannot
    answer anything. `test_the_system_prompt_can_actually_be_built` now pins it.
  - The catalog moves OUT of the turn prompt into the system prompt, so
    `test_loop.py::test_the_prompt_carries_the_catalog_and_the_facts` fails
    correctly. It is now two tests: the turn prompt carries the question and the
    facts, and the catalog is in the system prompt and *not* repeated per turn.
- **`service.py`** — **copied, then three things rewritten.** Only two lines
  touched the database:
  - `_profile_of` — one SQL statement, now a Mongo aggregation
    (`$lookup` degree_programs, `$lookup` a scoped sum of passed credits). It
    shares `sources.PASSED_EXPRESSION` rather than restating the pass rule.
  - `SupabaseConversations` → `MongoConversations`, `app.db.postgres` →
    `app.db.mongo`.
  - `_audience_of_profile` and its `build_context(..., audience)` argument were
    **dropped, not ported**. Audience selects a rulebook inside the agent's
    `CorpusRetriever`; this repo's `WikiRetriever` wraps the graph engine and has
    no such concept. Carrying the parameter would have been a no-op that looks
    like a capability. *This is the one real capability the port leaves behind.*
- **`course_names.py`** — **merged, not copied.** Take the agent's
  `_hebrew_name`, `_same_course`, `pair_codes_with_names` and
  `course_display_name(value, hebrew=)`; keep this repo's `_name_index` (walks
  the graph) and `load_catalog_names` (already Mongo, already correct). Widen the
  index to `code -> (english, hebrew)` so `_same_course` has something to compare.
  Measured after the merge: 2,601 wiki names, 2,613 catalog names, and
  corroboration rejects **131 of 1,752 (7.5%)** wiki names as belonging to a
  different course — matching the ~6.8% this document predicted.
- **`wiring.py`** — builds `DispatchContext` from the database. Rewrite for
  Mongo; **do not copy**. It now also carries the category derivation.

---

## 7. Two things worth carrying over that are not in `facts/`

**`course_names.py`.** In the agent this resolves a course code to a name from
two sources: the wiki corpus (English, ~2601 courses) and the catalog (Hebrew,
all courses), preferring whichever matches the question's language. Both sources
were **dead through the port** — `_name_index` read a graph engine that did not
exist in the agent, and `load_catalog_names` had no call site — so every answer
carried bare 8-digit codes and nothing raised. Check both are actually connected:

```python
from app.agent_core.loop.course_names import _name_index
assert len(_name_index()) > 0    # returned 0 for months, silently
```

Note the agent requires the wiki page to **corroborate** the catalog title
before using its English name — the wiki's code→page mapping is wrong for about
6.8% of courses, and preferring it wholesale attached a wrong name to roughly
one course in fifteen.

**The temperature fix in `llm_client.py`.** gpt-5 models accept only their
default temperature. OpenAI direct silently ignores `temperature=0.0`; LiteLLM
(and therefore LLMod) returns a 400. Match on the **model name**, not the
provider — `MB5R2CF-azure/gpt-5.4-mini` and `gpt-5.4-mini` are the same model
reached two ways.

---

## 8. Verification

Unit tests are necessary and **not sufficient** — that is the recurring lesson
in both repos. A guard that goes silent, a name index that returns `None`, an
argument the parser drops: all of them keep the suite green.

| level | command | proves |
|---|---|---|
| unit | `pytest tests/agent_core -q -o addopts="" -m "not live"` | nothing regressed |
| reachability | `pytest tests/agent_core/facts/test_reachability.py ...` | every advertised tool can be fed |
| live | `POST /advise` with a real student | the whole path works |

Port the agent's evaluation harness too — `evaluation/run_eval.py` scores
against ground truth **derived from the data by SQL**, never by asking the agent.
Comparing runs to each other proves only consistency, and this agent was once
consistently wrong about credits across five identical runs.

---

## 9. Order of work

1. Tier A modules + their tests — **done, 1554 passing**
2. The four sources on Mongo — **done, 1568 passing**
3. Reachability verification — **done, 1571 passing**
4. `catalog.py` + `adapter.py` — **done, 1573 passing**
5. `dispatch.py`, `loop.py`, `service.py` — **done, 1578 passing**
   (`wiring.py` correctly not copied)
6. `course_names.py` — **merged and verified**: 2,601 wiki + 2,613 catalog names,
   both languages rendering, corroboration rejecting 7.5%
7. Live `/advise` against a real student, in both languages — **done, and it
   found a bug nothing else could**

## 10. What the live run found

Scored against student `6a578a2da43a2cfe1bcc791c` (ISE, 129.5/155 credits), whose
ground truth is computable in SQL and is the same student this repo's field notes
cite. The two numbers that matter are unambiguous:

| | wrong answer | right answer |
|---|---|---|
| credits completed | 135.0 (`creditsEarned`) | **129.5** (`creditsCounted`) |
| GPA | 72.64 | **74.45** |

| question | turns | time | result |
|---|---|---|---|
| How many credits have I completed? | **1** | 8.4s | 129.5 ✅ |
| What is my GPA? | 2 | 9.8s | 74.45 ✅ |
| Which courses do I still need to take? | 8 | 56.3s | **refused** ❌ |
| כמה נקודות זכות נשארו לי? | 1 | 2.0s | 25.5, in Hebrew ✅ |

The credits question answered in **one turn with no tool calls at all** — the
seeded facts doing exactly what they were ported for. Both derived-column traps
were avoided.

### The refusal, which was the whole point of running this

The one question these sources exist for was the one that failed, and unit tests
and reachability had both passed on it. The transcript showed two things:

**A post-condition misfiring.** `check_term_load` read the 21 remaining courses
(50 credits — the CORRECT total, and exactly what `remaining_courses.credits`
documents) as a 50-credit *semester*, and rejected the answer three times. The
model had no legal move, because nothing was wrong with the answer, and the run
burned its rejection budget and returned a partial.

The cause is in `_plan_collections`: any collection carrying numeric `credits` is
treated as a plan. That looseness was deliberate — requiring `min_grade` had let
ordinary term plans ship unverified — but it does not distinguish a PLAN from a
LISTING. Fixed with `_is_term_scoped`: rows carrying a `term` are a plan and are
always checked; with no term label, the question and answer decide. Pinned in
both directions by `TestAListingIsNotATerm`, including that "how many semesters"
still trips the ceiling.

**After the fix: answered in 6 turns / 39.8s**, all 21 courses listed with names
and `category`. That single run exercised the whole port end to end —
`remaining_courses` reached, category derived from the wiki headings, and
`pair_codes_with_names` falling back to Hebrew where the wiki has no English
title.

> **The lesson this document keeps re-learning.** 1,578 unit tests and 37
> reachability checks were green while the flagship question returned nothing.
> Neither can see a check that fires when it should not — the answer was correct,
> the facts were correct, and the verifier refused it. Run step 7.

---

## Appendix — current state

Ported and verified in `services/ai`:

```
postconditions.py   5 → 21 checks
answer_verify.py    5 → 20 checks wired
answer.py           readable labels, clarification exception,
                    mid-sentence table refusal, enum words, list dedup
codec.py            silently-dropped `field` argument, the `traverse` hint
operators.py  prose.py  forecast.py  runner.py
catalog.py          copied whole, after the four sources existed
adapter.py          copied whole — the recipes now have sources to read
dispatch.py         copied whole; no SQL in it at all
loop.py             copied whole; catalog moved to the system prompt
tests               533 → 1578 passing
```

Merged rather than copied:

```
service.py        _profile_of rewritten as a Mongo aggregation; Supabase and
                  postgres swapped for Mongo; `audience` DROPPED (see §6)
course_names.py   the agent's Hebrew / corroboration / pairing logic onto this
                  repo's graph-backed index and Mongo catalog loader
```

Written for Mongo rather than copied:

```
find.py       + SourceSchema.computed, ViewSchema, field_notes, order_tiebreak
sources.py    + passed / creditsCounted, PASSING_GRADE = 55, the ported notes
views.py      NEW — passed_courses, remaining_courses, track_categories
wiring.py     + category on track_courses, registers the two views
loop.py       _render_sources renders field notes beside the field
```

`PASSING_GRADE = 55` is not invented here: it is `PASSING_GRADE_THRESHOLD` in
`services/web/src/lib/transcript.ts`, and the product already tells students
"grades of 55 and above count toward progress".

Reverted after failing, and why:

```
predicate.py   compile_to_sql vs compile_to_mongo — service would not import
```

Untouched, correctly:

```
conversation.py  ledger.py  find.py(structure)  dispatch.py  service.py
```

New tests: `tests/agent_core/facts/test_views.py` (14), plus two reachability
tests that go through the REAL wiring — the existing ones build contexts from
`REGISTRY` alone and would have stayed green with all four sources unreachable.
Both were confirmed to fail when their fix is removed.

Backups of every replaced file: `/tmp/port-backup/`. Nothing is committed —
the branch was already dirty before this work began.
