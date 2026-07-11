# Higher-level tools

Tracks a second tier of tools built **on top of** the 9 generic primitives
from [`AGENT_VISION.md` §5](AGENT_VISION.md) (tracked separately in
[`TOOL_PRIMITIVES_PROGRESS.md`](TOOL_PRIMITIVES_PROGRESS.md), all done).
These exist purely to save the Orchestrator/subagents from re-deriving the
same multi-primitive chain, via LLM reasoning, at real latency/cost, every
single time a common pattern recurs — `search_over_state` itself already
set this precedent (it internally composes `get_entity`/
`traverse_relationship`/`extract_temporal_pattern`/`evaluate_eligibility`).

**The enumeration-mistake test still applies one layer up.** Every tool
below must stay a generic, parameterized composition — "is this a new
generic operation, or an existing operation with different params" — never
a canned answer to one example question. If a proposed tool only makes
sense for one specific worked example, it doesn't belong here.

## Architecture decision: no role-private tools

**Confirmed with user.** Every higher-level tool is a first-class
`ToolDescriptor`, registered in the same `ToolRegistry` the 9 primitives
already live in — never a role-private code path only one subagent type can
reach. This follows AGENT_VISION §7.1 exactly, extended to cover this new
tier rather than inventing a second access-control mechanism:

- Each role's `tool_grant_ceiling` (`roles/roster.py`) gets the relevant
  higher-level tools added alongside its existing primitive grants (e.g.
  Retrieval's ceiling gains `get_course_profile`/`get_policy_answer`;
  Simulation/Planning's gains `simulate_course_disruption`/
  `audit_graduation_progress`).
- The Orchestrator's per-step dispatch decides, at runtime, which specific
  tools one subagent *instance* actually receives — narrowing, never
  widening, the role's ceiling (§7.1's "least-privilege per instance,
  layered on top of a sensible default per role").
- Nothing about *which tools exist* or *who could theoretically use them*
  is decided by hardcoding a role restriction into the tool itself.

## Resolved flag: composites can't declare `side_effect="propose"`

`ToolRegistry.register()` hard-enforces that only a tool literally named
`"propose_action"` may declare `side_effect="propose"`
(`app/agent_core/tools/registry.py`). This blocks any composite that ends
in a real proposal (e.g. a `compose_answer` + `propose_action` bundle) from
being registered with that classification under its own name.

**Resolved: composites never get `side_effect="propose"`, period** — not
even a relaxed version of the registry rule. A composite that would end in
a proposal instead returns the *ingredients* for one (the
`action_type`/`payload` the caller would pass to `propose_action`) as part
of its own structured, `"read"`/`"compute"`-classified output; the actual
`propose_action` call stays a separate, explicit step the calling subagent
makes itself. This keeps "every real write is its own individually-visible
entry in the tool-call audit trail" intact — judged load-bearing enough
(the same property `propose_action` existing as its own primitive protects
in the first place) to accept one extra round-trip rather than loosen it.
Consequently, no `propose_and_explain`-style bundled-write tool is planned;
`compose_answer` + `propose_action` stay two separate calls a subagent
chains itself in one tool-loop round.

## Status at a glance

| Tool | Category | Composes | Status |
|---|---|---|---|
| `get_policy_answer` | D — interpretation | `search_knowledge` → `interpret_text` | ✅ Implemented + tested (100% line coverage) |
| `get_course_profile` | A — read | `get_entity` + `traverse_relationship` (×3) + `extract_temporal_pattern` | ✅ Implemented + tested (100% line coverage) |
| `check_eligibility` | A — read | `AcademicGraphEngine.evaluate_eligibility` (currently only reachable inside `search_over_state`) + `extract_temporal_pattern` | ✅ Implemented + tested (100% line coverage) |
| `get_track_requirements` | A — read | `get_entity` + `traverse_relationship` | ✅ Implemented + tested (100% line coverage) |
| `simulate_course_disruption` | B — simulation | `mutate_state` (×1-2) + `traverse_relationship` + `extract_temporal_pattern` + `search_over_state` (×2) | ✅ Implemented + tested (100% line coverage) |
| `compare_plans` | B — simulation | Pure diff over two `search_over_state` outputs, no new primitive calls | ✅ Implemented + tested (100% line coverage) |
| `audit_graduation_progress` | C — requirements | `get_track_requirements` + `apply_deterministic_rule` + optionally `search_over_state` | ✅ Implemented + tested (100% line coverage) |
| `find_requirement_substitutes` | C — requirements | `get_track_requirements` + `search_over_state` (new `find_substitute` objective) | ✅ Implemented + tested (100% line coverage) |
| ~~`propose_and_explain`~~ | E — write | ~~`compose_answer` + `propose_action`~~ | ❌ Dropped — see flag resolution above |

## Build order and rationale

1. **`get_policy_answer(question)`** — smallest, zero new architectural
   questions, immediately useful to both Retrieval and Interpretation
   roles. `interpret_text` currently requires an already-known wiki slug;
   in practice a caller usually doesn't have one ("what's the retake
   limit" needs a search first) — this is probably the single most common
   two-step pattern in real use, so it's the highest-value-per-effort
   place to start.
2. **`get_course_profile(course_id)`** — proves the "bundle several
   `get_entity`/`traverse_relationship` calls into one" pattern that
   `get_track_requirements`/`check_eligibility` will reuse.
3. **`simulate_course_disruption(course_id, disruption_type, state)`** —
   highest payoff: this is literally steps 2–5 of the fail-course-X worked
   example (AGENT_VISION §10) that the whole architecture was
   pressure-tested against, currently requiring ~6 chained calls.
4. Remaining tools as follow-up, roughly in the order listed above.

## Design notes per tool (fill in as each is built)

### `get_policy_answer(question)` — ✅ done

File: `tools/composites/get_policy_answer.py`. Tests: `tests/agent_core/tools/test_get_policy_answer.py` (10 cases, 100% line coverage).

- Composes `run_search_knowledge`/`run_interpret_text` directly (the two primitives' own `run_*` functions) — no new data-access path.
- **A real value-add beyond naive chaining**: tries up to `_MAX_SOURCES_TRIED` (3) distinct top-ranked search results in order, stopping at the first `interpret_text` can actually answer from, rather than giving up after just the single top-ranked (but not necessarily correct) match — mirrors the Retrieval role's own documented allowance to "iterate if what it finds is ambiguous" (§6). Bounded, so cost/latency stays predictable even when every candidate fails.
- `search_knowledge` can return multiple chunks from the same page — deduped to distinct slugs (`_distinct_slugs_in_rank_order`, preserving rank order) before spending an `interpret_text` call on each; verified this matters with real data (`"student rights ombudsman"` returns `overview`/`student-rights`/`log` as its 3 distinct top slugs, with `student-rights` appearing 3 times in the raw match list).
- Still fails closed at every stage: empty question, search failure (propagates the underlying error), zero relevant sources found, or every attempted source coming back "cannot determine" (`cannot_determine: tried [...]`, listing exactly what was tried).
- One infrastructure snag hit and fixed during testing (unrelated to this tool's own logic): a `timeout`/`max_retries` extension to the shared `LLMAdapter` protocol landed elsewhere in the codebase mid-session; this test file's own local fake adapter (a duplicate of the one in `test_interpret_text.py`) hadn't been updated to accept the two new kwargs, causing a `TypeError` once real end-to-end LLM-adapter calls actually ran. Fixed by matching the same signature `test_interpret_text.py`/`test_compose_answer.py`'s fakes already had.

### Shared infrastructure change: `ToolOutputEnvelope.warnings`

Found while designing `get_course_profile`: `get_entity.py`'s `_course_entity_result` built a local `warnings` list (`"course_not_in_active_semester_catalog"`, `"no_wiki_page_found_for_course"`) but the envelope it returned had no `warnings` field at all — the list was computed, then silently discarded, and had been since Group 1. **Confirmed with user**: added `warnings: list[str] = Field(default_factory=list)` to `ToolOutputEnvelope` itself (`app/agent_core/tools/envelope.py`) — a small, backward-compatible additive change (every existing call site is unaffected, since it defaults to empty) — rather than having each primitive invent its own ad-hoc "something's off" convention inside `data`. This directly feeds AGENT_VISION §7.3's `SubagentResult.warnings` one layer up. Fixed `get_entity.py` to actually pass its already-computed `warnings` through, added test coverage proving it (`test_course_in_catalog_only_warns_missing_wiki_page`, `test_course_in_wiki_only_warns_missing_catalog_entry`, `test_course_in_both_catalog_and_wiki_has_no_warnings`).

`get_course_profile` is the first tool to actually *rely* on this field: a sub-call (any of the 3 `traverse_relationship` calls, or `extract_temporal_pattern`) failing degrades to an empty list/`null` plus a specific warning (`prerequisites_unavailable`, `dependents_unavailable`, `tracks_unavailable`, `offering_pattern_unavailable`) rather than failing the whole composite — and `get_entity`'s own warnings (e.g. a wiki-only course) propagate straight through into the composite's warnings list too.

### `get_course_profile(course_id)` — ✅ done

File: `tools/composites/get_course_profile.py`. Tests: `tests/agent_core/tools/test_get_course_profile.py` (5 cases, 100% line coverage).

- Composes `get_entity` (course details) + `traverse_relationship` ×3 (`has_prerequisite` forward/backward, `belongs_to` forward) + `extract_temporal_pattern` — 5 primitive calls in 1.
- **Only `get_entity` failing is a hard failure** (`course_not_found`) — nothing to build a profile around otherwise. Every other sub-call degrades gracefully via the new `warnings` field rather than failing the whole call — a genuinely common case, not a hypothetical: a wiki-only course (no catalog entry) has no plain-course-code graph node in the general case, so its `traverse_relationship` calls would come back `entity_not_found`.
- **A real data quirk found while writing tests, not assumed**: course `02360861` (used elsewhere as the canonical "wiki-only, no catalog entry" example) turned out to still have a real graph node — because some *other* course's prerequisite string mentions it, and `build_graph()`'s prerequisite-parsing loop adds a node for every course code it encounters that way, regardless of whether that code has its own catalog entry or wiki page. Verified this directly before relying on it for a test scenario — it does **not** naturally exercise the `entity_not_found` degradation path, so that path is tested via a monkeypatched failure instead of a hunted-for natural example.
- `prerequisites`/`dependents` are explicitly documented as a **flattened, non-AND/OR-aware edge set** (same caveat `search_over_state` already carries about `has_prerequisite` edges) — the authoritative AND/OR structure is already present verbatim in `course.prerequisitesAst` (from the nested `get_entity` result), so this list is a convenience, never a substitute.
- `offeringPattern` carries its **own nested `certainty` sub-object** (`predicted_pattern` basis) rather than being merged into one top-level tag with `get_entity`'s `official_record`/`wiki_derived` certainty — forcing two structurally different certainty claims (a lookup vs. a prediction) into one tag would have been dishonest; the top-level `certainty` stays `get_entity`'s own (the core "this course exists" claim), matching how `search_over_state` already nests per-course `offeringCertainty` rather than trying to flatten everything into one number.

### `simulate_course_disruption(course_id, disruption_type, state, constraints)` — ✅ done

File: `tools/composites/simulate_course_disruption.py`. Tests: `tests/agent_core/tools/test_simulate_course_disruption.py` (13 cases, 100% line coverage). This is the flagship composite — it automates steps 2–5 of the fail-course-X worked example (AGENT_VISION §10) that the whole architecture was pressure-tested against.

- Composes `mutate_state` (1 or 2 calls, see below) + `traverse_relationship` (direct dependents) + `extract_temporal_pattern` (retake timing) + `search_over_state` **twice** — once on the untouched `state` (baseline plan), once on the disrupted state — so the caller gets a real before/after comparison in one call, not just a mutated state with nothing to compare it against.
- **A real correctness bug caught and fixed before it ever shipped, not left to the caller to discover**: `mutate_state.fail_course` never touches `plannedSemesters` by design (it only records `completedCourses` status). A course being "failed" while still sitting in `state.plannedSemesters[semester]` (i.e. currently in progress) would make `search_over_state._planned_course_numbers` wrongly treat it as already handled and never reschedule it. Fixed by **always** calling `drop_course` first (a safe no-op if the course wasn't planned there), then `fail_course` too when `disruption_type == "fail"` — never just one call for a failure.
- `additionalSemestersUsed` (the `impact` diff) is explicitly documented as an approximate proxy, not a precise "N-semester delay" claim — the baseline and disrupted plans satisfy slightly different required-course sets (the disrupted one has the extra work of retaking the disrupted course), so exactness isn't claimed; the full `baselinePlan`/`disruptedPlan` data is always included for anything that needs to be exact.
- The `compare_plans` idea from the original brainstorm is implemented as a private helper (`_diff_plans`) inline in this file rather than built as its own tool first — this composite needed it now, and a future standalone `compare_plans` tool can extract the same logic later without duplicating it (tracked in the status table above).
- Only a hard mutation failure or either `search_over_state` call failing is a hard failure (`mutation_failed`/`baseline_plan_failed`/`disrupted_plan_failed`); the supplementary facts (direct dependents, retake pattern) degrade gracefully via `warnings`, same pattern as `get_course_profile`.
- `certainty.basis` is always `hypothetical_simulation`, regardless of how confident the underlying sub-facts are — the defining characteristic of this composite's entire output is that it describes a hypothetical, never an official record. `confidence` is the minimum across the disrupted plan's own certainty and the retake-offering-pattern's certainty (when available).
- **Verified the full real scenario end to end before writing test assertions**, and caught my own test-setup mistake in the process: an early manual verification passed `semester` unset (defaulting to `state.currentSemesterCode`) instead of the semester the course was actually planned in, which silently dropped the course from the *wrong* `plannedSemesters` entry — a bug in my verification script, not the tool, but exactly the kind of mistake "verify against real data before writing assertions" exists to catch before it becomes a wrong test that passes for the wrong reason.

### `check_eligibility(course_id, state, target_semester)` — ✅ done

File: `tools/composites/check_eligibility.py`. Tests: `tests/agent_core/tools/test_check_eligibility.py` (12 cases, 100% line coverage).

- Exposes `AcademicGraphEngine.evaluate_eligibility` directly as its own callable — the one place that already gets AND/OR-aware prerequisite logic right, currently only reachable *inside* `search_over_state`'s multi-semester search. Deliberately **not** a partial reimplementation of `search_over_state`: this is a snapshot check against genuinely `status=="completed"` courses only, and does not credit merely-*planned* courses the way `search_over_state`'s multi-semester walk legitimately does. Documented explicitly in the file's own docstring so a future caller doesn't reach for this tool expecting multi-semester "will I be eligible after my planned courses are done" semantics.
- `target_semester` is optional and additive: when supplied (validated against the same `"YYYY-N"` format used elsewhere, `N∈{1,2,3}`), the tool also runs `extract_temporal_pattern(fact_type="course_offering")` and folds a `schedulable = eligible AND offered_this_term` verdict into the result — `schedulable` stays `null` when no `target_semester` was given, since the question wasn't asked. A missing/failed offering-pattern lookup degrades to `offeringPattern: null`, `schedulable: null` plus an `offering_pattern_unavailable` warning, never a hard failure — same graceful-degradation pattern as every other composite in this tier.
- **Real-data facts verified directly, not assumed, before writing test assertions**: course `00440148` requires `{00440105, 00440140}` (both, AND logic); course `00140008` has zero prerequisites and a reliable Winter(1)/Spring(2), never-Summer(3) offering pattern — reused from `test_search_over_state.py`'s own already-verified fixture data rather than re-deriving it.
- `certainty` is always `basis="official_record", confidence=1.0` at the top level — the eligibility check itself is a direct graph/state lookup, not a prediction; the separately-nested `offeringPattern.certainty` (when present) carries its own `predicted_pattern` basis, same nesting pattern `get_course_profile` already established for the same reason (a lookup and a prediction are different kinds of claim and shouldn't be flattened into one tag).
- A course explicitly marked `status="failed"` in `state.completedCourses` does **not** count as satisfying a prerequisite — verified with a real AND-logic scenario (`00440148` with one prerequisite `"completed"` and the other `"failed"`) to make sure the completed-set filter really does check `status=="completed"` and not just presence in the list.

### `get_track_requirements(track_slug)` — ✅ done

File: `tools/composites/get_track_requirements.py`. Tests: `tests/agent_core/tools/test_get_track_requirements.py` (4 cases, 100% line coverage).

- Composes `get_entity(entity_type="track")` + `traverse_relationship(relation="contains", direction="forward")`, filtered down to `nodeType=="course"` entries — bundles a track's own wiki page details with its graph-derived required-course list, since almost nothing that needs one of these skips straight to just the other.
- **Deliberately narrow about what `requiredCourses` means**: it reflects only what the graph can derive deterministically from a track page's `[[wikilinks]]` (`contains` edges) — credit minimums, elective-bucket rules, and other free-text requirement details live in the track's own wiki `content` (also returned here verbatim) and need a separate `interpret_text` call to extract. Same "structured facts here, free-text interpretation stays a separate step" split every other composite in this tier already follows.
- Only `get_entity` failing on the track itself is a hard failure (`track_not_found`); the `traverse_relationship` call failing degrades to `requiredCourses: []` plus a `required_courses_unavailable` warning rather than failing the whole call.
- **Real-data fact verified directly**: `track-materials-engineering` resolves to exactly 57 required courses via `contains` edges, including `01040019` — used as the success-path fixture. Also verified directly (by reading `get_entity.py`'s track-path code) that `entity_type="track"` never populates the envelope's `warnings` field at all (unlike the course path, which does) — so `track_result.warnings` propagating through is always `[]` in practice for this tool; not asserted as its own separate test case since it's implicitly covered by the success-path assertion already checking `result.warnings == []`.

### `compare_plans(plan_a, plan_b, focus_course_id)` — ✅ done

File: `tools/composites/compare_plans.py`. Tests: `tests/agent_core/tools/test_compare_plans.py` (6 cases, 100% line coverage).

- Extracted from `simulate_course_disruption.py`'s former private `_diff_plans` helper into its own first-class tool, per the status table's tracked follow-up. `simulate_course_disruption` now calls `run_compare_plans` itself instead of computing the diff inline — the two files no longer duplicate the same logic.
- **Deliberately generalized while extracting, not a verbatim lift**: the original private helper only handled the one shape `simulate_course_disruption` needed (baseline vs. disrupted, one course of interest). The standalone tool also surfaces `newlyScheduledCourses` (the reverse direction — a course unscheduled in `plan_a` that `plan_b` resolves), a case that never arises from a *disruption* (things only get worse) but is a real, useful comparison for two independently-produced plans in general (two track choices, two constraint sets, a genuine "did things get better" re-run). No new primitive calls either way — still a pure diff.
- Deliberately takes two already-computed `search_over_state`-shaped plan dicts as input, not two states it re-runs `search_over_state` on itself — keeps this tool a cheap, dependency-free diff, and lets any caller compare plans it already has on hand (e.g. from two separate `search_over_state` calls made for unrelated reasons) without this tool needing to know how those plans were produced.
- Validates both inputs carry the two required fields (`semestersUsed`, `unscheduledCourses`) before touching them — fails closed with `malformed_plan_a`/`malformed_plan_b: missing [...]` naming exactly what's missing, since the input is caller-supplied and not guaranteed to actually be `search_over_state` output.
- `certainty` is always `basis="official_record", confidence=1.0` — this tool performs one exact, deterministic computation over whatever two plans were handed to it (same classification `apply_deterministic_rule` uses for its own deterministic compute-tier operations); it's not a claim about how certain the plans *themselves* are, which stays whatever certainty the caller already has attached to them separately.
- `simulate_course_disruption`'s own test suite gained one new case (`test_plan_comparison_failure_propagates`) covering `compare_plans` failing — defensively handled (`plan_comparison_failed: ...`) even though real `search_over_state` output is always well-formed and this path isn't naturally reachable with real data.

### `audit_graduation_progress(track_slug, state, completion_rule, include_plan)` — ✅ done

File: `tools/composites/audit_graduation_progress.py`. Tests: `tests/agent_core/tools/test_audit_graduation_progress.py` (9 cases, 100% line coverage).

- Composes `get_track_requirements` (structural required-course list) + `apply_deterministic_rule` (the actual pass/fail determination) + optionally `search_over_state` (`include_plan=True`, projecting the remaining required courses onto a schedule).
- **Routes the completion check through `apply_deterministic_rule` rather than hand-rolling a comparison**, specifically so the default "100% of required courses done" bar is a caller-overridable `count_threshold` rule, not a hardcoded assumption — a caller can pass its own `completion_rule` for an earlier-progress check (e.g. "at least 40 of 57") using the exact same `requiredCourses: [{"courseNumber", "completed"}]` facts shape this tool documents and builds. This is the enumeration-mistake test applied directly: "graduation complete" and "made enough progress" are the same generic operation with a different threshold, not two different tools.
- `include_plan=True` reuses the track's required-course set via a `courses_required_by_track` constraint (the exact same `contains` traversal `get_track_requirements` already ran) rather than passing `remainingRequiredCourses` in as a `courses_required` list — lets `search_over_state`'s own already-correct `required - satisfied - alreadyPlanned` subtraction do the work instead of this tool duplicating that logic.
- **A real "nothing to do" case handled explicitly, not just naturally falling out of the plumbing**: when `remainingRequiredCourses` is already empty, `search_over_state` is never called at all — `projectedPlan`/`projectedPlanCertainty` stay `null`, distinct from a plan call that was attempted and failed (`graduation_plan_unavailable` warning only fires on an actual failed call). Verified directly with the real 100%-complete scenario.
- Deliberately **no credit-sum audit** (e.g. a 130-credit graduation minimum) bundled in here — that would need a `get_entity` call per required course just to build the facts list (dozens of extra calls for one composite invocation), which isn't worth the cost for this tool's specific job of tracking required-course completion. A caller that needs a credit-total check already has `apply_deterministic_rule` directly available, built from whatever credit facts it already has on hand — not a gap this tool needs to fill.
- Only `get_track_requirements` or `apply_deterministic_rule` failing is a hard failure (`track_requirements_failed`/`completion_rule_evaluation_failed`); the optional plan projection degrades via a `graduation_plan_unavailable` warning, and `get_track_requirements`'s own warnings (e.g. `required_courses_unavailable`) propagate straight through, same pattern as every other composite in this tier.
- `certainty` is always `basis="official_record", confidence=1.0` at the top level — the audit itself (which required courses are done, whether the rule is satisfied) is an exact computation over already-known facts; the separately-nested `projectedPlanCertainty` (when a plan was actually run) carries `search_over_state`'s own `predicted_pattern` basis, same nesting precedent `get_course_profile`/`check_eligibility` already established.
- **Real-data facts verified directly before writing assertions**: `track-materials-engineering` has 57 required courses; marking the first 10 completed yields `completedRequiredCourses` (10) / `remainingRequiredCourses` (47), an unsatisfied default rule (`count>=57` → `10 satisfied=False`), and (with `include_plan=True`) a real projected plan using 3 semesters with 37 courses still unscheduled at the default 8-semester bound, certainty `predicted_pattern`/`0.95`.

### `find_requirement_substitutes(course_id, track_slug, state, max_semesters)` — ✅ done

File: `tools/composites/find_requirement_substitutes.py`. Tests: `tests/agent_core/tools/test_find_requirement_substitutes.py` (8 cases, 100% line coverage). This was the one remaining tool blocked on real design work rather than pure implementation — **confirmed with the user before building**: given the graph has no explicit elective-bucket/substitutability structure (only 3 relations exist at all: `has_prerequisite`, `belongs_to`, `contains`), a "substitute" here means *structurally plausible*, not semantically verified — another course from the same track's required-course pool that's actually schedulable, never a claim that it fulfills the identical requirement line the original course was filling.

- **Required a schema change to `search_over_state` itself, not just a new composite**: added a new `objective="find_substitute"` and a paired `substitute_for` constraint (`{courseId, trackSlug}`) to `search_over_state`/`SEARCH_OVER_STATE_CONTRACT.md` — the contract doc had already anticipated exactly this ("a future objective that needs its own parameters ... should take them via a new constraint type"). `find_substitute` reuses `_minimize_semesters`'s entire forward-scheduling walk unchanged: the candidate pool (the track's `contains` list minus `courseId`) is simply substituted in as the "required" set, so eligibility/offering/credit-cap logic, certainty aggregation, and the plan/unscheduled output shape are all free reuse, not reimplemented. Validated: exactly one `substitute_for` constraint required when `objective="find_substitute"`, and rejected (`substitute_for_constraint_requires_find_substitute_objective`) when given with any other objective rather than silently ignored.
- The composite layer adds exactly what the primitive-level objective can't do itself: confirming `course_id` is actually a member of `track_slug`'s required pool before searching (`course_not_in_track`, a hard failure — substituting for a course that isn't even part of the track doesn't make sense), and flattening the resulting per-semester `plan` into one ranked, soonest-first `candidates` list (`[{courseNumber, semester, offeringCertainty}]`) rather than making every caller re-flatten a `{semester: [...]}` dict itself.
- **The limitation is stated in the tool's own output, not just in docs a caller might not read**: every successful response includes a static `note` field spelling out "not a semantic verification" directly in the data, mirrored in the `DESCRIPTOR` description text too — both places a caller/LLM could actually encounter before acting on a suggested substitute.
- Only `get_track_requirements` failing, `course_id` not being in the track, or the underlying `search_over_state` call failing are hard failures (`track_requirements_failed`/`course_not_in_track`/`substitute_search_failed`); `get_track_requirements`'s own warnings still propagate through, same pattern as every other composite in this tier.
- **Real-data facts verified directly before writing assertions**: substituting for `00350022` (confirmed a member of `track-materials-engineering`'s 57 required courses) yields 13 schedulable candidates within the default 8-semester bound — the first, `00350053`, landing in `2025-2` at `predicted_pattern`/`0.95` certainty — and 43 candidates still unscheduled; capping `max_semesters=1` narrows that to 9 schedulable candidates.

With this, all 7 originally brainstormed composites plus the `compare_plans` extraction are implemented and tested — the higher-level tools tier is complete for now.
