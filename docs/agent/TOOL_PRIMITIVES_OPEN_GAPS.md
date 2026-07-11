# Open gaps surfaced while tracing a real plan through the 9 tool primitives

While walking step-by-step through a real 4-step plan (steps A–D of the "what happens if
I fail Data Structures" turn, `services/ai/tests/agent_core/live_eval_logs/full_turn-20260710T191712Z.json`)
against the 9 tool primitives (`get_entity`, `search_knowledge`, `traverse_relationship`,
`interpret_text`, `extract_temporal_pattern`, `apply_deterministic_rule`, `mutate_state`,
`search_over_state`, `propose_action` — `compose_answer` is deliberately excluded from this
set, treated as a separate final-composition step), several concrete gaps surfaced that
aren't yet resolved anywhere in the codebase or docs. Each is listed with why it matters and
a suggested way to handle it.

None of these are bugs in the 9 primitives themselves — each primitive does exactly what its
own contract says. The gaps are all at the seams: what a plan step assumes exists that
doesn't, or what one role needs from another that isn't wired up yet.

---

## 1. GPA / academic standing / probation status are not stored facts anywhere — RESOLVED

**Where it surfaced:** Step A asked a Retrieval subagent to fetch "academic standing (GPA,
probation status)." Checked both schemas directly (`services/api/app/schemas/student_profile.py`,
`services/api/app/schemas/completed_course.py`) — `student_profiles` has no GPA/probation
field, and `completed_courses` only stores per-course `grade`/`gradePoints`/`creditsEarned`,
never an aggregate.

**Why it matters:** A Retrieval-role subagent given this objective as written will either
silently fail the success criterion or try to compute GPA itself — the latter violates the
Calculation/Retrieval role split in `AGENT_VISION.md` §7.2 (Calculation is the role
constrained to "cite which rule and which facts it applied"; Retrieval isn't supposed to
compute anything).

**How it's resolved:** Confirmed against a REAL model call, not just architectural plausibility
— `tests/agent_core/test_task_handler_gap_live_eval.py::test_gap_1_gpa_probation_step_is_not_treated_as_pure_retrieval`
runs the real classifier (`task_handler_classifier.py::classify_step`) and the real nested
Planner (`NESTED_PLANNER_V1`) against Step A's actual, verbatim recorded objective. The task
handler's classifier initially only flagged the step non-atomic without any domain knowledge
about WHY, and re-running the same live eval showed this was flaky: the nested planner's own
decomposition sometimes still routed a sub-step asking for "cumulative GPA, probation status"
straight to Retrieval, which has no honest way to compute it. Fixed with one new instruction
added to BOTH the shared Planner contract (`planning/planner.py::_planner_contract`, which
`NESTED_PLANNER_V1` inherits via `.model_copy`) and the classifier's own contract
(`orchestrator/task_handler_classifier.py::_task_handler_classifier_contract`): a
cumulative/semester GPA or academic-standing/probation status is explicitly called out as a
DERIVED fact (computed from raw per-course grades via `apply_deterministic_rule`), never a
field a bare Retrieval fetch can return. Re-running the live eval after this fix passed
consistently.

---

## 2. No resolution path from a student's declared program to a wiki program slug — RESOLVED

**Where it surfaced:** Step A needs the student's declared program's actual requirements
(for "progress towards degree requirements"). `student_profiles` stores `programType` (free
string) and `degreeId` (a Mongo `ObjectId`) — neither is obviously "the program's wiki slug"
that `get_entity(entity_type="program", entity_id=...)` expects (e.g. `program-alonim`).

**Why it matters:** Without this mapping, a Retrieval subagent has no deterministic way to
go from "this student's profile" to "this program's requirement text" — it would have to
guess or fall back to a fuzzy `search_knowledge(query=programType)`, which is exactly the
kind of unreliable, non-deterministic resolution the primitive design otherwise avoids
(compare: `get_entity`'s own `course` dispatch merges catalog + wiki via a real, tested
reverse-lookup, not a guess).

**How it's resolved:** Turned out simpler than either originally-suggested option once
`services/api`'s catalog data was actually checked: no new lookup table was needed at all.
`degree_programs` documents already carry their wiki slug under `metadata.wikiPage`, and
`catalog_path_options` documents (minors, special/graduate programs) already carry it as a
top-level `wikiSlug` — both set by `services/api/app/db/catalog_bootstrap.py`. Profile
creation was *already* fetching that exact document, via
`services/api/app/services/student_profile_validation.py::validate_degree_id_for_profile`,
to validate `degreeId` — it just discarded the slug afterward. That function now returns
the resolved slug instead of `None`, and `services/api/app/routes/student_profile.py`
persists it as a new `programSlug` field on the `student_profiles` document (server-derived
only, never client-supplied; recomputed on update only when `degreeId` itself changes).
Since `get_entity(entity_type="student_profile", ...)` returns the raw Mongo document
sanitized, `programSlug` is visible to `services/ai` with zero changes needed there. See
`services/api/tests/unit/test_student_profile_validation_service.py`,
`test_student_profile_repository.py`, and
`services/api/tests/integration/test_student_profile_integration.py` for coverage.

---

## 3. No primitive maps a wiki search hit (slug) to a course code — RESOLVED

**Where it surfaced:** Step B needs to resolve the name "Data Structures" to a course code.
`search_knowledge` returns `slug`/`title`/`kind`/`content`/`score` (confirmed directly in
`search_knowledge.py`) — never a course code. `get_entity(entity_type="course", ...)`
requires the code as `entity_id`. The only bridge today is the LLM noticing that course
wiki slugs conventionally start with the 8-digit code (e.g. `00440148-waves-distributed-systems`)
and parsing it out — not a structured, testable guarantee.

**Why it matters:** This is silent, implicit behavior riding on a naming convention rather
than a contract. If that convention is ever violated for one page (a slug that doesn't lead
with the code, a typo, a manually-created page), name-to-code resolution breaks with no
error signal — it just silently extracts the wrong code or fails to extract one at all.

**How it's resolved:** `search_knowledge.py` now adds a `courseCode: str | None` field to
each match, sourced from `AcademicGraphEngine.slug_to_course_code` (keyed by slug) whenever
`kind == "course"`, `None` otherwise — a small, backward-compatible addition to the existing
envelope, not a new primitive. The implicit "course slugs lead with their code" convention
is now an explicit, tested contract; see
`services/ai/tests/agent_core/tools/test_search_knowledge.py`'s
`test_course_kind_hit_resolves_course_code_from_the_real_engine_map` and
`test_non_course_kind_hit_has_none_course_code`.

---

## 4. Mandatory-vs-elective course status isn't a graph fact — it's prose — RESOLVED

**Where it surfaced:** Step B needs "which degree requirements it fulfills (mandatory,
elective, etc.)." `traverse_relationship`'s `belongs_to`/`contains` edges only say a course
links to a track — confirmed directly in `traverse_relationship.py` — there's no
mandatory/elective attribute on the edge itself. That classification lives, if anywhere, in
the track page's own prose/requirement table.

**Why it matters:** Getting this right requires `interpret_text` (prose comprehension), but
`interpret_text` is a Group 4/LLM-intrinsic primitive that per §7.2's role-guardrail examples
reads more like an Interpretation-role tool than a Retrieval-role one. Whether a Retrieval
subagent's tool ceiling includes it is an orchestrator decision that doesn't seem to be made
anywhere yet — so this success criterion is currently unimplementable by a pure-Retrieval
subagent as scoped.

**How it's resolved:** Option (b) from the original suggestion — keeping Retrieval's tool
ceiling unchanged — confirmed against real model calls in
`tests/agent_core/test_task_handler_gap_live_eval.py`. One new instruction added to both the
shared Planner contract and the classifier's contract (same two files as gap #1's fix) states
that a course's/program's requirement-fulfillment status (mandatory/elective/core) lives in
prose, not a graph edge, and must never be bundled into the same step as a structural catalog
fetch. Confirming this surfaced a SECOND, deeper issue the original write-up didn't
anticipate: requirement-fulfillment status is relative to one specific degree program (the
same course can be mandatory in one program, elective in another), so it can't be resolved at
all without knowing which program applies. The real, original recorded plan
(`live_eval_logs/full_turn-20260710T191712Z.json`) never wired this step to depend on the
sibling step that fetches the student's declared program — a dependency-graph gap, not a
role-grant gap. Fixed with a second instruction in the shared Planner contract: a
requirement-fulfillment step must declare a dependency on whichever step fetches the
student's declared program (adding one if none exists yet).
`test_gap_4_mandatory_elective_step_gets_an_interpretation_capable_path` confirms the nested
planner now correctly separates the two concerns (and, absent program context, legitimately
returns `blocked_needs_clarification` rather than guessing — a pass, not a failure);
`test_gap_4_top_level_plan_wires_requirement_fulfillment_step_to_program_step` confirms a
fresh, real, end-to-end top-level plan (via a real Request-Understanding + Planner call, not
hand-built steps) now wires that dependency edge itself, which should prevent this
clarification need from arising at all in normal use.

---

## 5. "No unusual temporary exceptions apply" cannot be verified with the current primitive set

**Where it surfaced:** Step C's one stated assumption includes this clause. There's no
entity type, relation, or primitive today for "is there a currently-active policy exception
or announcement" — the 9 primitives cover structured records, wiki prose, computed rules,
and simulated state, but nothing time-bound-and-exceptional in that specific sense.

**Why it matters:** An Interpretation subagent asked to verify this assumption has no
honest way to confirm it — it can only interpret whatever static wiki text it finds, which
by definition won't reflect a genuinely temporary exception unless someone already edited
the wiki to mention it.

**Suggested handling:** Don't try to solve this with a new primitive speculatively — YAGNI
applies here until there's a real, recurring need for "check active exceptions." For now,
the correct behavior is for the subagent to explicitly flag this half of the assumption as
*unverifiable* in its output (a warning, not a silent pass) rather than reporting the
assumption as confirmed. If temporary exceptions turn out to be a recurring real need, that's
the trigger to design a proper `entity_type` (e.g. `policy_exception`) for it then — not now.

---

## 6. Step D conflates the Calculation and Composition roles — RESOLVED

**Where it surfaced:** Step D's objective asks a single subagent to both *compute*
consequences (GPA impact, probation trigger, delay estimate) and *explain* them in prose.
Per §7.2, Composition is explicitly constrained to "never introduce a number or status it
wasn't handed" — which only makes sense if computation happens in a prior, separate step.

**Why it matters:** As scoped, one subagent has to either be granted both compute primitives
and `compose_answer` (blurring the role boundary the rest of the design relies on for
guardrails like "Composition never introduces new numbers"), or silently skip the
composition-only discipline. Either way, the role separation that makes Composition's
guardrail meaningful stops being enforceable for this step.

**How it's resolved:** The task handler (`services/ai/app/agent_core/orchestrator/task_handler.py`)
now sits between the Orchestrator and every step. A cheap classifier
(`task_handler_classifier.py::classify_step`) judges whether a step like D reduces to one
specialist call; a compound objective like D's ("compute consequences" + "explain them")
is exactly the shape its prompt contract instructs it to classify `atomic=false` on. A
non-atomic step gets its own private, bounded sub-plan via a recursive Planner invocation
(`planning/planner.py`'s `NESTED_PLANNER_V1` contract) — which is free to produce a
Calculation-then-Composition sub-plan shape (each sub-step gets its own fresh role
assignment from the same classifier), rather than forcing one subagent to do both jobs.
This isn't a Planner-authored fix (the top-level Planner still doesn't decompose steps
itself, by design) — it's a dispatch-time fix, exactly the "role and reasoning-budget
decisions belong to the Orchestrator, made fresh at dispatch time" principle already
established for ordinary steps, just extended to steps that need more than one dispatch.

---

## 7. Step D's success criteria need a fact no upstream step (A/B/C) ever fetches — RESOLVED

**Where it surfaced:** Step D needs "graduation timeline if repeat is needed," which per
`AGENT_VISION.md` §10 point 4 fundamentally depends on the course's offering cadence
(Winter-only vs. Winter+Spring, etc.) — that's `extract_temporal_pattern`. Step B's objective
(the only step that looks at the course itself) stops at code/credits/prerequisites/
dependents/track role — it never asks about offering pattern. Step D's `depends_on` is only
`["A", "B", "C"]`, none of which retrieved this fact.

**Why it matters:** This is a genuine hole in the plan as generated, not a gap in the tool
surface — `extract_temporal_pattern` exists and is fully implemented. The plan simply never
scheduled a call to it, so Step D cannot actually satisfy its own graduation-timeline success
criterion from its declared dependencies alone.

**How it's resolved:** This turned out not to need Monitor/replanning changes at the
top-level plan-graph level, as originally suggested — the fix is one level down. Once
step D is classified non-atomic, its private nested Planner (seeded with D's own objective,
`success_criteria`, and `assumptions_to_verify` as `open_questions`) discovers mid-decomposition
that it needs the course's offering pattern and schedules an `extract_temporal_pattern`
sub-step itself, as part of producing D's own sub-plan — the same adaptive, invoked-repeatedly
rhythm the top-level Planner already uses, just scoped privately to resolving one step
(`task_handler.py::_run_nested_subplan`). A sub-step that still can't be satisfied keeps
threading `monitor_flags`/`replan_reason` into further rounds (bounded by
`DEFAULT_MAX_TASK_HANDLER_ROUNDS`), so a step whose real data needs weren't fully anticipated
by the top-level plan gets a real chance to self-correct before failing, rather than silently
returning an incomplete result.

---

## Summary table

| # | Gap | Surfaced in | Fix type | Status |
|---|-----|--------------|----------|--------|
| 1 | GPA/probation not stored; shouldn't be computed by Retrieval | Step A | Planner/classifier prompt instruction (derived-fact rule) | Resolved |
| 2 | No program → wiki-slug mapping | Step A | Propagate existing catalog metadata (`programSlug` on `student_profiles`) | Resolved |
| 3 | No slug → course-code field in `search_knowledge` output | Step B | Small primitive-output addition (`courseCode`) | Resolved |
| 4 | Mandatory/elective status needs `interpret_text`, role grant unclear | Step B | Planner/classifier prompt instruction + dependency-graph wiring | Resolved |
| 5 | "No temporary exceptions" unverifiable | Step C | Behavior fix (flag as unverifiable), no new primitive yet | Open |
| 6 | Step D conflates Calculation + Composition roles | Step D | Task handler (dispatch-time decomposition) | Resolved |
| 7 | Step D needs a fact (`extract_temporal_pattern`) no upstream step fetched | Step D | Task handler (private nested planning) | Resolved |

Gaps 6 and 7 were resolved by the task handler implementation
(`services/ai/app/agent_core/orchestrator/task_handler.py`,
`task_handler_classifier.py`, `task_handler_success_check.py`, and the `NESTED_PLANNER_V1`
contract in `planning/planner.py`) — see `services/ai/tests/agent_core/test_orchestrator_task_handler.py`
for the behavioral test coverage. Gap 3 was resolved with a small additive field on
`search_knowledge`'s output (`services/ai/app/agent_core/tools/primitives/search_knowledge.py`).
Gap 2 was resolved in `services/api` by propagating a wiki slug the catalog already carries
onto `student_profiles` at profile-creation/update time (`app/services/student_profile_validation.py`,
`app/repositories/student_profile_repository.py`, `app/routes/student_profile.py`) — no new
lookup table, reusing data that already existed.

Gaps 1 and 4 were confirmed and resolved against REAL model calls (DeepSeek, via
`services/ai/tests/agent_core/test_task_handler_gap_live_eval.py::pytest.mark.live`), not
just architectural plausibility — the task handler's mechanism alone was not sufficient
without two targeted, explicit prompt instructions added to both
`planning/planner.py::_planner_contract` (inherited by `NESTED_PLANNER_V1` via `.model_copy`)
and `orchestrator/task_handler_classifier.py::_task_handler_classifier_contract`: (1) a GPA/
academic-standing/probation value is a derived fact needing `apply_deterministic_rule`, never
a bare Retrieval fetch; (2) a requirement-fulfillment status (mandatory/elective/core) lives
in prose needing `interpret_text`, and is relative to one specific degree program, so a step
asking for it must depend on whichever step fetches that program. The first live-eval run
before these fixes showed real, observed non-determinism (the classifier sometimes correctly
recognized these cases without any explicit instruction, sometimes didn't) — after adding the
instructions, repeated live runs passed consistently. Gap 5 remains open (deliberately, per
YAGNI — see its own section above).
