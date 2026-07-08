# UniPilot Agent — target vision

**This document describes where the agent system is meant to go, not what exists in the codebase today.** For the current, phase-by-phase implementation state, see [`CURRENT_STATE.md`](CURRENT_STATE.md) and [`docs/architecture/agent-orchestration-architecture.md`](../architecture/agent-orchestration-architecture.md). Where this vision and the current implementation diverge, this document wins for direction; `CURRENT_STATE.md` wins for what is actually true right now.

The vision below was arrived at through direct, adversarial design discussion — each design choice was pressure-tested against concrete counterexamples (most importantly, "what happens if I fail course X this semester?") until it either held up or was revised. It is recorded here in that spirit: not just conclusions, but the reasoning and the traps each conclusion was chosen to avoid, so a future reader can tell the difference between "this is arbitrary" and "this is load-bearing."

---

## 1. The problem this architecture exists to solve

The system must be able to answer **any** in-scope academic question a Technion student could ask — not a fixed menu of pre-imagined intents. Two earlier approaches to that goal were tried and explicitly rejected, and the rejection reasons are the foundation everything else is built on:

1. **A fixed intent-enum + one hardcoded workflow per intent.** This only ever covers the intents someone thought to enumerate in advance. A student can ask about anything within the domain's scope, phrased any way, combining any number of academic concerns in one question — a fixed enum is structurally incapable of covering that, no matter how many intents get added to it.

2. **Deterministic, hand-written rule engines parsing the catalog wiki** (the `api` service's existing approach: parse `.md` catalog pages with regex/rules into Mongo collections, then compute against those). This was rejected because *"understand what applies to this student, in this faculty, on this academic path, per the wiki text"* is a **language-comprehension problem** — exactly what an LLM with strong reasoning is good at, and exactly what a hand-written rules engine is bad at, because a rules engine has to enumerate every faculty, path, and edge case in advance. That's a complex task that is likely to have bugs and gaps with a deterministic approach, and it is squarely the kind of problem this system's whole reason for existing (state-of-the-art AI reasoning) should be able to handle.

Both rejections point at the same underlying principle: **anywhere the system tried to pre-enumerate the shape of a problem — intents, tools, or roles — it broke the first time reality didn't match the enumeration.** Every subsequent design decision in this document is, in one way or another, an application of that lesson: push the boundary of what must be decided in advance as far down as possible, and let reasoning (Planner, Orchestrator, subagents) handle everything above that boundary dynamically, per request.

---

## 2. Data architecture and source of truth

### 2.1 The decision

**The source of truth for all academic knowledge is the catalog wiki (markdown corpus) and the raw Technion offering data.** MongoDB is used **only** for user-specific / operational data:

- `student_profiles` — degree program, track, catalog year, current semester, preferences
- `users` — account/auth records
- `completed_courses` — per-student completed-course records (course, semester, grade)
- `semester_plans` — saved/generated semester schedules
- `agent_clarification_states` (and the rest of the agent's own conversation/audit trail — runs, steps, tool calls, action proposals) — the agent's own operational state, not academic knowledge

No academic fact (course data, requirements, prerequisites, catalog rules) has a Mongo copy. Today's `courses`, `degree_requirements`, `course_offerings`, `catalog_rules`, `catalog_path_options`, `catalog_faculties` collections — and every deterministic engine that currently reads from them (the graduation-audit engine, the requirement-contribution engine, the catalog repository) — are retired as sources of academic truth and re-pointed at the wiki + raw offering data directly. This is a real migration, not a config flag.

### 2.2 Why: killing sourcing fragmentation

Before this decision, the same academic fact often existed as 2–3 independent copies that could silently drift apart:

- Course/prerequisite data existed as three independent representations: the Mongo `courses`/`degree_requirements` collections, the raw per-semester Technion JSON, and the retrieval graph's own course-catalog structure (built only from the raw JSON, never from Mongo).
- Eligibility/prerequisite checking existed as at least two independently-written implementations (a graph traversal, and a separate audit-engine implementation) with nothing guaranteeing they agree — for a system whose core promise is factual reliability, two unsynchronized implementations of "is this student eligible" was the single biggest reliability risk in the old design.
- Prerequisite parsing was a bespoke regex parser over raw Hebrew strings that failed *closed* in a way that looked like success (a malformed string silently became "no prerequisites" instead of flagging incompleteness) — the same "placeholder trusted as real content" failure mode that recurs throughout systems like this, not a one-off bug.
- Wiki content and structured catalog data were never reliably cross-linked, so retrieval quality varied unevenly per course/track.

The fix: **one authoritative source per fact type**, with every other layer (graph, embeddings, computed engines) treated as a *view* over it, never an independent parallel copy.

### 2.3 Handling future semesters — prediction, not assertion

The system does not have access to future semester offerings (they aren't published yet) — only the current semester and previous semesters. This is not a data-layer limitation to work around by "holding more semesters" in the graph; **there is no ground truth for future semesters, so the system must infer one.**

The raw Technion offering JSON files go back several years. For a given course, its offering history per term-type (Winter/Spring/Summer) can be mined for a pattern — reliably-Winter, reliably-Spring, both, irregular, or summer-and-vote-dependent — and that pattern used to **predict** (never assert) whether the course will run in a future target semester. This is a genuinely new capability: nothing in the old design mined the historical raw files for a pattern across time; it only ever loaded one semester's snapshot as ground truth.

This distinction is load-bearing for grounding: a predicted future offering is categorically different from a published one, and must be surfaced to the user as an inference with an explicit confidence/pattern basis ("offered every Winter for the last 3 years" vs. "summer offerings depend on student vote, historically inconsistent") — never phrased as a fact the way a published offering is.

### 2.4 One narrow, deliberate exception: cached interpretation

Re-running an LLM interpretation of "what's the retake limit" (for example) on every single relevant request is correct but wasteful; hardcoding it once (the old `api` approach) is exactly what this architecture moves away from. The resolution is a **materialized, versioned cache of derived interpretations** — keyed to the source wiki content's hash, automatically invalidated and re-derived when the wiki text actually changes, always fully traceable back to which page/section and which reasoning path produced it (mirroring how the wiki embeddings index is already cached and rebuilt).

This does **not** violate the wiki-is-the-only-authority rule: it is the agent's own **derived operational state** — the same category as its own run/step/audit records — not a competing source of academic truth. It belongs in the agent's own Mongo collections, rebuildable at any time from the wiki, never a thing anyone edits directly.

---

## 3. High-level architecture

```
User request
     │
     ▼
Request Understanding (LLM)          -- turns the raw prompt into a goal
     │
     ▼
Planner (LLM)                        -- decomposes into an adaptive set of steps
     │
     ▼
Orchestrator                          -- executes the plan step by step, manages
     │   (per step, repeated)             everything; does not do the work itself
     ├─► step-prep pass (LLM, small)  -- decides what this one step needs
     ├─► prompt_builder               -- renders the step's structured decision into
     │                                    natural-language instructions
     ├─► context_builder               -- assembles a bounded, step-scoped context
     │                                    package (rendered prompt + structured
     │                                    context, as mutual anchors)
     ├─► subagent_builder               -- assembles a subagent instance from the
     │                                    fixed specialist roster + reasoning-block
     │                                    tuning for this step
     ├─► subagent runs                  -- reasons, may call tools, returns a
     │                                    schema-validated, certainty-tagged result
     ├─► result appended to shared      -- shared plan-execution state (working
     │   plan-execution state               memory) accumulates across the whole plan
     └─► Monitor                        -- checks the result against the plan's own
                                            stated assumptions/success criteria;
                                            decides continue / replan / clarify
     │
     ▼  (once the Planner judges the plan complete)
Synthesis / Composition (LLM)         -- produces the final answer from accumulated,
                                          certainty-tagged state — never re-derives
                                          numbers itself
     │
     ▼
Response to user
```

The Orchestrator's job is explicitly **delegation and management, not execution** — "a smart and good orchestrator does not do the actual work, it delegates, and manages the subagents workforce."

### 3.1 Plans are adaptive, not fully-formed upfront

Replanning is not an error-recovery fallback; for genuinely investigative requests, it is **the primary control loop.** A plan cannot always be fully specified before execution starts, because later steps' necessity or shape often depends on what earlier steps discover. (Concretely: whether a course's failure is even final yet determines whether "what does this block" is even the right next question; how long a course won't be offered again determines how many downstream semesters need re-examining — none of that is knowable until earlier steps return.) The Planner plans a few steps, lets them execute, looks at what was actually discovered, and plans the next chunk — repeatedly, not once.

### 3.2 Certainty is a first-class, structural property

Every result that flows through the shared plan-execution state carries an explicit certainty/basis tag (source, confidence, and — for anything interpretation-derived — which wiki page/section and reasoning path produced it), generalizing the existing "distinguish official records vs. assumptions vs. suggestions" grounding rule to every step's output, not just the final answer. This has to survive being consumed by two, three, or four downstream steps without collapsing into "just a fact" along the way — a predicted-offering-timing fact and a from-the-record completed-course fact have fundamentally different confidence, and that difference must still be visible in the composed final answer, not flattened into uniform-sounding prose.

### 3.3 "Simulate a what-if" and "generate a plan" are the same engine

A what-if question ("what happens if I fail X") and semester-plan generation are not two capabilities — they are the same underlying constraint-search engine, parameterized only by whether the starting state is the student's real current state or a hypothetically-perturbed one. Producing a hypothetical state is a small, cheap, deterministic transform (fail/drop/retake a course, delay a semester) that feeds into the *same* search engine plan-generation already needs. This is a genuine simplification, not two things to build.

---

## 4. Division of labor: what's LLM, what's code

**The LLM owns understanding — interpreting ambiguous language and deciding what to do next. Code owns computing — traversal, arithmetic, search, state mutation, once meaning is settled.**

Concretely, there are exactly **two** places an LLM call is intrinsic to the operation itself — everywhere else, an LLM may *decide to invoke* an operation, but the operation itself is plain deterministic code:

1. **Planning/orchestration reasoning** — deciding which tools to call, in what order, with what arguments, adaptively, as step results come in. This is the Planner and the per-step step-preparation pass.
2. **Text interpretation and composition** — turning wiki prose into a structured rule/fact (`interpret_text`), and turning structured, certainty-tagged results into grounded prose (`compose_answer`). These are the only two primitives where the LLM's actual language comprehension is the point of the operation.

Every other primitive (`get_entity`, `traverse_relationship`, the pattern-mining math inside `extract_temporal_pattern`, `apply_deterministic_rule`, `mutate_state`, `search_over_state`) never involves an LLM call at execution time — the LLM only ever decides *to* call one of these, and *with what arguments*.

This split resolves a nuance that matters for reliability: LLM reasoning replaces the *brittle deterministic interpretation* of wiki prose (which rule applies, which requirement bucket a course counts toward) — but the *computation* on top of that interpretation (summing credits, checking a threshold) stays a small, deterministic step, specifically because letting an LLM do open-ended arithmetic free-form is where hallucination creeps back in. This is the same schema-validated-extraction-then-deterministic-check pattern used elsewhere in this design, applied to requirements interpretation instead of intent classification.

### 4.1 The one rule that never moves

**The LLM inside any subagent may decide, interpret, and judge — but it may never directly assert a computed or structural fact without routing it through the corresponding tool call.** A subagent can use its own judgment to notice an edge case and decide how to handle it, but the actual arithmetic, traversal, or lookup still has to go through the deterministic tool, never get generated as a number or fact in the LLM's own output text. This is not a restriction on *which* subagents get to reason (see §6.1) — it is a restriction on *what kind of output* is allowed to come from reasoning versus from a tool call. This is the one boundary in the entire architecture that cannot move without reopening the exact hallucination risk the whole design exists to avoid.

---

## 5. The generic, composable tool primitives

Tools are **generic, composable primitives** — data in, data out — never one tool per canned answer. This is the only way a Planner can chain them into something never pre-scripted, like a genuinely novel multi-step plan or a what-if simulation. The organizing test for whether something deserves to be its own tool: **is this a new generic operation, or is it an existing operation with a different parameter?** Any specific question should be answerable as a *choice of parameters* over a small, fixed set of operations — not by writing a new tool.

This was arrived at the hard way: an earlier pass derived tools by walking through one worked example ("what happens if I fail course X") and asking what it needed — which produced plausible-looking tools like `get_course_dependents`, `predict_future_offering`, `find_requirement_substitutes`, `check_academic_standing_risk`. That approach was explicitly rejected once named: deriving tools from examples is the same enumeration mistake as the fixed-intent-enum, just recurring one layer down — every new prompt would surface one or two more scenario-shaped tools, forever, because a student can ask literally anything in-scope. Re-deriving the list at the level of **generic operations over the domain's actual data model** collapsed all of those scenario-shaped tools into nine primitives:

1. **`get_entity(entity_type, id)`** — structured fetch of any named record: course, track, program, minor, regulation topic, student profile, completed courses, saved plans. Replaces the whole family of "get X record" tools — they were never different tools, just different `entity_type` values.
2. **`search_knowledge(query)`** — semantic resolution over the wiki when the exact entity isn't already named.
3. **`traverse_relationship(entity, relation, direction)`** — a generic graph walk, parameterized by relation type and direction. Replaces "what depends on this course," "check prerequisites," "how does this course contribute to a requirement," track-membership lookups — all the same operation, just different `relation` values and which direction the edge is walked.
4. **`interpret_text(source, question)`** — LLM-reasoning extraction of a rule/fact/interpretation from wiki prose. The general form of "read the applicable rule from the wiki and tell me what it says" — any rule the system ever needs (retake limits, GPA thresholds, reserve-duty accommodations, minor eligibility) gets *identified* here, never hardcoded anywhere.
5. **`extract_temporal_pattern(fact_type, entity)`** — mine a time-indexed historical record for a pattern and project forward with confidence. Generalizes the offering-prediction need (§2.3) into something reusable for any other fact that turns out to be time-indexed.
6. **`apply_deterministic_rule(rule, facts)`** — arithmetic/validation given an already-identified rule (from #4) and already-retrieved facts. One generic compute step, not a separate tool per rule (credit totals, academic-standing checks, etc.).
7. **`mutate_state(base_state, change)`** — apply a hypothetical change to a state object (fail/drop/retake a course, delay a semester, change track).
8. **`search_over_state(state, constraints, objective)`** — constrained search/optimization. Powers both semester-plan generation and what-if simulation off the same engine (§3.3), and also absorbs "find an alternative course that satisfies this requirement bucket" as the same search with a different objective.
9. **`compose_answer(facts_with_certainty)`** and **`propose_action(action_type, payload)`** — final grounded-prose composition, and the one generic, always-proposal-only (never a direct mutation) write primitive.

Two unrelated prompts were used to sanity-check that this genuinely generalizes rather than being the fail-course-X example in disguise:

- *"I want to do a robotics minor — is that realistic two years in?"* → `get_entity` for the minor's requirements, `traverse_relationship` to see which required courses overlap with what's already done, `search_over_state` to check whether a feasible remaining-semester plan exists satisfying both the minor and the main degree, `compose_answer`.
- *"I have a month of reserve duty next semester — what should I do about my course load?"* → `search_knowledge` + `interpret_text` for the reserve-duty accommodation regulation, `get_entity` for the student's currently planned courses, `apply_deterministic_rule` to check what accommodation applies, possibly `search_over_state` for a lighter-load alternative, `compose_answer`.

Same nine primitives, zero new tools, neither example in mind when the list was written.

**The architectural payoff: extensibility lives in the data/schema vocabulary, not in the tool surface.** A new relation type, entity type, or time-indexed fact is an additive change to the graph's schema — it never requires writing a new tool or touching the orchestrator. The Planner's actual job becomes: not "match this request to a pre-built capability," but "figure out the right sequence of these nine generic operations, and the right parameters for each, for a request phrased in a way never seen before." That is the part that genuinely needs state-of-the-art reasoning, and the part a fixed-intent architecture could never do no matter how many intents were added to it.

### 5.1 Tool contract discipline

- **Every tool needs a strict, typed input/output schema** — not a fuzzy natural-language capability description — so a Planner/orchestrator LLM can reliably pick and chain them, the same way a function signature works rather than a paragraph.
- **Certainty/provenance is structural, not optional**, as part of every tool's output schema (source + confidence, generalizing the existing provenance-claim pattern to every tool, including derived/computed ones) — this is what lets certainty survive three or four chained calls without collapsing into "just a fact."
- **Fail closed, explicitly.** A tool that cannot determine an answer must return a distinct "insufficient/undetermined" outcome — never a placeholder that silently passes downstream as if it were real. `apply_deterministic_rule` and `interpret_text` are the two primitives most at risk of this and both need a real "not enough to determine this" return path, never a best-guess default.
- **Side-effect classification stays strict.** Eight of the nine primitives are pure reads or pure computation; only `propose_action` can produce a write, and it only ever produces a proposal, never a direct mutation — the same human-confirm boundary as everywhere else in the system, just no longer scattered across per-workflow special cases.

---

## 6. The specialist agent roster

Just as there is a small, fixed set of generic tools, there is a small, fixed set of specialist agent **roles** — a non-generative roster assembled from building blocks, never generated fresh per request. Having a roster of specialized agents, each with its own role, means the same "chef" can cook different "meals": each role gets a fully detailed system prompt (role and job, tool grant, explicit output schema, role-specific guardrails) defined once, and any specific instance of that role — retrieving user information vs. course information vs. a regulation — only needs its context package changed, never its definition redefined.

Five roles cover the domain cleanly:

- **Retrieval Agent** — resolves/fetches, owns `get_entity` / `search_knowledge` / `traverse_relationship`, can iterate if what it finds is ambiguous, returns facts + source + confidence, never commentary.
- **Interpretation Agent** — reads authoritative wiki text and produces a structured rule/fact for a specific question, owns `interpret_text` (plus retrieval to pull the source it's interpreting), must cite the exact page/section, must return "cannot determine" rather than guess.
- **Calculation/Validation Agent** — applies a deterministic rule to given facts, owns `apply_deterministic_rule` and the pattern-mining inside `extract_temporal_pattern`, must show its work, never asserts a number without the tool call backing it.
- **Simulation/Planning Agent** — owns `mutate_state` / `search_over_state`, translates loose constraints into the formal object the search primitive needs, produces projected plans or outcomes.
- **Composition Agent** — turns accumulated, certainty-tagged results into grounded prose. Deliberately gets **no tool access at all** — the one hard guarantee that keeps the very last step from reaching out and grabbing something ungrounded at the last second.

Checked against the fail-course-X example end to end: get-user-data → Retrieval; get requirements → Retrieval; retake-policy consequence → Interpretation; what-does-X-block → Retrieval (graph traversal); retake-timing prediction → Calculation (pattern-mining is just another tool in its kit, not a sixth role); cascading-delay projection → Simulation/Planning; substitution search → Simulation/Planning; regulatory risk → Interpretation then Calculation, chained; final answer → Composition. Every step lands on exactly one of the five roles, with no leftover case needing a sixth.

### 6.1 Every subagent gets full reasoning capability, unconditionally

An earlier framing split the five roles into "LLM-heavy" (Interpretation, Composition) versus "mostly deterministic" (Retrieval, Calculation, Simulation) — that framing was explicitly rejected as **the same enumeration mistake as the fixed-intent-enum and the scenario-specific tool list, just moved one layer up, from intents/tools to roles.** Deciding *by role*, at design time, which subagents get to reason and which don't repeats the exact trap the rest of this document exists to avoid.

**Every subagent is a `ReasoningBlock` instance** — an LLM call with optional tool access and an iteration loop is what a `ReasoningBlock` fundamentally is. There is no such thing as a subagent that's "just code." A Calculation-role subagent should still be able to notice, mid-task, that the requirement record it was handed is ambiguously worded, or that a fetched fact doesn't cleanly fit the rule it's about to apply, and use judgment rather than blindly proceeding — exactly the kind of situation the fail-course-X example was full of, where almost no step was actually as clean as "fetch X, done."

The correct framing: **don't decide by role whether a subagent gets to reason; every subagent gets the same general capability, and whether it actually uses that capability is decided dynamically, per instance, not prescribed per role at design time.** A "fetch my profile" step never needs an LLM in practice — not because Retrieval is barred from reasoning, but because there's nothing ambiguous to reason about; the step-preparation pass already resolved it to a direct call. A credit-total calculation usually just applies the rule deterministically, but the moment it hits genuinely ambiguous input, it should be able to escalate into its own reasoning pass rather than either failing or guessing. This escalation path — a cheap deterministic attempt first, a full reasoning loop only when it turns out to be needed — generalizes "retrieval is a spectrum, not one mechanism" to every subagent, not just retrieval.

The honest tradeoff: giving every subagent full reasoning-loop capability by default means every step, even trivial ones, technically *could* spin up an LLM call and iterate — real cost and latency if ungated. The resolution: the default execution path stays as cheap and deterministic as the step allows, and escalation into a real reasoning loop is **automatic and available, not mandatory** — triggered by the tool layer itself signaling low confidence, multiple candidates, or an unmet expectation, rather than a human having decided in advance which roles are "allowed" to think.

### 6.2 Per-role reasoning-block tuning

Each layer/role having its own optimized reasoning-block architecture is a direct consequence of this design, not an afterthought:

- **Retrieval** wants a cheap, fast, low-temperature model with a tight iteration cap — a bounded tool-observation loop.
- **Interpretation** wants a stronger model tuned for close reading, a schema-repair loop, and possibly a compare-and-synthesize pattern when cross-checking more than one wiki source.
- **Calculation/Validation** wants effectively zero creative freedom — single-pass, temperature at or near zero, strict schema-plus-validation, no iteration needed since it's arithmetic over already-settled facts.
- **Simulation/Planning** wants a larger iteration budget, since constraint search often needs a reflect-and-revise pass when the first candidate fails a constraint.
- **Composition** wants a moderate temperature for fluency, hard-constrained by the grounding rules.

---

## 7. The per-step dispatch mechanism

This is the mechanism by which the Orchestrator turns "the next step in the plan" into an actually-running subagent. Worked through concretely against an example: the user asks *"What happens if I fail course X this semester?"* Request understanding analyzes it, the Planner builds a step-by-step plan, and the Orchestrator executes it. Say the first step is "get the user's data." The Orchestrator must reason out what to spin up (a retrieval agent) and what to give it — which is itself one LLM call, whose output contains clearly structured fields:

1. **Which subagent to assign** to this subtask (here, the retrieval agent).
2. **The raw, optimized user-prompt text** the orchestrator wants to hand the subagent — the subtask's specific goal, description, and instructions.
3. **The necessary context** the subagent will need to complete the subtask.
4. **The subagent's own reasoning-block parameters** (budget, maximum iteration loops, and similar tuning).

Three tools then turn that single structured decision into a running subagent:

- **`prompt_builder`** takes the structured fields from that LLM output and assembles the ready-to-use natural-language prompt for the subagent.
- **`context_builder`** builds a context package containing (a) the prompt `prompt_builder` produced, and (b) the same underlying structured fields, packaged in their original structured form. This is deliberate redundancy: the structured form acts as an anchor the subagent (or the orchestrator, afterward) can use to stay anchored to the subtask's true intent and to validate the subagent's own work.
- **`subagent_builder`** builds the subagent from the parameters the orchestrator chose — the reasoning-block parameters and the context package — and the orchestrator starts it.

Once running, the subagent builds its own reasoning block from the context package it was given, and uses its own reasoning capability to decide how best to use its available tools to complete the assigned subtask. When done, it sends its output back to the orchestrator, which continues the plan.

### 7.1 Two refinements to keep this mechanism sound

**`prompt_builder` must be a rendering function of the structured fields, not an independent second decision.** The natural-language prompt and the structured context package are meant to act as mutual redundancy/anchors — but that property only holds if they're guaranteed consistent by construction. If the orchestrator's LLM call produces the structured fields once, and `prompt_builder` is a template that (mostly deterministically) renders those same fields into fluent instruction text, the two can never drift apart. If instead the LLM separately "writes a prompt" *and* separately "fills in context," there would be two independently-hallucinatable descriptions of the same intent that could quietly disagree — defeating the entire point of the anchor. So: **one structured decision, two renderings of it** — prose to guide the subagent's reasoning naturally, structure for it (or the orchestrator afterward) to mechanically check against.

**Tool access is owned by the specialist role as a ceiling, with per-instance narrowing — not decided fresh each call.** Each specialist role's fixed system prompt bakes in its *maximum* tool grant, so the orchestrator's structured decision doesn't need a "which tools" field in the common case — only the four listed above. But the orchestrator retains the option to *narrow* that ceiling for a specific instance: e.g., a Retrieval agent's default grant might include search and traversal, but if a particular call only ever needs to fetch one known entity by id, the orchestrator can hand it a tighter, single-tool grant for that call. Least-privilege per instance, layered on top of a sensible default per role.

**One more field belongs alongside the original four: the expected output schema for this specific subtask** — not just "the role has some output shape," but the concrete shape this instance's result needs so it composes cleanly into whatever step reads it next, and so it can be schema-validated before anything downstream trusts it.

### 7.2 What the orchestrator gives a subagent — the full, bounded package

Not "everything we know so far" — a deliberately bounded package:

- **The step's specific goal** — the operative instruction for this one step, not the raw user prompt (plus enough of the original request for tone/language grounding).
- **Only the upstream results this step actually depends on**, resolved out of the shared plan-execution state via dependencies the Planner declared when it created the step ("step 4 needs step 2's output") — never a guess at what might be relevant.
- **A tool grant appropriate to the role** — either pre-resolved calls with arguments already filled in (a Calculation-role subagent just gets the facts, it doesn't need to decide anything), or live access to a bounded subset of the nine primitives if the role needs to iterate (a Retrieval agent doing an ambiguous search may need to call `search_knowledge` more than once, refining as it goes).
- **An explicit output schema** — the exact shape of the result expected back. No role is ever allowed to return free text except Composition, on the terminal step.
- **Role-specific guardrails** — Composition is constrained to never introduce a number or status it wasn't handed; Calculation is constrained to never skip straight to an answer without citing which rule and which facts it applied; Interpretation is required to name the exact wiki source it read.

### 7.3 What the orchestrator expects back — never bare prose

- **The actual data**, conforming to the step's schema.
- **A certainty/provenance field** — source, confidence, and (for anything interpretation-derived) which wiki page/section and reasoning path produced it.
- **A status**: succeeded / partially succeeded (something's missing, but not fatally) / failed.
- **Assumptions and warnings** — anything the subagent had to assume rather than confirm.
- **A tool-call audit trail** — which tools were actually invoked, with what arguments, for traceability and for the Monitor to check the step actually did what the plan expected.
- **Optionally, a "needs another round" signal** — if the role needs to iterate, it returns an intermediate result requesting one more tool-call round rather than the orchestrator having to guess when to stop.

---

## 8. Shared plan-execution state (working memory)

Steps build on each other, so an accumulating state object is carried across the whole plan: each step's structured, schema-validated, certainty-tagged output is appended to it, and later steps' context packages are assembled by pulling declared-dependency slices out of it. This is what makes "simulate → then re-check requirements against the simulated state" possible — step 2 doesn't re-derive step 1's answer, it reads it out of shared state.

---

## 9. Monitor and replanning

The Monitor checks each step's result against the plan's own stated assumptions and success criteria, and can trigger a replan if something breaks mid-plan — the primary control loop for investigative requests (§3.1), not merely an error-recovery fallback. It can also interrupt between steps to ask the user something if a genuine ambiguity surfaces mid-plan, rather than only ever offering clarification after the fact. Once the Planner judges the plan complete, Synthesis/Composition produces the final answer purely from the accumulated, certainty-tagged plan-execution state, honoring every certainty tag it was handed rather than flattening them into uniform-sounding prose.

---

## 10. Worked example: "What happens if I fail course X this semester?"

This example is the one the whole design was pressure-tested against, and it is worth preserving because it is what forced several of the above decisions (adaptive replanning, certainty tagging, and three of the nine tool primitives) into existence.

**What a real student actually wants back, in priority order** — not a single-semester audit diff ("your remaining credits changed"):

1. **Is it even final yet?** Is this "will probably fail" or "already failed" — is there still a makeup exam (moed bet)? If there's still a path to pass, that's the first thing to hear, not a hypothetical analysis of a failure that hasn't happened.
2. **What does failing actually do to this course** — does it show permanently on the transcript even after a retake, is there a retake limit, does retaking replace the failing grade or add to it?
3. **What does it block, and for which of the courses the student is actually planning to take soon** — not just "X has dependents" in the abstract.
4. **When can it actually be retaken** — this is what really determines how bad the situation is. If X runs every Winter and every Spring, the delay is minor; if X is Winter-only and was just failed in Winter, it could be a full year (unless an unreliable summer offering happens). The honest answer names the pattern basis ("offered Winter and Spring for the last N years") rather than just asserting "you need to retake it."
5. **Given #3 and #4 together, how much does this actually push back graduation** — not "credits changed by -3," but "the courses stuck behind X can't happen until [semester], likely delaying graduation by [N] semesters" — or, ideally, "it likely doesn't delay you at all, because none of the blocked courses are on your critical path yet."
6. **Is there a way to avoid the delay entirely** — is X specifically required, or one option in a substitutable bucket? Could reordering the remaining semesters absorb the delay for free?
7. **Is there a risk of anything worse than a delay** — proximity to academic probation, a retake-count limit, or another regulation.
8. **A concrete recommendation** — push for the moed bet, plan around a Winter retake, or flag this as a borderline/regulatory edge case for a human advisor.

Every one of those eight concerns is a dependent step whose input is the previous step's output — a multi-semester, causally-chained question, not a single "simulate and recompute" pass. This is precisely why:

- **Adaptive replanning is the normal rhythm** — step 3 can't be planned in detail until X's fail/pass status is confirmed; step 6 can't run until step 5's predicted retake timing returns; step 6's shape (how many downstream semesters get re-examined) isn't knowable until the blocked courses are known.
- **Certainty has to be structural** — the predicted-retake-timing fact and the current-completed-courses fact have fundamentally different confidence, and that distinction must survive being consumed by three or four downstream steps.
- **Offering-pattern prediction (§2.3), reverse-dependency traversal, and requirement-substitute search** are all genuinely necessary primitives this example surfaced — which is exactly why they were generalized into `extract_temporal_pattern`, `traverse_relationship`, and `search_over_state` (§5) instead of being kept as one-off tools named after this specific scenario.

---

## 11. Open questions at time of writing

These were flagged during the design discussion as unresolved, not accidentally omitted:

- **Validation depth** — should a subagent self-check its own output before returning it, or should the Orchestrator perform an independent check afterward (using the structured-context anchor from §7.1), or both? The "anchor for validation" idea in the dispatch mechanism implies the latter is at least partly intended, but the split of responsibility wasn't finalized.
- **How exactly the Monitor decides a step "broke" enough to replan** — the mechanism (compare against stated assumptions/success criteria) was named, but the precise decision rule wasn't fully specified.
- **How tightly the step-preparation pass itself should be constrained** — it's meant to be small, cheap, and schema-bound, but the exact boundary between "step-prep decides this" and "the subagent itself decides this" has some genuine judgment calls still open (e.g., whether the orchestrator's structured decision needs a "which tools" field at all beyond the role's default ceiling, versus leaving that entirely to the role).
