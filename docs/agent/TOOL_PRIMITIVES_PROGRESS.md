# Tool primitives implementation progress

Tracks implementation of the nine generic tool primitives from
[`AGENT_VISION.md` §5](AGENT_VISION.md) inside `services/ai/app/agent_core/`.

**Scope note:** this build ignores `services/agent/` entirely (the old,
shadow-only, fixed-observation-registry implementation retired per user
instruction). `services/ai/app/agent_core/` is a from-scratch rebuild of
`AGENT_VISION.md`, reusing ported code/concepts from `services/ai/app/`
(retrieval, graph engine, repositories, LLM adapter) where useful.

Code locations:
- Primitives: `services/ai/app/agent_core/tools/primitives/*.py`
- Registry: `services/ai/app/agent_core/tools/registry.py`, `default_registry.py`
- Tests: `services/ai/tests/agent_core/tools/`

---

## Status at a glance

| # | Primitive | Group | Status |
|---|-----------|-------|--------|
| 1 | `get_entity` | 1 — reads | ✅ Implemented + tested (100% line coverage) |
| 3 | `traverse_relationship` | 1 — reads | ✅ Implemented + tested (100% line coverage) |
| 2 | `search_knowledge` | 1 — reads | ✅ Implemented + tested (100% line coverage) |
| 7 | `mutate_state` | 2 — compute | ✅ Implemented + tested (100% line coverage) |
| 6 | `apply_deterministic_rule` | 2 — compute | ✅ Implemented + tested (100% line coverage) |
| 5 | `extract_temporal_pattern` | 2 — compute | ✅ Implemented + tested (100% line coverage) |
| 8 | `search_over_state` | 3 — search engine | ✅ Implemented + tested (100% line coverage; `minimize_semesters` objective only) |
| 4 | `interpret_text` | 4 — LLM-intrinsic | ✅ Implemented + tested (100% line coverage) |
| 9a | `compose_answer` | 4 — LLM-intrinsic | ✅ Implemented + tested (100% line coverage; standalone, not yet reconciled with `synthesis.compose_answer`) |
| 9b | `propose_action` | 5 — write | ✅ Implemented + tested (100% line coverage) |

**All 9 primitives are now implemented and tested, 100% line coverage
each.** Planned build order (dependency-driven, per the original plan) was
**Group 1 → 2 → 3 → 4 → 5** — followed exactly, all 5 groups done. Full
`services/ai` suite: 282 passed, 0 failures (as of Group 5 completion).

---

## Group 1 — pure reads, no LLM (✅ done)

### `get_entity(entity_type, entity_id)`

File: `tools/primitives/get_entity.py`. Tests: `tests/agent_core/tools/test_get_entity.py` (28 cases, 100% line coverage).

**Dispatch:**
- `entity_type in {course, track, program, minor, faculty, wiki_page}` → `AcademicGraphEngine` (via `app.retrieval.graph_engine.graph_registry.graph_registry`, the wiki + raw-offering-data graph — AGENT_VISION §2.1's sole academic source of truth). Originally implemented against `app.services.graph_registry` (a since-deleted duplicate engine); migrated to this one during the retrieval-model cleanup below — see that section for why.
- `entity_type in {student_profile, completed_courses, semester_plan}` → this service's own read-only Mongo repositories (`app/repositories/*`), via `app.db.mongo.get_database()`.

**Design decisions made (confirmed with user or grounded in real data — not guessed):**
- `entity_type` is a runtime-validated `str`, **not** a Pydantic `Literal`. Per §5's closing paragraph ("a new entity type ... is an additive change to the graph's schema — it never requires ... touching the orchestrator"), locking the vocabulary into the schema would defeat that extensibility.
- **Confirmed with user:** track/program/minor/faculty get their own `entity_type` values (not collapsed into one generic `wiki_page`); `wiki_page` is the deliberate catch-all for everything else (concepts, regulations, people, sources — anything with no dedicated structural classifier).
- **Found and worked around a real bug** in the ported `AcademicGraphEngine._classify_page`: it checks `rel_path.startswith("entities/faculty")` but the real directory is `entities/faculties/` (plural) — `"entities/faculties/x.md".startswith("entities/faculty")` is `False` (verified directly), so every real faculty page silently falls through to generic `"wiki"` in the engine's own classification. Rather than editing the shared engine (used elsewhere in retrieval), `get_entity` has its own local `_classify_wiki_path` helper with the corrected prefix.
- Added program/minor detection (`entities/programs/` dir, `program-`/`minor-` filename prefix — matches the convention `entity_slug_registry.py`'s `_slug_priority` already uses) that the engine does not classify at all today.
- `course` entities merge two independently-keyed representations that exist in the graph: the course-catalog node (keyed by 8-digit course code, from the raw per-semester Technion JSON — rich structured fields: name/credits/faculty/prerequisites/schedule/syllabus) and the wiki page (keyed by slug, e.g. `"00124507-chemistry-..."`, found via reverse lookup on `engine.slug_to_course_code`). Either one missing is a warning, not a failure; both missing is `entity_not_found`.
- Certainty basis: `official_record` for course-catalog-sourced data and all Mongo-backed types; `wiki_derived` for wiki-only content (tracks/programs/minors/faculty/wiki_page, or a course found only via its wiki page).
- Mongo documents are recursively sanitized (`ObjectId`→`str`, `datetime`→isoformat) before being placed in `ToolOutputEnvelope.data`, since raw Mongo types aren't JSON-safe.
- Every failure path (unknown `entity_type`, empty `entity_id`, not found, wiki `entity_type` requested but the slug is structurally a different kind, graph not configured, Mongo lookup exception) returns a distinct, fail-closed error — never a placeholder success.

**Verified-real test fixtures used** (greped/confirmed against the actual wiki tree, not assumed):
- Course `00440148` — has both a catalog entry and a wiki page (wiki slug `00440148-waves-distributed-systems`, verified via `engine.slug_to_course_code`), prereqs `00440105`/`00440140` (reused from the now-deleted `tests/test_academic_graph_engine.py`).
- Course `02080353` — in the active semester catalog with **no** matching wiki page (verified directly against the real engine, not guessed) — exercises the `course_not_in_active_semester_catalog`-is-absent / `no_wiki_page_found_for_course` warning path.
- Course `02360861` — has a wiki page but is **absent** from this semester's catalog JSON (same verification) — exercises the opposite one-sided-merge path.
- Track `track-biomedical-engineering`, program `program-alonim`, minor `minor-economics`, faculty `faculty-chemistry`, generic wiki page `student-rights`.
- `_classify_wiki_path`'s `courses/` branch and the "`entities/programs/` path with neither `minor-`/`program-` prefix" branch (no real file matches the latter — every file under `entities/programs/` uses one of the two prefixes, verified directly) are covered as direct pure-function unit tests rather than forced through fabricated wiki data.

### `traverse_relationship(entity, relation, direction)`

File: `tools/primitives/traverse_relationship.py`. Tests: `tests/agent_core/tools/test_traverse_relationship.py` (11 cases, 100% line coverage).

- `relation` validated at runtime against `_KNOWN_RELATIONS` — the **exact three** edge-relation labels `AcademicGraphEngine.build_graph()` actually writes: `has_prerequisite` (course → prerequisite course), `belongs_to` (course → track it wikilinks), `contains` (track page → course it wikilinks). No relation vocabulary was invented; these are the only ones that exist in the data today.
- `relation` is also a runtime-validated `str`, not `Literal`, same extensibility rationale as `entity_type`.
- `direction="backward"` on `has_prerequisite` answers "what does this course block" (the reverse-dependency need from the fail-course-X worked example, AGENT_VISION §10) for free — no dedicated tool needed.
- **Found a genuine asymmetry, not merged away:** `belongs_to` (course-side wikilink) and `contains` (track-side wikilink) are independently sourced from different documents and are *not* guaranteed consistent with each other — a track can `contains` a course without that course `belongs_to` it back, or vice versa. `traverse_relationship` exposes exactly what's in the graph rather than silently reconciling the two.
- Certainty basis is always `official_record`, confidence `1.0` — this is a deterministic graph walk over already-loaded structured data, no interpretation involved.

**Verified-real test fixtures used:**
- `02140093 --belongs_to--> track-education-biology` (course page's "Required in:" wikilink section).
- `track-materials-engineering --contains--> 01040019` (track page's course table wikilink).
- `00440148 --has_prerequisite--> 00440105, 00440140`.
- `00440148 --belongs_to (backward)-->` always structurally empty for any course entity — `belongs_to` edges only ever target a track slug (never a course code), so no course can have a `belongs_to`-labeled predecessor; used as a guaranteed-by-construction (not data-dependent) zero-match case for the backward direction.

### `search_knowledge(query, limit=5)`

File: `tools/primitives/search_knowledge.py`. Tests: `tests/agent_core/tools/test_search_knowledge.py` (9 cases, 100% line coverage).

- Thin wrapper over `AcademicGraphEngine.search_wiki()` (same engine as the other two) — BM25 always, plus embedding cosine similarity when `EMBEDDING_*` is configured; this environment has no `.env`/embedding key, so all tests here exercise the deterministic BM25-only fallback, no live network calls.
- **Zero matches is `ok=True`, not `ok=False`.** Unlike `get_entity`/`traverse_relationship` (where "not found" is a real failure), "nothing matched" is a legitimate, accurate search outcome — `error` stays reserved for genuine failure paths (bad input, graph unavailable, the underlying call raising). Callers detect "no matches" from an empty `data["matches"]` list.
- `limit` is a real input field (default 5, hard-clamped to `[1, 20]` regardless of what's requested) — not present on `get_entity`/`traverse_relationship` since neither of those returns a ranked, open-ended result set.
- `certainty.confidence` reuses `min(1.0, score / 10.0)` — the exact BM25-score-to-confidence heuristic the now-deleted `graph_retriever.py` used for `wiki_search` blocks, not a fresh invention. `certainty.source_ref` points at the top match's slug when any match exists, `None` otherwise.
- **Verified-real test fixtures** (ran `engine.search_wiki()` directly before writing assertions, not assumed): `"student rights ombudsman"` ranks the `student-rights` page/chunks highly. `"a b c"` deterministically tokenizes to nothing (`_tokenize_search` drops tokens shorter than 2 chars) — used as a guaranteed, corpus-independent zero-matches case, the same "verified by construction, not data-dependent" pattern used for `traverse_relationship`'s backward-`belongs_to` case above.

### Shared infrastructure decisions from Group 1 (apply to all future primitives)

- **Dependency access pattern:** primitives call `app.db.mongo.get_database()` / `app.retrieval.graph_engine.graph_registry.graph_registry.get_engine()` directly inside `run_*` — no change to `ToolCallable`'s signature (`Callable[[BaseModel], Awaitable[ToolOutputEnvelope]]`) or `subagents/tool_loop.py`'s call site. This matches the codebase's own established singleton-getter-with-test-override convention (`get_database()` + `set_test_database()`, `graph_registry.get_engine()`).
- **Test isolation for the graph:** don't touch `Settings`/env vars. Build a real `AcademicGraphEngine` once (session-scoped fixture) from the real wiki/catalog data on disk, then `monkeypatch.setattr(graph_registry, "get_engine"/"is_configured", ...)` to point the singleton at it for the duration of one test. Lives in `tests/agent_core/tools/conftest.py` as `real_academic_engine` / `use_real_academic_engine`. Skips (`pytest.skip`) when the real data isn't checked out locally.
- **Test isolation for Mongo:** `FakeDatabase`/`FakeCollection`/`FakeCursor` in the same `conftest.py` — a minimal in-memory double for exactly the Motor API surface the repositories use (`find_one`, `find().sort().skip().limit().to_list()`, `count_documents`). No `mongomock` dependency added.
- **Fail-closed is enforced everywhere:** every `run_*` wraps engine/DB access in `try/except Exception` and returns `ToolOutputEnvelope(ok=False, ...)` rather than raising — primitives must degrade gracefully even when called outside `subagents/tool_loop.py`'s own exception handling. **Every one of these `except` branches has a dedicated test** (`is_configured=True` + `get_engine` monkeypatched to raise → `academic_graph_unavailable`; a repository/`get_database` monkeypatched to raise → `mongo_lookup_failed`; `search_wiki` monkeypatched to raise → `search_failed`) — confirmed by driving each of the three primitive files to 100% line coverage individually.
- Pure helper functions with a branch real data can't reach (`get_entity._classify_wiki_path`'s `entities/programs/`-without-known-prefix case — verified no such file exists) are tested directly as unit tests on the function itself, not forced through fabricated wiki fixtures.
- `tests/agent_core/test_tools_registry.py`'s "every stub returns not_implemented" parametrized test now runs over `_STUB_TOOL_NAMES` (all 10 minus whichever are implemented) instead of all 10 — update this set every time a new primitive gets implemented.

---

## Retrieval-model cleanup (done, between Group 1 and Group 2)

While scoping `search_knowledge`, discovered `services/ai` actually had **two
parallel, non-identical retrieval stacks** — not one. Per explicit user
instruction, deleted the older/duplicate one and every genuinely-dead legacy
module, and stripped the old fixed-intent-enum coupling out of what remained,
so there is now exactly one retrieval engine for `agent_core` to build on.

**What existed before:**
- **Stack A** (`app/services/*` — `academic_graph_engine.py`, `graph_registry.py`, `graph_tools.py`, `advisor_agent.py`, `semester_catalog.py`) — the original, simpler `services/ai` engine. `search_wiki()` was plain keyword/token-overlap matching. Live via `POST /retrieve`/`POST /advise`/`POST /infer` (`app/routes/advisor.py`), which `services/api`'s own `/advisor` route (`ai_advisor_client.ask_advisor()`) actually called — a real cross-service dependency, confirmed before deleting anything.
- **Stack B** (`app/retrieval/graph_engine/*` — richer `academic_graph_engine.py` with a real BM25 + optional-embeddings `search_wiki()` via `obsidian_wiki_indexer`/`reranker`/`wiki_vector_index`) — ported from `services/agent`'s retrieval layer, marked in its own docstring as "Primary agent retrieval... replaces legacy hybrid RAG," but not wired into any live route and not yet used by `agent_core`.
- `app/retrieval/hybrid_wiki_retriever.py` — explicitly marked `LEGACY` in its own docstring, no real importer anywhere; the module `reranker.py` was originally built for, superseded by Stack B's engine absorbing the same reranker/chunk pipeline directly.
- `app/retrieval/graph_retriever.py` (Stack B's own top-level wrapper) + `app/retrieval/intent_types.py` (`AgentIntent`) — an intent-driven retrieval *planner* (`plan_graph_retrieval_actions`), not a generic search function; exactly the fixed-intent-enum shape AGENT_VISION §5 rejects.
- `app/retrieval/profiles.py` had intent-coupled functions (`select_profiles_for_intent`, `primary_profile_for_intent`, `intent_omits_student_profile`, `WIKI_ONLY_INTENTS`) alongside its generic profile-config machinery.

**What was done:**
- **Deleted Stack A entirely**, plus `app/routes/advisor.py`, `app/schemas/advisor.py`, and the now-empty `app/services/`/`app/schemas/` packages. `app/main.py`/`app/routes/health.py` migrated to Stack B's `graph_registry`. User explicitly accepted this breaks `services/api`'s `/advisor` route until `agent_core` is wired up to replace it (stated intent: "implement the whole new AGENT_VISION and then wire it up to the app instead of advisor.py").
- **Deleted `hybrid_wiki_retriever.py`** (confirmed dead).
- **Deleted `graph_retriever.py` and `intent_types.py`** — the only non-intent-coupled thing in `graph_retriever.py`, `warmup_graph_engine()`, was moved as-is into `app/retrieval/graph_engine/graph_registry.py`; `app/retrieval/cache_warmup.py` and `app/retrieval/__init__.py` updated to import it from there.
- **Stripped the intent-coupled functions out of `profiles.py`**, kept the generic profile-config machinery (`RetrievalProfile`, `get_profile`, `get_rerank_boosts`, `profile_allows_*`, `estimate_context_tokens`) — Stack B's own `search_wiki()` depends on `get_profile("fallback_academic_search")` internally, so `profiles.py` itself is not legacy.
- **Migrated `get_entity.py`/`traverse_relationship.py`** (and their tests/`conftest.py`) from Stack A's `graph_registry`/`academic_graph_engine` imports to Stack B's — pure import-path changes; the graph-building logic (node/edge shapes, the faculty-directory classification bug both copies shared) is identical between the two, so no other Group 1 logic changed.
- **Tests:** deleted `test_academic_graph_engine.py`, `test_advisor_agent.py`, `test_graph_retriever.py`, and 4 more files that directly tested the now-deleted `hybrid_wiki_retriever.retrieve_wiki_context_with_profile` (`test_catalog_requirement_retrieval.py`, `test_course_exact_lookup.py`, `test_rag_regression_extras.py`, `test_requirement_entity_ranking.py` — 551 lines of real regression coverage lost with no direct replacement; flagged below). `test_semester_catalog.py` was migrated rather than deleted (Stack A/B copies were byte-identical, and it was the only direct unit coverage `graph_engine/semester_catalog.py` had). `test_rag_profiles.py`/`test_api_routes.py` trimmed to drop only the intent-coupled/deleted-route cases.
- Full suite verified green after cleanup: **123 passed** (15 `live`-marked deselected), no other stale references found (`grep` swept for `app.services.`, `app.retrieval.graph_retriever`, `app.retrieval.intent_types`, `app.retrieval.hybrid_wiki_retriever`, `app.routes.advisor`, `AgentIntent`).

**Known gap, partially closed:** the 4 deleted `hybrid_wiki_retriever`-testing files had real regression coverage (exact-course-number lookup, requirement-entity ranking, mixed-language queries, metadata relaxation fallback) that had no equivalent against Stack B's `AcademicGraphEngine.search_wiki()` at the time. `search_knowledge`'s own tests (above) now cover `search_wiki()` at the tool-contract level (ranked results, zero-match handling, exceptions) with 100% line coverage of the primitive itself, but do **not** re-create the deleted files' scenario-specific regression cases (exact-course-number-wins-over-mentioned-prereq, mixed-language query ranking, metadata relaxation fallback) — still an open gap if that specific regression coverage is ever needed again.

---

## Group 2 — pure compute, no LLM (✅ done)

### `mutate_state(base_state, change)` — ✅ done

File: `tools/primitives/mutate_state.py`. Tests: `tests/agent_core/tools/test_mutate_state.py` (26 cases, 100% line coverage).

**No `base_state`/student-simulation-state shape existed anywhere in the codebase before this** — `get_entity` returns raw records, nothing assembles them into one simulate-able object. Defined the shape fresh, **confirmed with the user first**, and wrote it up as its own living contract doc: [`SIMULATION_STATE_CONTRACT.md`](SIMULATION_STATE_CONTRACT.md) — the single source of truth for `base_state`'s keys and the `change["type"]` vocabulary, since Group 3's `search_over_state` will consume the same shape. **Update that doc, not just this one, whenever the shape or vocabulary changes.**

Key decisions (all written up in the contract doc, summarized here):
- `change` is one dict carrying its own discriminator (`change["type"]`), not a separate input field — matches AGENT_VISION §5's literal `mutate_state(base_state, change)` signature without adding a field.
- `change["type"]` is a runtime-validated `str`, not `Literal` — same extensibility rationale as `entity_type`/`relation`.
- 5 change types implemented, matching AGENT_VISION's own description verbatim: `fail_course`, `drop_course`, `retake_course`, `delay_semester`, `change_track`.
- `delay_semester` reuses the exact `"YYYY-N"` (N∈{1,2,3}) semester-code format `app.retrieval.graph_engine.semester_catalog` already produces elsewhere in this codebase — not a new format invented here. Wrap-around arithmetic (`Summer 2025 + 1 → Winter 2026`) verified by hand before writing tests.
- **Immutability enforced twice over**: `base_state` is deep-copied once at the top of `run_mutate_state`, and every handler still builds fresh dicts/lists for the keys it touches rather than mutating the copy in place — belt-and-braces, per this repo's "never mutate, always return a new object" rule. A dedicated test (`test_base_state_is_never_mutated_in_place`) asserts the caller's original dict is byte-for-byte unchanged after the call.
- `count: bool` is explicitly rejected for `delay_semester` — `isinstance(True, int)` is `True` in Python, which would otherwise silently treat a boolean as `count=1`.
- Certainty basis is always `hypothetical_simulation` (the one `CertaintyBasis` value no other Group 1/2 primitive has used yet) — a mutated state is by definition not an official record or a wiki fact.
- Every handler fails closed on a missing required field (never applies a partial/guessed change) and the dispatcher fails closed on an empty/unknown `change["type"]`.

### `apply_deterministic_rule(rule, facts)` — ✅ done

File: `tools/primitives/apply_deterministic_rule.py`. Tests: `tests/agent_core/tools/test_apply_deterministic_rule.py` (36 cases, 100% line coverage).

Same pattern as `mutate_state`: no `rule` shape existed anywhere in the codebase, so it's defined fresh in its own contract doc — [`DETERMINISTIC_RULE_CONTRACT.md`](DETERMINISTIC_RULE_CONTRACT.md), the single source of truth for `rule["type"]`'s vocabulary. **Update that doc, not just this one, whenever the vocabulary changes.**

Key decisions (written up in the contract doc, summarized here):
- Three rule types, not a general expression language, matching AGENT_VISION's own named examples: `sum_threshold` (credit totals), `count_threshold` (e.g. "at least N courses in bucket X"), `field_comparison` (single scalar checks like GPA).
- **The fail-closed distinction the contract doc calls out explicitly**: a `facts` key the rule references being entirely **absent** is `ok=False` (`facts_source_missing`) — "we don't have this data"; the same key present as an **empty list** is a real, computable answer (sum is legitimately `0`) — `ok=True`. Both are tested (`test_sum_threshold_missing_facts_source_fails_closed` vs `test_sum_threshold_empty_facts_source_is_a_real_zero_not_a_failure`), since collapsing them into one behavior is exactly the "placeholder trusted as real content" failure mode AGENT_VISION's data-architecture section (§2.2) warns about.
- A matched record whose field isn't numeric fails closed (`non_numeric_field_value`) rather than being skipped or coerced — including the `bool`-is-a-`Number`-in-Python trap (`isinstance(True, numbers.Number)` is `True`), explicitly rejected via a dedicated `_is_number` helper, with a test proving `{"passed": True}` doesn't silently sum as `1`.
- `certainty.basis` is always `official_record` — this primitive only computes over facts it's handed; it introduces no new uncertainty, so tracking the *facts'* own certainty is the caller's job, not this primitive's.
- All 6 comparators (`>=, >, <=, <, ==, !=`) have a dedicated parametrized correctness test — not just line coverage, since a wrong comparator implementation wouldn't show up as a coverage gap.

### `extract_temporal_pattern(fact_type, entity)` — ✅ done

File: `tools/primitives/extract_temporal_pattern.py`. Tests: `tests/agent_core/tools/test_extract_temporal_pattern.py` (16 cases, 100% line coverage).

Same fresh-contract pattern as the other two Group 2 primitives, plus a real design conversation (confirmed with the user) since there was zero prior art and zero way to validate a formula. Full design in [`TEMPORAL_PATTERN_CONTRACT.md`](TEMPORAL_PATTERN_CONTRACT.md).

- **Data-availability finding that shaped the whole design**: `AcademicGraphEngine` only ever loads one semester's catalog at a time (`course_catalog` is replaced wholesale on each `load_semester_catalog` call) — mining a real history required reading every raw semester JSON file independently via `semester_catalog.discover_semester_catalogs`, bypassing the engine entirely for this primitive. Checked the raw data directory before designing anything: **7 real semester files exist** (`2023_201`, `2024_{200,201,202}`, `2025_{200,201,202}`) — 2 Winters, 3 Springs, 2 Summers — not the single semester every other primitive assumes.
- **Confirmed with user**: per-term-type classification into exactly 3 buckets (`reliable` = ratio 1.0, `never` = ratio 0.0, `irregular` = anything between) from the *exact* observed/total ratio — no invented percentage threshold, since 2–3 samples per term-type would make a threshold like "≥75%" statistically meaningless.
- **Confirmed with user**: `certainty.confidence = min(0.95, 0.5 + 0.1 × totalSemestersInHistory)` — explicitly documented as an invented heuristic with no ground truth to validate against, never reaching `1.0` since `certainty.basis` is always `predicted_pattern` (a prediction, never an observed fact).
- Output is structured per-term-type data, never a pre-baked English sentence ("usually offered in Winter...") — composing that into prose is Composition's job (§4), not this primitive's.
- A course that never appears in any discovered file is still `ok=True` (all buckets `"never"`) — mining a history is this primitive's whole job; whether the entity is a *real* course is `get_entity`'s concern. The one real failure is zero discoverable semester files at all (`insufficient_history`).
- **Every bucket verified against real courses before writing test assertions**, not fabricated: `00440148` (offered all 7/7 → reliable every term), `00440105` (reliable Winter+Spring, never Summer), `03180530` (the one real course found with a genuinely partial ratio: 1 of 2 Winters, 0 elsewhere → `irregular`), `99999999` (a nonexistent course code → never everywhere).

## Group 3 — constraint-search engine (✅ done)

### `search_over_state(state, constraints, objective)`

File: `tools/primitives/search_over_state.py`. Tests: `tests/agent_core/tools/test_search_over_state.py` (32 cases, 100% line coverage). Full design in [`SEARCH_OVER_STATE_CONTRACT.md`](SEARCH_OVER_STATE_CONTRACT.md).

**The design went through a real correction, not just a confirmation.** The first draft baked one scenario (track-completion planning) directly into fixed named fields (`trackSlug`, `maxCreditsPerSemester`) — the user caught this as exactly the enumeration mistake AGENT_VISION §5 warns against, since it wouldn't generalize to what-if simulation or requirement-substitute search with a different constraint/objective shape. Corrected to the same typed-vocabulary pattern as `mutate_state`/`apply_deterministic_rule`:

- `constraints` is a `list[dict]`, each entry independently typed (`courses_required`, `courses_required_by_track`, `max_credits_per_semester`, `max_semesters`) — additive vocabulary, not fixed fields.
- `objective` stays a plain `str` discriminator; v1 implements only `"minimize_semesters"`. **User explicitly signed off on implementing just this one objective now, testing it, then adding others later** (`check_feasibility`, `find_substitute` for requirement-substitute search) rather than building all of them up front.
- **Confirmed with user**: this primitive is fully standalone — zero code dependency on `interpret_text` (Group 4, not yet built) or any other not-yet-built primitive. It composes only already-implemented primitives (`get_entity`, `traverse_relationship`, `extract_temporal_pattern`) plus one engine method called directly.

**Implementation composes rather than duplicates**: calls `run_get_entity`/`run_traverse_relationship`/`run_extract_temporal_pattern` directly (one source of truth for graph/history access, matching the "sourcing fragmentation" warning in AGENT_VISION §2.2), and reuses `mutate_state._advance_semester_code` for semester arithmetic rather than reimplementing it a second time.

**A genuine correctness finding, not a design preference**: prerequisite checking uses `AcademicGraphEngine.evaluate_eligibility` directly, *not* `traverse_relationship`'s `has_prerequisite` edges — `build_graph()` flattens an OR-prerequisite AST into one flat edge set per course (confirmed by reading `_collect_course_ids`), which would incorrectly require every alternative in an OR clause rather than just one. `evaluate_eligibility` is the one place in the codebase that already gets AND/OR right; reusing it avoids reintroducing a bug that already exists elsewhere in the graph's edge model.

**Other decisions:**
- A missing/failed `extract_temporal_pattern` result never blocks scheduling — only a positive `"never"` bucket excludes a term; a *missing* prediction is tagged with `confidence=0.0` and left schedulable, since "we don't know" isn't the same as "we know it won't happen."
- Every required course is accounted for in exactly one of `satisfiedCourses`, `alreadyPlannedCourses`, `plan`, or `unscheduledCourses` — a real gap caught during testing (an already-planned-but-not-yet-completed required course was silently disappearing from the output before `alreadyPlannedCourses` was added).
- An exhausted search (`max_semesters` reached with courses still unscheduled) is `ok=True` with a populated `unscheduledCourses` list — a partial plan is still useful output, not a failure.
- `ToolOutputEnvelope.certainty` is the minimum-confidence entry across every scheduled course (a conservative aggregate — one weak link determines trust in the whole plan).

**Every branch — including the tricky ones — verified against real data before writing assertions, not fabricated**: found and fixed a filter bug in my own sanity-checking script along the way (checking for a truthy `"operands"` key false-matched single-course prerequisite ASTs, which have no `"operands"` key at all — only the true `{"type": "AND", "operands": []}` shape means "no prerequisites"). Real verified fixtures used: course `00440148` (needs `00440105`+`00440140`, reliable every term); course `00140008` (zero prerequisites, 3 credits, reliable Winter/Spring, **never** Summer — used to prove the offering-exclusion logic against a real "never" bucket, not a synthetic one); track `track-materials-engineering` → `01040019` via `contains`.

**Known limitation (not fixed, out of scope for this primitive)**: `AcademicGraphEngine` only has one semester's catalog loaded as its "active" graph at a time — a course entirely absent from that snapshot (e.g. only ever offered in a past semester no longer active) gets treated as prerequisite-free/zero-credit by `evaluate_eligibility`'s own pre-existing default-empty-AST behavior, not something `search_over_state` introduced or can fix without changing the engine's architecture.

## Group 4 — LLM-intrinsic primitives (✅ done)

Both follow `request_understanding.py`'s `BaseReasoningBlock` pattern (single-shot, no tools, schema-validate-then-repair), each with its own `PromptContract` defined inline in its own primitive file (not a separate `schemas.py` module, matching the file-per-primitive convention every other primitive uses).

### `interpret_text(source, question)`

File: `tools/primitives/interpret_text.py`. Tests: `tests/agent_core/tools/test_interpret_text.py` (13 cases, 100% line coverage).

- `source` is treated as a wiki slug, fetched via `get_entity(entity_type="wiki_page", entity_id=source)` — the generic wiki-entity catch-all already proven in Group 1/3 — rather than inventing a new data-access path. Composes an existing primitive rather than duplicating graph/content access, same discipline as `search_over_state`.
- **The one deliberate, confirmed-with-user behavioral difference from `request_understanding.py`**: fails *closed*, not open. `request_understanding.py` always falls back to a usable default (a turn must never be blocked); `interpret_text` must return `ok=False` on every failure path — source not found, LLM unavailable, schema never becomes valid, *or* the LLM's own `status="cannot_determine"` verdict, *or* a schema-valid-but-hollow `"determined"` verdict with no real citation (schema validation alone can't express "cited_section required when status='determined'", so this is checked explicitly, same pattern as `request_understanding.py`'s own hollow-result check).
- Wiki content is capped at `_MAX_SOURCE_CHARS` (6000) before being sent to the LLM — a defensive token-budget bound, not a new contract decision.
- **A real infrastructure finding surfaced while testing**: `_normalize_result` (shared by every `BaseReasoningBlock` subclass) substitutes a blank *required* string field with a documented placeholder (`GENERIC_BLANK_FIELD_PLACEHOLDER = "unknown"`) before schema validation runs — this doesn't affect `interpret_text` (its `answer`/`cited_section` fields are nullable `["string", "null"]`, not plain `"string"`, so the placeholder-fill is skipped), but discovering this here is what caught the bug described below in `compose_answer`.
- The Python-level `confidence` clamp/non-numeric-fallback in `_to_output` is defensive-in-depth, not reachable via a normal LLM response (the JSON schema itself already bounds `confidence` to `[0, 1]` and type-checks it, so an out-of-range/non-numeric value gets caught by schema validation first) — tested by calling `_to_output` directly rather than asserting a fake LLM response can reach it end to end.

### `compose_answer(facts_with_certainty)`

File: `tools/primitives/compose_answer.py`. Tests: `tests/agent_core/tools/test_compose_answer.py` (15 cases, 100% line coverage).

**Implemented standalone, per explicit user instruction — does NOT reuse or modify `agent_core.synthesis.synthesis.compose_answer`.** That function already exists and runs the "Composition" role via the full subagent/role machinery (`run_subagent`, `roles/prompts.py`'s `COMPOSITION_AGENT_V1` contract, real `StateEntry` objects) — reusing it would have required either adding a `user_goal` field to this primitive's input (a real schema deviation from AGENT_VISION's literal one-argument signature) or synthesizing fake `StateEntry` objects from loose fact dicts. The user explicitly deferred that reconciliation to when the subagent/role layer itself gets wired up, so this primitive has its own self-contained `BaseReasoningBlock` shape and its own fact-shape contract instead:
- Each `facts_with_certainty` entry must carry `data: dict` and `certainty` (validated as a real `CertaintyTag` — basis must be one of the 5 known values, confidence in `[0, 1]`) — a fact with no certainty tag is refused (`fact_N_missing_or_invalid_certainty`), never given a guessed one, since that would defeat the primitive's entire purpose.
- Reused `roles/prompts.py`'s `COMPOSITION_AGENT_V1` prose (already well-written and exactly matches this job) as inspiration for this primitive's own prompt contract, without importing that module or its code — content reuse, not a code dependency, consistent with staying standalone.
- `ToolOutputEnvelope.certainty` aggregates all input facts: minimum confidence (one weak link bounds trust in the composed prose, same pattern as `search_over_state`), basis stays the shared value if every fact used the same one, else falls back to `"llm_interpretation"` (the composition itself is an LLM-synthesis act layered on top of whatever the underlying facts were).
- **Bug found and fixed via testing, not by inspection**: the first version's blank-`answer_text` check (`if not answer_text.strip()`) never actually fired, because `_normalize_result`'s shared blank-required-string-field substitution (see `interpret_text` above) had already replaced the blank string with `"unknown"` before this code ever saw it. Fixed by also checking `answer_text == GENERIC_BLANK_FIELD_PLACEHOLDER` explicitly — the same convention `result_normalizer.py`'s own docstring already documents ("any caller ... must treat an exact match against this constant the same as 'no usable answer'"), not a new rule invented here.
- Fails closed like `interpret_text` (a malformed fact, unavailable LLM, or schema/repair failure all return `ok=False`) — a defensible conservative default for this primitive even though §5.1 only names `apply_deterministic_rule`/`interpret_text` explicitly as needing this.

## Group 5 — the one write primitive (✅ done)

### `propose_action(action_type, payload)`

File: `tools/primitives/propose_action.py`. New repository: `app/repositories/agent_action_proposal_repository.py`. Tests: `tests/agent_core/tools/test_propose_action.py` (8 cases, 100% line coverage on both files).

- **New collection, new repository, both built fresh** — `agent_action_proposals`, named directly from AGENT_VISION §2.1's own text ("agent_clarification_states (and the rest of the agent's own conversation/audit trail — runs, steps, tool calls, action proposals)"), not ported from the retired `services/agent`. This is the **first write-capable repository** in `services/ai` — every other repository (`student_profile_repository.py`, `completed_course_repository.py`, `semester_plan_repository.py`) is deliberately read-only by its own docstring ("this service never writes to shared student-state collections"). Writing here doesn't violate that rule: `agent_action_proposals` is the agent's *own* operational collection, not a shared student-state one.
- **`action_type` is deliberately the one vocabulary-shaped field in the whole primitive set that gets zero runtime validation.** Every other primitive's vocabulary field (`entity_type`, `relation`, `change["type"]`, `rule["type"]`, `fact_type`, constraint `type`s) gates real per-type dispatch logic inside that primitive. `propose_action` never branches on `action_type` at all — it always does exactly one thing (persist a `status="pending"` record) regardless of what's being proposed. There is nothing to validate against a known set, so nothing is; the caller owns the meaning of `action_type`/`payload`, this primitive only owns durably recording the proposal.
- Extended the shared `FakeDatabase` test double (`tests/agent_core/tools/conftest.py`) with `insert_one` support (a real `_FakeInsertOneResult.inserted_id`) — every other primitive's tests only ever needed read operations (`find_one`/`find`/`count_documents`) on it before this.
- `certainty.basis="official_record"`, `confidence=1.0` always — once the write succeeds, the proposal's *existence* is an unambiguous fact, not a prediction or interpretation.
- Fails closed on a missing `action_type` or any database exception (`proposal_creation_failed: <exc>`) — consistent with every other primitive's contract.

**Deliberately out of scope for this primitive** (matches §5.1's "always proposal-only, never a direct mutation" boundary): confirming/rejecting a proposal, and actually executing the underlying write it describes — both stay future `api`/`web`-level work, exactly like the retired `services/agent` design kept the real write inside `api`'s own confirm/reject routes rather than in the agent itself.
