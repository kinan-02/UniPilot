# UniPilot Agent — Architecture V2

**Status:** design, pre-implementation. Supersedes the orchestration model in
[`AGENT_VISION.md`](AGENT_VISION.md) §3, §6, §7, §9. The *substrate* and *grounding*
commitments of the vision (§2, §4, §4.1, §5, §5.1) are **kept and promoted to the
center**; the *orchestration spine* (Request Understanding → Planner → Orchestrator
→ Task Handler → Monitor as five separate LLM-calling services) is **retired**.

This document is written to leave no gap: every seam where a fact could be
fabricated, every place the old design spent an LLM call to watch another LLM
call, and every failure mode of the new design, is named and answered.

---

## 0. Why V2 exists — the one-sentence diagnosis

The V1 layers each named a real *cognitive operation* — understand, plan,
dispatch, decompose, verify — and reified each into its **own agent, with its own
LLM call and its own context, connected by schemas.** That reification is the
defect. It turned one train of thought into an org chart of specialists passing
memos, and every memo hand-off is a call that cannot see the others' context and
can therefore fabricate. Measured consequence: a trivial question ("how many
credits do I still need?") cost **30 LLM calls and 110 seconds**, produced a
**fabricated `92.5`** (the Planner did the subtraction in prose and wrote the
answer into a step's success criteria before any tool ran), and shipped it at
**"high" confidence** — while every guard the org chart added ran with **thinking
disabled on all 50 calls of the run**, because plan quality had collapsed and the
fix for slow thinking calls was to turn thinking off and add more guards.

V2 inverts the organizing principle:

> **Reliability comes from substrate safety, not orchestration control.**
> Make the floor structurally incapable of fabricating a fact, and the ceiling
> can be a single intelligent reasoning loop — because it no longer matters *how*
> the model reasons above a layer that cannot lie.

---

## 1. The two invariants everything derives from

Every decision below is an application of exactly one of these. If a proposed
change violates neither, it is a matter of taste; if it violates either, it is
wrong.

### Invariant A — Grounding (structural, not prompted)

**Every fact in any output is one of exactly three kinds, each with its own
structural guarantee. A bare model-authored fact is unrepresentable.**

| Kind | Origin | Guarantee | Certainty basis |
|---|---|---|---|
| **Fetched** | `get_entity`, `search_knowledge`, `traverse_relationship` | The value is *selected* out of a recorded tool envelope by a code-resolved path. The model emits a selector, never the value. | `official_record` / `wiki_derived` |
| **Computed** | `apply_deterministic_rule` / `expression_tree`, `extract_temporal_pattern` | The value is the output of a deterministic expression over **refs to existing facts**. Literal operands are rejected where a ref is available. | weakest input fact |
| **Interpreted** | `interpret_text` | The model authors a fact from authoritative prose — the *one* place its language output IS the product. Fenced by a **mandatory citation** (page + section) and a certainty tag; it may **not** contain a computed number (arithmetic is handed to Compute). | `wiki_derived` / `llm_interpretation` |

The mechanism that makes Fetched and Computed structural already exists in the
codebase and is proven: `subagents/fact_projection.py` ("there is no syntax in
which the model can express a number") and `tools/primitives/expression_tree.py`.
**V2 promotes these from a retrieval-only patch to the universal fact-admission
path.** Nothing enters the working set as a fact except through one of the three
kinds.

Interpreted facts are the single softer seam, and deliberately so: reading "which
requirement bucket does this course satisfy" out of Hebrew catalog prose is a
language-comprehension problem — the exact thing this whole system exists to do —
and there is no tool envelope to select from because the model IS producing the
fact. The guarantee there is *provenance + honesty tagging*, not structural
impossibility: it must cite the exact source, it is tagged as interpretation (never
`official_record`), and it is forbidden from emitting arithmetic. That is the
strongest guarantee available for that class of fact, and the boundary is drawn so
that everything computable stays on the structural side of it.

### Invariant B — Bounded cognition (one loop, data in hand)

**The system reasons in one continuous loop with the data already in hand. It
never commits to structure before seeing data, and it never runs an LLM call whose
only job is to watch another LLM call.**

Corollaries:
- Structure is **emergent (traced), not predicted (blueprinted).** The dependency
  graph is discovered by execution, not drawn up front.
- Decomposition is for **context economics, never a role taxonomy.**
- Cognitive operations (plan, route, monitor, replan) are **moves inside the
  loop**, not separate agents.
- **Budget the turn, not the call.** Degrade honestly; never return silence.

---

## 2. Architecture at a glance

```
                       ┌──────────────────────────────────────────────┐
   student request ──► │  FRONT DOOR (1 cheap call)                    │
                       │  → {in_scope, decline_reason?, sub_asks[],    │
                       │      language}                                │
                       └───────────────┬──────────────────────────────┘
                        in_scope=false │ in_scope=true
                             ▼         ▼
                    Boundary decline   ┌───────────────────────────────────────┐
                    (grounded prose)   │  AGENT LOOP  (thinking ON)             │
                                       │  repeat until final_answer / budget:  │
                                       │    think ─► emit ONE of:              │
                                       │      • tool_calls[]  (parallel ok)    │
                                       │      • spawn_subtask (context isolate)│
                                       │      • clarification_needed(question) │
                                       │      • final_answer(prose + fact_refs)│
                                       │    code executes ► append typed facts │
                                       └───────────────┬───────────────────────┘
                                                       ▼
                       ┌───────────────────────────────────────────────────────┐
                       │  ANSWER BOUNDARY (the single verification)             │
                       │   1. grounding check  (code, no LLM): every number/    │
                       │      code/status/offering traces to a fact ref         │
                       │   2. completeness check (≤1 LLM call): every sub_ask    │
                       │      addressed                                         │
                       │   pass ► deliver   fail ► bounded continuation w/ the  │
                       │                            specific named gap          │
                       └───────────────────────────────────────────────────────┘
                                                       ▼
                                          API response (unchanged contract)
```

Everything between the Front Door and the Answer Boundary that V1 had — Planner,
Planner Council, critics, Specialist Router, Task Handler, Monitor, per-step
success-checks, complexity classifier, five role-blocks — **is deleted and
replaced by the one loop.** The loop plans by thinking, routes by choosing a
tool, monitors by reading the observation it just got, and replans by deciding
differently next turn.

---

## 3. The Substrate (grounding floor) — kept, promoted

The substrate is the only place a fact can be born. It is the part of V1 worth
keeping almost intact; V2 changes its *status* (from subordinate detail to the
thing the whole architecture rests on), not its code.

### 3.1 The fact envelope — the universal unit

```
FactEnvelope {
  key:       str                     # stable name the loop refers to it by
  value:     JSON                    # the actual data (never model-typed)
  source:    ToolCitation            # tool name + args of the call that produced it
                                     #   — GENERATED IN CODE from the recorded call,
                                     #     never taken from the model's say-so
  certainty: CertaintyTag {          # structural, survives chaining
    basis:      "official_record" | "wiki_derived" | "predicted_pattern"
              | "llm_interpretation" | "simulated"
    confidence: float
    source_ref: {page, section, reasoning_path}?   # for interpreted/wiki facts
  }
}
```

This is the existing envelope shape (`state.py`, `fact_projection.py`) — kept
verbatim so the downstream consumers (`state_index`, the calc block's
`_unwrap_fact_envelope`) need no change.

### 3.2 Fact admission — the three paths (Invariant A, in code)

- **Fetch:** tool returns raw data → the agent surfaces a fact by emitting a
  selector `{key, from: call_handle, path}` → `project_facts` resolves the value
  from the recorded envelope and stamps `source`/`certainty` from the call. The
  model cannot write the value.
- **Compute:** the agent emits an `expression_tree` whose leaves are **refs**
  (`ref:1e`) → the evaluator rejects a literal where a ref is available (this is
  the fix for the `92.5` bug: `155 - 62.5` typed as literals is refused exactly as
  `ref:1d - ref:1e` was) → result is a fact whose certainty is the weakest input.
  **(Strengthened by §16.3: forbid a numeric literal in *any* arithmetic operand,
  not only when a ref happens to be available — the spike caught a `const:155`
  laundered through precisely because no ref existed for it yet.)**
- **Interpret:** `interpret_text(source, question)` returns a structured fact +
  mandatory citation; tagged `wiki_derived`/`llm_interpretation`; forbidden from
  containing a computed number.

### 3.3 The tool surface (reorganized by grounding kind, not role)

The 9 primitives and the composites are kept. They are re-grouped by *what
grounds their output*, which is the distinction that actually matters, replacing
the 5-role taxonomy (which was dead weight — its per-role reasoning tuning was
literally unreachable code in V1).

| Group | Grounding | Tools |
|---|---|---|
| **Fetch** | provenance | `get_entity`, `search_knowledge`, `traverse_relationship` |
| **Interpret** | citation | `interpret_text` |
| **Compute** | expression over refs | `apply_deterministic_rule`, `extract_temporal_pattern` |
| **Simulate** | typed state transform | `mutate_state`, `search_over_state` |
| **Write** | human-gated proposal | `propose_action` |
| **Composite** | inherits from its chain | `get_policy_answer`, `get_course_profile`, `check_eligibility`, `get_track_requirements`, `simulate_course_disruption`, `compare_plans`, `audit_graduation_progress`, `find_requirement_substitutes`, `get_current_date`, `get_current_semester` |

**Composites are re-legitimized by the loop model.** In V1 they *looked* like the
scenario-shaped tools the vision §5 rejected, because the pipeline pre-committed to
them via routing. In V2 a composite is a **macro the reasoning agent may choose
when it fits** — identical status to a primitive, selected dynamically with the
data in hand, never hardcoded into a control path. Their job is to **keep the loop
short on common questions** (one call instead of a 6-turn chain), which is the
primary defense against the loop's own failure mode (§7). They stay. The
enumeration-mistake test still applies to *new* ones: a composite must be a
generic parameterized chain, never a canned answer to one question.

Tool contract discipline (unchanged from §5.1): strict typed I/O schema;
certainty/provenance structural in every output; **fail closed** with a distinct
"undetermined" outcome, never a placeholder; strict side-effect classification
(only `propose_action` writes, and only a proposal).

### 3.4 The injection firewall lives here, not in the front door

Prompt-injection defense is a **substrate** property, not a Front-Door property.
The Front Door sees only the user message and can be subverted by the same
injection the loop would see; worse, it never sees *retrieved data*, which is the
more dangerous vector. The real guarantees:
- No tool ever executes instructions found in data. Tools only read / compute /
  propose.
- `propose_action` is the sole write and is always a human-confirmed proposal.
- The loop's system prompt treats all tool-result content as data to reason about,
  never as instructions.

---

## 4. The Agent Loop (the reasoning core)

One thinking-enabled loop. This is the entire "middle" of the system.

### 4.1 One iteration

Input assembled each turn:
- **System prompt:** the single agent role (advisor) + the grounding rules
  (`grounding.py`, kept, including its hard-won entity-schema notes) + the tool
  schemas + the output contract (§4.2).
- **Working set (§5):** the question, the sub-asks checklist, all fact envelopes
  so far, an **index** of raw tool results (handles + shapes, *not* full
  payloads), and the observation log.
- **Last observation:** the result(s) of the previous turn's tool calls.

The model thinks (thinking ON), then emits **exactly one**:

1. `tool_calls: [ {tool, args}, ... ]` — one or more calls; **independent calls in
   the same turn run in parallel** (native parallel tool-calling — this is how the
   dependency graph's parallelism is recovered, without an up-front plan).
2. `spawn_subtask: {objective, inputs, output_schema}` — delegate a bounded
   sub-problem to a child loop for **context isolation** (§6).
3. `clarification_needed: {question}` — a genuine ambiguity blocks progress; end
   the turn asking the student (§8).
4. `final_answer: {prose, fact_refs}` — compose the answer (§4.2, §9).

Code executes the choice, appends typed results to the working set, and loops.

### 4.2 The final-answer contract — how composition stays grounded (the crux)

This is the seam that produced both the `92.5` fabrication and the
`Winter 2025`/`Spring 2025` self-contradiction, so it is specified exactly.

**A number, course code, semester code, status, or offering claim may not be
typed into the answer prose. It must be a slot filled from a fact ref.**

`final_answer` is emitted as:
```
{
  prose:      "You need {gap} more credits to finish {track}. {course} is offered {offering}.",
  fact_refs:  { gap: ref:computed_gap, track: ref:1a.trackName,
                course: "00960211", offering: ref:1d.offering_label }
}
```
- **Slot-filled tokens** (all numbers + structured facts): rendered by code from
  the referenced fact's value. The model literally cannot write `92.5`; it writes
  `{gap}` bound to a computed ref. Semester labels are a pure code function of the
  code (`2025-2 → "Spring 2025"`), so the model can never write "Winter" — killing
  that bug class structurally.
- **Free prose** (the connective language, tone, multilingual phrasing): written
  by the model for fluency.

**Backstop (deterministic, no LLM):** after slot-filling, extract every numeral /
course-code / semester-token from the *rendered* prose and require each to appear
in the referenced facts. Any stray token that slipped into free prose → reject
with that specific token named. This is `fact_projection`'s guarantee applied to
the whole answer.

Certainty is preserved, never flattened: because every slot carries its fact's
`basis`, a predicted offering renders with its hedge ("offered every Spring for
the last 3 years") and an official record renders flat — the composed answer keeps
the distinction the vision §3.2 requires.

### 4.3 Prompt architecture — one loop is *not* one giant prompt

The objection that retired the layered design must be answered head-on, because it
is the strongest argument the layers had: *"a single loop needs one enormous system
prompt holding every role's instructions; the model, while fetching, won't heed the
fetch-specific rules buried among unrelated ones, and the huge prompt adds
latency."* Both halves are real concerns. Neither implies separate LLM calls.

The false premise is that every role's full instructions must live in one system
prompt. They must not. **The single loop's system prompt is *smaller* than the sum
of the five V1 role prompts, because role-specific detail moves to where it is
used.** Context is engineered in three tiers by lifetime and relevance:

1. **The constitution (system prompt — small, static, cached).** Only what is
   *always* relevant: the grounding rules (`grounding.py`), the fact-kind rules
   (Invariant A), and the loop's output contract (§4.1). One to two screens. This
   is the part the model must hold at all times, and it is short enough to hold.

2. **Tool definitions (static, cached, surfaced at point of use).** Each tool
   carries its **own** detailed instructions in its description and schema. The
   fetch-specific guidance that V1 kept in the Retrieval role's system prompt —
   "join a completed course to the catalog by `metadata.courseNumber`, never
   `courseId`"; "`student_profile` has no `year_of_study` field, derive it" (the
   hard-won notes now in `grounding.py`'s `_ENTITY_SCHEMA_CONTEXT`) — moves onto
   `get_entity`. The model reads it **exactly when it is considering that tool**,
   and never while doing anything else. This is the mechanism that delivers
   role-specific instruction-following **without a role-specific call**: the
   instruction arrives at the point of use, for free, and is reinforced in the
   tool's returned observation (the repair-message pattern already in
   `fact_projection.available_paths`).

3. **The working set (dynamic, the only uncached part).** Question, sub-asks,
   accumulated facts, the tool-result index, the last observation (§5).

**Why this beats the role-call design on its own terms.** In the layered design the
fetch instructions sit in the Retrieval role's prompt *and* you pay an extra LLM
call, an extra round-trip, and a blind handoff to reach them — and the model may
*still* not follow them. With tool-attached instructions the same guidance is
present precisely when the model calls the tool, at zero extra calls, with the real
data in hand. Progressive disclosure replaces prompt-cramming: the model holds the
short constitution always, sees a tool's specifics only when that tool is in play,
and receives corrective guidance inline in a failed call's observation.

**The focused-prompt instinct survives where it is genuinely warranted.** A subtask
that truly needs a large, specialized instruction set — interpreting a gnarly
multi-clause regulation — is exactly the §6 `spawn_subtask` case: the sub-loop gets
its own **lean, focused** system prompt for that bounded job and returns a grounded
result. The "dedicated role prompt" idea is kept — but triggered by context
economics when needed, not imposed as a mandatory blind station before every step.

**Latency, precisely.** System-prompt tokens are processed in *prefill*, which is
parallel and cheap per token; generation (the thinking tokens) is *decode*, which
is sequential and is where per-call latency actually goes — and decode cost is
independent of system-prompt size. Modern prompt caching amortizes the static
prefix (constitution + tool definitions) across the loop's turns, so it is paid
once, not per turn. The layered design pays the opposite: **N separate round-trips**
(30, measured), each re-sending its own grounding block, role prompt, and
re-serialized state, each generating its own output. One loop sends the cached
constitution once and grows only the working set. **Total tokens processed and
total wall-clock are both lower for the loop, not higher** — consistent with the
measured 30-call/110s baseline for a question a short loop answers in a handful of
turns.

**The mini-model sharpening (GPT-5-mini, the demo model).** A smaller model is more
susceptible to long-context instruction dilution than a frontier one — which makes
the lean-constitution + tool-attached-instruction discipline **more** important,
not the layered design more attractive. The layered design does not escape the
problem; it relocates it to a place a mini model is *also* weak: blind planning and
routing with no data in hand. A mini model reasoning over real observations in a
short, focused context will follow instructions better than the same model drawing
up a dependency graph it cannot yet see the data for. This is an empirical claim and
§14 commits to testing it on GPT-5-mini directly.

---

## 5. Context & Memory model

The **working set** is the single source of truth for the turn and the entire
audit trail (it replaces V1's scattered `tool_audit_trail` plumbing and the
`PlanExecutionState`).

```
WorkingSet {
  question:     str
  sub_asks:     [str]                      # the completeness checklist (§8)
  language:     str
  facts:        {key: FactEnvelope}        # everything grounded so far
  tool_results: {handle: RecordedEnvelope} # raw payloads, addressed by handle
  observations: [Observation]              # append-only: what ran, ok/failed, why
  budget:       {turns_used, wall_clock_s, subloop_depth}
}
```

**Context discipline (this is what keeps the *flat* loop from flooding):** the
loop's prompt carries the `facts` and an **index** of `tool_results` (handles +
shapes + a one-line summary each) — **never the full raw payloads.** A 40-page
wiki page fetched on turn 2 does not re-enter the prompt on turns 3–10; the agent
addresses it by handle and pulls specific paths via selectors. This is how a long
investigation stays context-bounded without necessarily spawning a sub-loop.

Freshness invariant (kept from V1's `TurnContext`): the working set, tool cache,
and unresolvable registry are created **fresh per request**, never shared across
turns — so concurrent students can never see each other's state.

---

## 6. Decomposition — sub-loops, for context only

The single legitimate trigger for a second loop is **context economics**: a
subtask whose raw material would flood, or whose own multi-step search would
pollute, the parent's reasoning trace.

Canonical cases: "read this long regulation and extract the one applicable
clause"; "mine several years of offering JSON for a term pattern"; "search
hundreds of candidate courses for a substitute."

```
spawn_subtask(objective, inputs, output_schema) ─►
    child loop:
      • fresh, clean context (only `inputs`)
      • same substrate (tools, grounding, cache)
      • its own bounded budget, debited from the parent turn
      • returns ONE typed result → FactEnvelope(s) into the parent working set,
        provenance and certainty preserved
```

Rules that close the gaps:
- **Not a role taxonomy.** One recursive loop mechanism. There is no "retrieval
  agent" vs "calculation agent" — there is the loop, and a smaller instance of the
  loop when context demands.
- **Depth cap ≤ 2**, enforced in code, to forbid runaway recursion.
- **Shared budget:** a sub-loop debits the parent's turn/wall-clock budget, so
  decomposition can never buy unbounded total work.
- **Inline vs spawn heuristic (concrete):** spawn when the subtask's expected raw
  input exceeds a token threshold *or* requires its own iterative search;
  otherwise do it inline as one more turn. "Fetch, then compute" is **two inline
  turns**, never a spawn — the V1 Task Handler's atomic-vs-complex split is
  replaced by this single size-based rule.

---

## 7. Budgets, termination, and the new primary failure mode

Every architecture is organized around the one failure it refuses to allow. V1's
was **fabrication**, and the price was intelligence. V2's is **grounding by
substrate**, which buys the intelligence back — and its new exposure is
**wandering**: an autonomous loop that explores too long, floods context, or blows
latency. This is designed against explicitly.

- **Turn budget:** hard caps on both loop iterations (default **12**) and
  wall-clock (default **150s**, deliberately under the 180s API timeout so the
  student gets *our* honest conclusion, never a dropped connection). Whichever hits
  first forces graceful conclusion.
- **Graceful degradation (never silence):** on budget exhaustion, compose a
  best-effort answer from the working set that explicitly names the unresolved
  sub-asks. Keep V1's honest `_NO_ANSWER_MESSAGE` instinct — an honest "I could
  not determine X, ask the secretariat" beats both a blank reply and a confident
  guess.
- **No-progress detection:** the tool cache already dedupes identical calls; a turn
  that produces no *new* facts counts against a no-progress limit (default **3**)
  that forces conclusion. This catches the "re-resolving an ambiguous entity
  forever" loop that V1 hit.
- **No adapter-level retries** (kept, hard-won — see V1 `reasoning_effort.py`):
  retrying a call that timed out just hits the same wall more expensively. A failed
  tool call is an **observation the loop reasons about**, one level up, with full
  context — real recovery, not a blind retry. The one exception: a single retry on
  a transient provider error (429/5xx).
- **Sub-loop depth + shared budget** (§6).

**Effort control replaces the complexity classifier entirely.** Thinking is ON for
the loop's decision turns and the model self-scales reasoning effort per decision,
with the actual data in front of it — which is strictly better than V1's blind
pre-classification into tiers that (measured) all resolved to *thinking off*
anyway. The turn budget is the only global governor.

---

## 8. Front Door and multi-turn continuity

### 8.1 Front Door (one cheap call)

Produces `{in_scope, decline_reason?, sub_asks: [str], language}`. It does **scope
gating + request decomposition only** — no planning.
- `in_scope=false` → the Boundary Handler composes a grounded, tool-less polite
  decline. Done. (Kept from V1, it works.)
- `sub_asks` is the **completeness checklist** the Answer Boundary (§9) verifies
  against — the one artifact that makes "did we actually answer the question"
  checkable.
- It does **not** claim to be the injection defense (§3.4).

### 8.2 Multi-turn / clarification (fixing the V1 dead-end)

V1 could *ask* a clarification but structurally could not *hear* the answer:
`AdviseRequest` was `{question, user_id}`, `conversation_history` was plumbed into
Request Understanding and then always passed empty. V2 closes the loop:
- The API contract carries **`conversation_history`** (see §11).
- On the next turn the Front Door and loop see prior turns, so the student's
  "Winter 2025" reply lands in context and resolves the open ambiguity.
- The open clarification is the only cross-turn state, persisted in the agent's own
  Mongo collection (`agent_clarification_states`, already envisioned in vision
  §2.1) — minimal, rebuildable, never academic truth.

Statelessness otherwise is a **feature**: with no ambient session memory, the
memory-contamination failure mode (old topics leaking into new turns) is
structurally impossible. History is threaded **explicitly**, never carried
ambiently.

---

## 9. The Answer Boundary (the single verification)

Replaces V1's entire verification network (Planner Council, critics, Specialist
Router re-checks, per-step success-checks, Monitor). Runs **once**, at the end.

1. **Grounding check — code, no LLM, always.** Every numeral, course code,
   semester code, status, and offering claim in the rendered answer must resolve
   to a fact ref (§4.2). Deterministic and cheap; it is the `fact_projection`
   guarantee over the whole answer. An ungrounded token → reject.
2. **Completeness check — ≤1 LLM call, only when sub-asks are non-trivial.** Does
   the answer address every `sub_ask`? This is the *one* verification LLM call V2
   permits, justified because it runs once over the finished answer, not per step.
   **(Refined by §16.7: the presupposition case needs §8 decomposition to emit a
   *concrete* premise sub-ask and this gate to enforce it — a prompt-level "verify
   premises" rule was tested on GPT-5-mini and falsified. This is the hardest open
   item.)**
3. **On rejection → bounded continuation.** The loop resumes with the **specific,
   named gap** ("the number 92.5 traces to no tool call"; "sub-ask 2 —
   retake timing — is unaddressed") for a bounded number of extra turns. This is
   "replanning," but scoped to a real, concrete, named deficiency discovered *after
   the fact with data in hand* — never a blind council convened *before* the work.

This is the honest replacement for the V1 machinery: instead of many LLM calls
guessing whether each step *might* be wrong, one deterministic check *knows*
whether the finished answer is grounded, and one optional call checks whether it is
complete.

---

## 10. Worked validation — "what happens if I fail course X?" (vision §10)

The vision's own north-star case is the acid test, because §10 states its steps are
"a multi-semester, causally-chained question ... each step's input is the previous
step's output." **That description is a sequential loop, not a graph** — V1 built a
graph anyway. Under V2 the trace is:

1. `get_entity` student profile + completed courses *(parallel, one turn)*.
2. `interpret_text` on the retake regulation → "final only after moed bet" →
   the model reasons it must first check exam status (emergent dependency, not
   pre-planned).
3. `traverse_relationship` X's dependents; filter to the student's near-term
   planned courses.
4. **`spawn_subtask`**: mine X's multi-year offering history for a term pattern
   (context isolation — years of JSON stay out of the main trace) → returns a
   `predicted_pattern` fact.
5. `simulate_course_disruption` (composite) delay projection over the real state.
6. `find_requirement_substitutes` if the delay bites.
7. `final_answer` with slot-filled numbers, each carrying its certainty basis
   (the predicted retake timing renders hedged, the completed-courses fact flat).

Every dependency the vision enumerated **emerges** from the loop with prior
results in hand; nothing is committed before the data that determines it exists.
Parallelism appears exactly where the data is independent (step 1). Scoped recovery
is free — the loop only ever did what it did, so there is no premature structure to
walk back. **Nothing the dependency graph offered is lost; the up-front commitment
that caused the fabrication is gone.**

---

## 11. External contract (unchanged, so `services/api` needs no change)

- Route `POST /advise` and `/advise/stream` keep their response shape exactly
  (`response.answer/confidence/course_ids/sources/...`, `retrieval_agent.status`,
  `semester_resolution`) — the mapping in `services/api/advisor_service.py` and the
  frontend `AdvisorReply` type are untouched.
- **One additive change:** `AdviseRequest` gains optional `conversation_history`
  (§8.2). `services/api` passes it through; absent = a fresh single-turn request,
  identical to today.
- `course_ids` / `sources` continue to be **derived in code from the working set's
  tool trail**, never model-authored (kept from `advise.py`).
- **Streaming fix:** replace the single untyped `Queue[str]` (whose
  `startswith('{"type":')` control/content discrimination swallowed answers) with a
  **typed event envelope** — `{kind: "token"|"final"|"error", ...}` — so answer
  text and control events can never be confused, and delete the fragile backfill
  reconciliation pass.

---

## 12. Observability & eval

- Keep the `LoggingLLMAdapter` harness and every `ise_correctness` **case** — they
  are excellent and they are what caught these bugs.
- **Upgrade the assertions from presence to derivation.** Today
  `_assert_mentions(answer, ["92.5"])` passes on a *fabricated* 92.5. V2 asserts
  that 92.5 **traces to a Compute fact over refs** — a right answer by mental
  arithmetic must fail the eval. This closes the substring-match blind spot that
  let the fabrication ship green.
- Per-turn metrics: LLM call count, wall-clock, turns used, grounding-check
  pass/fail, sub-asks covered, budget-exhaustion rate. The working set + observation
  log is the audit trail.

---

## 13. Migration map — what survives, what dies, what's new

**Survives (mostly intact — the good work):**
- The entire substrate: 9 primitives, composites, `fact_projection` (promoted to
  universal), `expression_tree`, `grounding.py` (incl. entity-schema notes), tool
  cache, unresolvable registry, certainty envelopes.
- `interpret_text`, `apply_deterministic_rule`, `extract_temporal_pattern`,
  `mutate_state`, `search_over_state`, `propose_action` and their contracts.
- Front Door: `request_understanding` (slimmed to scope + sub_asks + language),
  `boundary_handler`, `response_language`.
- The whole retrieval/RAG layer (wiki index, embeddings, rerankers) — untouched.
- The `/advise` response contract and `advise.py`'s code-derived fields.
- Every eval case + the logging harness.

**Dies (the org chart):**
- `orchestrator/` — `loop`, `task_handler`, `task_handler_success_check`,
  `monitor`, `specialist_router`, `parallel_dispatch`, `state_index`,
  `replan_ledger`, `context_builder`, `prompt_builder`.
- `planning/` — the entire package: `planner`, `planner_council`, `critic_selector`,
  `plan_validator`, `rewrite`, plan `schemas`, `state`.
- `complexity_classifier/` and `reasoning_effort` tiers.
- `roles/roster` as a **dispatch** mechanism (the 5-role taxonomy); the role
  *prompt text* may be mined to inform the single advisor system prompt.
- The dead second framework already unreachable in V1:
  `reasoning/reasoning_block.py`, `subagents/run.py`, `subagents/builder.py`,
  `subagents/tool_loop.py`.
- `subagents/{retrieval,interpretation,calculation_validation,simulation_planning,
  composition}_block` **as separate role-blocks** — their grounding logic
  (fact_projection wiring, expression_tree wiring) migrates *into the tool/loop
  layer*; the blocks themselves are gone.

**New (small — a net deletion of thousands of lines):**
- The agent loop (~200 lines).
- The working set + tool-result index/store.
- `spawn_subtask` + the sub-loop runner (reuses the loop).
- The Answer Boundary: grounding check (code) + completeness check (1 call) +
  bounded continuation.
- Turn budget + graceful conclusion.
- The typed streaming event envelope.

---

## 14. The hard dependency, stated plainly

This architecture **uses** reasoning instead of disabling it, so it inherits a hard
prerequisite: a genuinely strong reasoning model with reliable tool-use and a
usable thinking mode. If the underlying model cannot reason and call tools well, no
architecture rescues it — but V1 proved the converse costs everything: a capable
model with thinking turned off, wrapped in guards, is slower, dumber, and *more*
prone to fabrication than the same model reasoning in one loop.

**Model split:** the demo runs on **GPT-5-mini**; development runs on
`deepseek-v4-pro` (cheaper). Two consequences follow, both load-bearing:

- **Validate on GPT-5-mini, not just the dev model.** Instruction-following of the
  lean constitution + tool-attached instructions (§4.3) is an empirical property
  that differs between a mini and a frontier model. The single decisive test: run
  `credits_remaining` and `presupposition_conflict` on GPT-5-mini and confirm the
  loop (a) follows the fetch/compute/interpret contracts, (b) grounds every number,
  (c) finishes inside the turn budget. If the mini model dilutes on the lean prompt,
  the fix is **better context engineering** (push more specifics onto tools, shorten
  the constitution, lean harder on progressive disclosure) — never reintroducing
  blind pre-planned calls, which a mini model handles *worse*, not better.
- **Behaviour parity check across the two models.** Because dev and demo differ,
  every eval run should record which model produced it, and the grounding/derivation
  assertions (§12) must pass on **both** — so "works in dev, breaks in the demo" is
  caught before the demo, and "which model" stays a separate, explicit decision from
  "which architecture."

---

## 15. Open decisions (yours to set before implementation)

**RESOLVED 2026-07-18 (spike-informed):** (1) **pure loop** + a minimal Front Door that
decomposes into sub-asks; (2) **slot-fill numbers + structured facts**, free prose backstopped;
(3) completeness gate **run whenever a sub-ask concerns the student's own record or a premise**
(a liberal gate, ~1 call — it was decisive for `presupposition_conflict`); (4) **ship
single-loop**, add `spawn_subtask` on the first real context-flooding case. The four forks below
are kept for the reasoning that led here.

These are the forks where judgment, not derivation, sets the answer. Defaults are
recommended, not assumed.

1. **Thin fixed spine, or pure loop?** Default: **pure loop + composites** (the
   composites already encode the recurring shapes, so structure comes without
   hardcoding control flow). Alternative: a minimal `resolve → reason → answer`
   spine for the first iteration, removed once the loop is trusted.
2. **Slot-fill strictness.** Default: **numbers + structured facts must be
   slot-filled** (structural), free prose backstopped by the extraction check
   (§4.2). Stricter option: slot-fill *all* facts including interpreted phrases.
3. **Completeness check — always or gated?** Default: **gated** — skip the LLM call
   when there is a single trivial sub-ask, run it when sub-asks are plural or
   non-trivial.
4. **Sub-loop availability in v1 of the rewrite.** Default: **build the mechanism,
   but ship the first version single-loop**, and enable `spawn_subtask` the first
   time a real case proves context flooding — so decomposition is added against
   evidence, not speculation.
```

---

## 16. Empirical validation — the loop spike (2026-07)

Before committing to the rewrite, the load-bearing bet of §14 was tested directly:
a throwaway single loop, thinking ON, on the **demo model (GPT-5-mini)**, against the
two hardest live cases (`credits_remaining`, `presupposition_conflict`), reusing the
real substrate unchanged (`project_facts`, `expression_tree`, the tools). The spike
lives at `services/ai/tests/agent_core/test_v2_loop_spike.py`. Every claim below is
measured, not argued.

### 16.1 The headline — the grounding floor holds on the mini model

Across every iteration the loop **never once typed an ungrounded number into an
answer.** The V1 signature failure — fabricating `92.5` by mental arithmetic and
shipping it at high confidence — did not reproduce; the loop either grounded the
number or degraded honestly. Invariant A survives contact with a mini model. And the
loop beats V1 on its own terms: the same `credits_remaining` question that cost V1
**30 calls / 110s / a fabricated answer** was answered in **6 calls / 30s / fully
grounded** once the seams below were closed.

The convergence is the evidence — each failure named the next fix, and the fixes compose:

| Iteration | `credits_remaining` outcome |
|---|---|
| V1 baseline (measured) | 30 calls, 110s, **fabricated** 92.5 at high confidence |
| Spike: action/tool split protocol | 12 turns, gave up — model conflated the two channels |
| Spike: unified tool channel | 11 turns, 92.5 but `155` **laundered** as a typed const |
| Spike: const-block + tool-attached notes | 10 turns, 92.5 grounded — but only when the model *happened* to phrase interpret as "return only the number" |
| Spike: scoped interpretation (whole-page → chunk) | **regressed** — scoped read missed the section, broken answer |
| Spike: scoped + whole-page fallback | interpret returned prose; `subtract` couldn't parse it; broken answer |
| Spike: **typed `numericValue`** | **6 turns, 30s, 92.5 fully grounded** — `155` interpreted-typed with citation, `62.5` computed from records |

Every recurring lesson was the same: **a required behaviour that is only prompted is
not reliable; the behaviour has to be made structural.** This section records the
refinements that lesson forced on the design above.

### 16.2 §4.1 refined — the loop's actions are *uniform tool calls*

The first spike split the model's moves into two kinds — real "tools" vs meta
"actions" (surface/compute/answer). GPT-5-mini conflated them, repeatedly trying to
call `surface_fact` inside `tool_calls`, and burned four turns before giving up.
Collapsing everything into **one uniform `tool_calls` channel** — where `surface_fact`,
`compute`, `final_answer`, and `clarify` are just callable tools alongside the
substrate tools — fixed it immediately. **§4.1's action list should be implemented as
one call channel, not a separate action taxonomy** — a tool-calling model expects a
single "call" surface.

### 16.3 §4.2 / §3.2 refined — the const-laundering seam

§4.2 as written ("reject a literal where a ref is available") is **insufficient.** The
spike caught the model computing `subtract({const: 155}, {ref: earned})` — typing the
degree total as a literal because it wasn't cleanly fetchable — and shipping the
resulting `92.5` as if grounded. It passed both guards: `expression_tree` only rejects
an *all-const* tree, and the final-answer backstop only inspects numerals in the
*rendered prose* (the `155` never appears there, only the computed `92.5`). The model
even **rationalised** the const in its own reasoning ("the total can be used as an
explicitly given constant"). Prompt discipline could not hold this; structure did.

**Strengthened rule (proven to close it):** an arithmetic operand that produces an
answer number must be a **ref to a grounded fact**, never a typed numeric literal. The
spike enforces this by rejecting a numeric `const` in any `add/subtract/multiply/divide`
node, with a repair message pointing at fetch/interpret. A genuinely user-given literal
(rare) is a separate, later concern — the safe default is to forbid the literal and
force grounding. This is the same move as `fact_projection`: make the ungrounded form
*unrepresentable*, don't detect it after the fact.

### 16.4 §3.2 refined — the Interpreted→Computed handoff needs a *typed* value

Invariant A's "Interpreted" path yielded **prose** (`answer: "…155 credits…"`), and
`expression_tree` cannot compute over prose — so a number that lived only in text was
ungrounded-in-practice: the loop could read it but not use it, and fell back to typing
a const. The fix, now implemented in `interpret_text`, is the Interpreted analogue of
`fact_projection`: when the answer is a bare quantity, the tool returns a **typed
`numericValue`** (the number, with its citation and `llm_interpretation` basis)
alongside the prose. A caller selects the typed value and computes directly. **§3.2's
Interpret path must specify that a numeric interpretation produces a typed number, not
only prose** — otherwise "Interpreted" facts are second-class and silently push the
loop toward laundering.

### 16.5 §3.3 / §4.3 refined — interpretation reads a *retrieved chunk*, not the page

`interpret_text` was fetching the whole wiki page and truncating to 6000 chars — which
both wasted context and could **silently truncate the answer out of view** on a long
page (a fabrication pressure, not just a cost). It now reads the top reranked
**section(s)** of the source page via a new page-scoped `retrieve_page_chunks`, with a
**whole-page fallback on `cannot_determine`** so scoping can only speed things up, never
lose an answer the page held. Two hard-won details:
- **Scoping's real payoff is correctness on over-cap pages, not token savings.** The
  interpret call's source text is *prefill* (cheap, parallel, and it does not affect
  *decode*, where the latency and cost actually live); a small JSON verdict is the only
  *decode*. So scoping a page that already fits the cap saves little and risks a miss
  that triggers a double-decode fallback — the payoff is on pages that *exceed* the cap,
  where the old code truncated.
- **Recall is a `k` problem here, cheaply.** The candidate set is one page's handful of
  sections, so a stingy `k` discards half the page and causes the miss; a generous `k`
  (now 8), bounded by the char cap, is a relevance-ordered budget-fill that keeps the
  answer in view. (Whether chunk/reranker *quality* also needs work is a separate, larger
  investment worth diagnosing before spending.)

### 16.6 §4.3 validated — tool-attached instructions demonstrably work

Direct A/B: with `interpret_text`'s "source is a wiki slug" guidance buried/truncated,
GPT-5-mini passed a call-handle as `source` and failed three times; with the guidance
attached to the tool at the point of use, it called it correctly on the first try.
Progressive disclosure via tool-attached instructions is not a hope — it measurably
changed behaviour on the demo model. §4.3 stands, reinforced.

### 16.7 §8 / §9 refined — the completeness gap is structural, and the hardest open item

`presupposition_conflict` ("if I fail `00940224`, can I take `00960211`?") is **not yet
solved.** The student already passed `00940224` (grade 85); the correct answer surfaces
that the premise is false. Across every spike run the loop *fetched* the record but
never made the trivial check "is `00940224` already in it?", answering the hypothetical
on catalog logic instead. **Grounding held (no fabrication) — but the answer was
incomplete/misleading.** This is a completeness/reasoning gap, and it is the acid test
for §8/§9.

Critically, a **prompt-level fix was tested and falsified.** A constitution rule ("verify
presuppositions against the record before answering") made the model *narrate* the check
but not perform it — it reached for the heavy hypothetical (simulate the failure via
`simulate_course_disruption`/`mutate_state`), drowned in composite argument-shape friction,
hit the turn budget, and still never surfaced the 85. Abstract instruction produced talk,
not action — the §16.1 lesson again.

**The structural fix (design, not yet prototyped):**
- **§8 decomposition emits a *concrete* premise sub-ask**, not an abstract directive:
  for this question, sub-ask A = *"the student's current status on `00940224`"* (a trivial
  retrieval that surfaces the 85), sub-ask B = *"is `00940224` a prerequisite for
  `00960211`"*. Concreteness is the mechanism — "what is the student's status on X" is a
  lookup the model executes; "verify the premise" is an abstraction it rationalises into
  simulation.
- **§9's completeness check gates on it** — an answer that never states the student's real
  status on the named course is rejected, and the loop resumes with that gap named. This is
  what makes the check non-optional (and it argues §15's completeness fork toward
  *"run it whenever a sub-ask concerns the student's own record,"* not merely "when sub-asks
  are plural").

This closes §15's completeness fork toward the structural side.

**Validated (2026-07-18).** The structural fix was prototyped in the spike and **closes the
case**: decomposition emitted exactly the concrete premise sub-ask ("the student's current
status and grade on `00940224`"), and — crucially — it redirected the loop *away* from the
simulation rabbit hole the prompt-rule fell into, straight to the record. Two further pieces
were needed and are now proven:
- **The gate must refuse "I could not determine it" for the student's own record.** The first
  gated run escaped through exactly that loophole (the model claimed it couldn't determine a
  status the record plainly held). Tightening the gate so a claim of non-determination never
  *addresses* a sub-ask about the student's own record closed the escape.
- **A substrate `select` capability.** The real blocker was not reasoning: the loop *knew* it
  needed `00940224`'s grade but had no tool to get it. A `surface_fact` selector walks a path
  and cannot filter; `expression_tree` aggregates but cannot select-and-return a record's
  field — so "the grade of course X in the completed list" was unreachable. Adding a **filter-
  select** ("the record where `courseNumber == X`, read its `grade`") let the model pull the
  `85`, and the final answer surfaced the already-passed conflict, fully grounded. This is a
  genuine **substrate gap to close in V2** (a new primitive, or extending `search_over_state`/
  the selector vocabulary) — a filter-select is the Computed-kind analogue of `fact_projection`
  for "which record," and it is now proven necessary.

### 16.8 New finding — composite `state` ergonomics

Orthogonal but real: `simulate_course_disruption` / `check_eligibility` / `mutate_state`
take a `state` argument the model could not reliably shape (it passed `{ref}` wrappers and
malformed semester codes, self-correcting only from error observations). This ate most of
the turns whenever the loop attempted a real hypothetical. **These composites should fetch
the student's state themselves from `student_id`** (or accept a working-set handle
explicitly) rather than making the model marshal it — a §3.3 tool-contract refinement to
schedule alongside the loop rewrite.

### 16.9 What is already implemented vs still to prove

- **Implemented in the real substrate** (survives into V2, non-live suite green): scoped
  `interpret_text` with whole-page fallback (`retrieve_page_chunks`), typed `numericValue`,
  `k = 8`. These benefit V1 today and V2 tomorrow.
- **Proven in the spike only** (not yet in the real loop): the unified tool channel, the
  const-block rule, the final-answer slot-grounding backstop (incl. rejecting a non-scalar
  slot), the §8 decomposition + §9 completeness gate (§16.7), and the **filter-select**
  capability that closes `presupposition_conflict`. These are the design decisions the rewrite
  must carry over from the spike.
- **Still unproven / to productionize**: turning the spike's `select` into a real substrate
  capability (§16.7 — a new primitive or an extension of `search_over_state`/the selectors),
  and the composite `state` ergonomics fix (§16.8). With those, both north-star cases
  (`credits_remaining`, `presupposition_conflict`) are grounded *and* correct in the spike.

---

## 17. Gap register & rewrite readiness

A deliberate sweep for what the spike has *not* yet retired, so the rewrite starts against a
known board rather than discovering these mid-flight. Each gap carries a disposition.

### 17.1 Resolved & validated (carry the decision straight into the rewrite)

Unified tool channel (§16.2); const-block (§16.3); typed interpretation `numericValue`
(§16.4); scoped retrieval + whole-page fallback + `k`-budget (§16.5); tool-attached
instructions (§16.6); §8 decomposition into concrete premise sub-asks + §9 completeness gate,
incl. the "no cop-out on the student's own record" tightening (§16.7); filter-`select`
(§16.7); the deterministic final-answer backstop for numerals/codes + unresolved-slot +
non-scalar-slot rejection (§4.2). These are no longer open questions — they are decisions.

### 17.2 Substrate / contract items to build (known engineering, not unknowns)

- **`select` as a real primitive.** Filter-select ("the record where `courseNumber == X`,
  read its `grade`") is spike-only and now proven necessary. Add it as a primitive, or extend
  `search_over_state` / the selector vocabulary. It is the Computed-kind analogue of
  `fact_projection` for *which* record.
- **Composite `state` — smaller than first thought.** `check_eligibility`,
  `simulate_course_disruption`, `audit_graduation_progress`, `find_requirement_substitutes`
  ALREADY self-fetch the student's record from `student_id` (`resolve_completed_entries`);
  `state` is only for a deliberately-altered what-if. The live failures were the model
  *over-supplying* a malformed `state` it never needed. Fix is a tool-attached note ("pass
  `student_id`; omit `state` unless simulating a what-if"), not a substrate rebuild.
- **No-progress / dedup governors (§7).** The spike re-surfaced the same fact several times and
  wandered toward the turn budget. The rewrite must implement §7's governors: a re-surface of an
  existing fact is a no-op, and a turn producing no new facts counts toward a no-progress cap
  that forces graceful conclusion.
- **Final-answer contract coverage (§4.2/§3.2).** Extend the deterministic backstop from
  numerals/codes to **statuses, semester labels, and offering claims**, and render **certainty**
  (a `predicted_pattern` fact hedged, an `official_record` flat). Specified but not yet
  built/tested.

### 17.3 The one residual behavioral risk to validate first

The **what-if simulation chain** — `mutate_state` (fail a course) → altered `state` →
`check_eligibility` / `simulate_course_disruption` — is the most complex tool-chaining in the
system and the only high-value path still unvalidated end-to-end. Everything the spike proved
retired the *unknowns* (grounding holds; completeness is solvable; fetch/interpret/compute/
select all ground). The what-if chain is where a genuine surprise could still appear, so it is
the first thing to exercise once `select` and the composite notes land. Its "valid-premise"
counterpart — a fail-course question where the course is *not* already taken, so the
hypothetical is real — rides on the same chain.

### 17.4 Deferred against evidence (not blockers)

- **Sub-loops / `spawn_subtask` (§6, §15):** ship single-loop first; enable on the first real
  context-flooding case.
- **Temporal/offering prediction + `predicted_pattern` rendering + the full fail-course-X trace
  (§10):** validate after the core loop and the what-if chain land — it depends on both.
- **Clarification threading (§8.2) + out-of-scope Front Door (§8.1):** build from the existing
  design; low risk, since V1's boundary handler works and is kept. The spike deliberately skips
  the Front Door (raw question → loop), so these are unexercised but not in doubt.

### 17.5 Readiness verdict

**Ready to rewrite — after a short decision pass, not more spiking.** The architectural risk is
retired: one thinking-ON loop, on the demo model (GPT-5-mini), grounds every fact and answers
*both* north-star cases correctly — the arithmetic-fabrication case that cost V1 30 calls and a
made-up number, and the presupposition-completeness case that produced contradictory answers in
V1. What remains is **decisions and known engineering, not unknowns.**

Pre-rewrite checklist:
1. ~~Settle the four §15 forks~~ — **DONE (2026-07-18):** pure loop + Front-Door decompose;
   slot-fill numbers + structured; liberal completeness gate; single-loop v1. (§15)
2. ~~Confirm the two substrate additions~~ — **DONE (2026-07-18):** `select` ships as a **new
   primitive**; composites keep their `student_id` self-fetch and get a tool-note ("omit `state`
   unless simulating a what-if").
3. **Accept the build-during-rewrite list** (§17.2 governors + backstop coverage + certainty
   rendering; §17.4 Front Door + clarification) as known work, not blockers.

**Status: GO.** The checklist is satisfied. Start the rewrite; validate the what-if chain (§17.3)
as the very first thing after the core loop stands, since it is the last place a surprise can hide.

---

## 18. The rewrite — landed, and its live correctness eval (2026-07-18)

The rewrite was executed on branch `rewrite/agent-v2`. This section records what shipped and
what the full 6-case live eval (the same ISE fixture student the spike used) then revealed.

### 18.1 What shipped

- **The loop package** `services/ai/app/agent_core/loop/`: `working_set` (WorkingSet + immutable
  Fact + prompt rendering), `constitution` (lean tier-1 prompt + tool-attached notes), `front_door`
  (decompose into concrete premise sub-asks), `fact_admission` (surface/compute/**select** +
  const-block), `answer_boundary` (deterministic grounding backstop + completeness gate),
  `arg_refs` (argument binding), and `runner` (the loop + budgets + governors + graceful
  conclusion). `run_agent_loop` is the entry point.
- **`select` shipped as a fact-admission operation**, not a registry `ToolDescriptor`: it filters
  an already-grounded working-set fact and must inherit its basis/confidence, which a
  model-authored-args registry tool cannot do. It is the Computed-kind analogue of `project_facts`
  for *which* record.
- **`/advise` runs on the loop** (§11 contract unchanged: `services/api` + the frontend untouched);
  `course_ids`/`sources` derived in code from the loop's tool audit; streaming replaced with typed
  `chunk`+`final` events (the untyped-queue backfill hack deleted).
- **Argument binding (§17.3 fix)** — see 18.2.

### 18.2 The what-if chain was inexpressible — found statically, fixed with arg-binding

The §17.3 residual risk turned out to be an **expressibility** gap, found by static analysis for
zero model spend: `mutate_state`.base_state and `check_eligibility`/`simulate`.state are *fetched
objects the model cannot type*, and the loop had no way to bind a tool argument to a grounded fact.
Fix: a tool argument of the exact form `{"ref": factKey}` resolves in code to that grounded fact's
value before dispatch (`loop/arg_refs.py`) — the tool-input analogue of `surface_fact`. Grounding
holds end-to-end. The what-if chain now threads a grounded altered state through
`mutate_state → check_eligibility`, proven by a scripted end-to-end test.

### 18.3 Live eval round 1 — the grounding floor holds; wandering is the new failure mode

All 6 `ise_correctness` cases run through `run_agent_loop` on GPT-5-mini
(`tests/agent_core/test_v2_ise_correctness.py`):

| case | outcome | claims | turns/calls/s |
|---|---|---|---|
| credits_remaining | answered | 8/8 | 6 / 8 / 37 |
| eligibility_00960211 | answered | 4/4 | 7 / 9 / 53 |
| presupposition_conflict | budget_exhausted | 3/5 | 12 / 14 / 148 |
| offering_pattern | budget_exhausted | 3/4 | 12 / 13 / 86 |
| completed_courses | clarified | 5/6 | 5 / 6 / 54 |
| action_boundary | budget_exhausted | 3/4 | 11 / 12 / 176 |

- **The grounding floor held 6/6 — zero ungrounded numerals, including the `92.5` case V1
  fabricated.** The architectural thesis (grounding by substrate) is validated live on the demo
  model across the full suite.
- **The new primary failure mode is wandering, exactly as §7 predicted** — not fabrication. Three
  cases hit the budget despite having the answer's facts in hand (presupposition_conflict had the
  selected grade 85; the completeness gate correctly rejected its cop-out first). The no-progress
  governor missed it because redundant re-surfacing under new keys *looks* like progress.
- **Two substrate gaps surfaced:** (a) list projection — `surface_fact` cannot index a list and a
  list slot was rejected as non-scalar, so "list my courses" was unanswerable; (b) a semantic
  mapping gap (term-index 3 → summer) sent `offering_pattern` searching.

### 18.4 Fixes applied (from the round-1 evidence)

1. **Forced compose-from-facts on exhaustion** (`runner._forced_compose`): one bounded LLM call
   composing from ONLY the grounded facts, through the same backstop — recovers the "had the answer,
   ran out of turns" cases. This is §7's "graceful degradation" made real.
2. **List-slot rendering** (`answer_boundary.resolve_final`): a list of scalars slots
   comma-separated, still grounded — this is the §17.2 "extend the backstop coverage" item, for
   lists.
3. **Answer-rejection cap** (`runner`, `REJECTION_LIMIT`): a wanderer that makes fact-progress but
   keeps rejecting its own draft (which no-progress cannot catch) is bounded before it burns the
   budget — the §7 governor the eval proved necessary.
4. Constitution now documents list enumeration (`select` with a field, no `where`) and that
   `surface_fact` paths cannot index a list.

### 18.5 Live eval round 2 (with 18.4 fixes)

| case | round 1 | round 2 | change |
|---|---|---|---|
| credits_remaining | answered 8/8 | answered 8/8 | held |
| eligibility_00960211 | answered 4/4 | answered 4/4 | held |
| completed_courses | clarified 5/6 | **answered 6/6** | **fixed** (list enumeration + rendering) |
| action_boundary | budget 3/4 | **answered 4/4** | **fixed** (forced compose + rejection cap) |
| offering_pattern | budget 3/4 | answered 3/4 | concludes now, but still misses the code |
| presupposition_conflict | budget 3/5 | budget 3/5 | unchanged (hardest case) |

- **Correctness went 2/6 → 4/6; grounding held 6/6 in both runs** (zero fabrication across 12
  case-runs). The thesis is validated twice over.
- **completed_courses fixed cleanly**: `select(field=courseNumber)` enumerated all 17 codes and the
  list slot rendered them — 4 turns, 15s.
- **action_boundary fixed**: the forced compose + rejection cap turned a wandering budget-exhaust
  into a grounded boundary answer that never claims to have registered.
- **Two refinements the round exposed (still open):**
  1. **Forced compose bypasses the completeness gate.** It runs only the grounding backstop, so it
     shipped an `offering_pattern` answer that omitted the course code `00960211` (grounded but
     incomplete). Fix: have the forced compose insist on the question's key entities, or run a
     light completeness check on the composed draft.
  2. **The completeness gate can't distinguish "didn't look" from "looked; no such record."**
     `presupposition_conflict` asks for the student's *this-semester* status of a course that was
     already passed *last* semester — there is no this-semester entry. Every honest draft ("not
     enrolled this semester; passed in 2025-1 with 85") was rejected as a cop-out, looping to
     budget. The gate rule "never accept 'could not determine' for the student's own record" is too
     strict when the record legitimately has no such entry. It also has a real knowledge gap
     (term-index → season) that sent it in circles. This remains the single hardest case.

### 18.6 Rounds 3–4 — the failures were the decomposer, not the loop

Round-3 fixes (completeness-gate wording; the fixed term→season mapping; forced-compose must name
the question's entities) fixed `offering_pattern` but not the two budget cases — and revealed the
real root cause: the **decomposer**. It echoed "this semester" into the presupposition sub-ask (so
the model hunted a current-semester record for a course passed *last* semester and never stated the
real grade), and it inflated `eligibility` into co-requisite / exclusion / department / standing
sub-asks the question never raised, sending the loop chasing them to budget.

Fixes across rounds 4–6: decompose at the root (un-scope premise checks to the course's *actual
recorded status*; enforce minimality); reject `None`-valued answer slots; require final answers to
name the course code(s) and the basis. Six full runs on the demo model:

| case | R1 | R2 | R3 | R4 | R5 | R6 | passed |
|---|---|---|---|---|---|---|---|
| credits_remaining | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | **6/6** |
| completed_courses | 5/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 5/6 |
| action_boundary | budget | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 5/6 |
| offering_pattern | budget | budget | 4/4 | 4/4 | 3/4 | 4/4 | 3/6 |
| eligibility_00960211 | 4/4 | 4/4 | budget | 3/4 | 3/4 | 3/4 | 2/6 |
| presupposition_conflict | budget | budget | budget | 5/5 | 5/5 | budget | 2/6 |
| **correct** | **2** | **4** | **4** | **5** | **4** | **4** | of 6 |

Each fix hit a real root cause and moved the average up, but **none made the two hardest cases
deterministic.** `presupposition_conflict` is the clearest lesson: R4/R6 both drew the *good*
un-scoped decomposition, yet R6 still failed — the model wandered (re-selecting the same record),
hit a transient `json_parse_failed`, and at the budget boundary bound whole *records* to answer
slots instead of the scalar grade 85 it had already grounded. The failures are an accumulation of
*different* stochastic fumbles, not one fixable cause. `eligibility` similarly oscillates between a
full answer (R1/R2) and an over-terse "eligible: True" that omits the prerequisite.

**Honest verdict.** The architecture is validated on the axis that matters: **the grounding floor
held 6/6 on all six runs — 36/36 case-runs, zero fabrication**, including the `92.5` case V1 faked.
Correctness lands **~4–5 of 6 per run**, and every case passes on some run, but a **deterministic
6/6 was not reached in six attempts** — two hard cases (`presupposition_conflict`,
`eligibility`-basis) jitter irreducibly on a temperature-1.0 model (GPT-5 forces temp=1). Further
prompt tuning shows diminishing returns because the residual failures are diverse stochastic fumbles
(wandering, composition slips, transient parse errors), not a single root cause. Closing the last
gap needs either a stronger model or deeper work (a stricter anti-re-derivation governor; a
composition step that can't bind a record to a scalar slot), which is beyond "validate the rewrite."
Net: the V2 thesis — grounding by substrate — is proven; correctness on the demo model is
good-but-variance-bounded, not perfect.

### 18.7 The structural fix — count information, not keys (round 7)

Rounds 4–6 were prompt-tuning (decomposer wording, gate phrasing, constitution nudges) — the exact
layered-design instinct this architecture rejects. The right question was structural: *what code
bug lets the loop wander?* The answer: **the no-progress governor counted new fact KEYS, not new
INFORMATION.** Every budget-exhaustion across the six rounds had one shape — the model re-derived a
value it already held under a fresh key name (`select` the record, then its grade, then the record
again), each looking like a new fact, so the governor never fired and the loop burned all 12 turns
re-deriving, with nothing left to recover at the answer boundary. A prompt cannot fix that; it is a
defect in how progress is measured.

**Fix (structural):** facts are admitted by **derivation signature** — the *operation* (a selector's
handle+path, a select spec, an expression), not the resulting value. Re-performing a derivation
already done still stores the fact (so a `fact_ref` resolves) but is **not progress**, so the
no-progress governor fires within a few turns, the loop concludes early *with budget to spare*, and
the forced compose answers from the facts in hand. The signature keys on the operation, never the
value, so two fields sharing a value (two booleans from one call) are never collapsed
(`WorkingSet.admit_derivation`, unit-tested).

**Round 7 — the falsifiable prediction held:**

| case | outcome | turns | claims |
|---|---|---|---|
| credits_remaining | answered | 8 | 8/8 |
| eligibility_00960211 | answered | 4 | 3/4 |
| presupposition_conflict | answered | 9 | 5/5 |
| offering_pattern | answered | 5 | 4/4 |
| completed_courses | answered | 5 | 6/6 |
| action_boundary | answered | 11 | 4/4 |

**Zero `budget_exhausted` — all six cases concluded** (prior runs had 2–3 budget-outs).
`presupposition_conflict` passed; correctness **5/6**. The single miss, `eligibility` at 3/4, is now
a *concluded, grounded* answer that is merely terse (omits the prerequisite it satisfied) — an
answer-verbosity nuance, not a robustness failure. The lesson generalizes the architecture: the
wandering was retired by making re-derivation structurally a no-op, exactly as fabrication was
retired by making an ungrounded number structurally unrepresentable. **Structural beat prompt,
again.**
