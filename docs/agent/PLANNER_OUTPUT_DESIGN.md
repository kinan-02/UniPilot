# Planner output design

**This document locks in the design of the Planner's input/output contract** — arrived at through a ground-up design discussion that deliberately set aside the current skeleton implementation (`services/ai/app/agent_core/planning/`, `orchestrator/`) and reasoned from first principles: given only Request Understanding's output as input, and given that the Orchestrator is the Planner's only consumer, what should the Planner actually produce? Like [`AGENT_VISION.md`](AGENT_VISION.md), it preserves the reasoning and the specific mistakes each decision was chosen to avoid, not just the conclusions — several of those mistakes were caught by re-examining an already-agreed design, not on the first pass.

This document describes a **target design**, not the current implementation. Auditing the current skeleton against this document (and correcting it) is separate, later work.

---

## 1. Why this redesign happened

Auditing the current skeleton (`planning/schemas.py`, `orchestrator/step_prep.py`, `orchestrator/context_builder.py`, `subagents/builder.py`) surfaced six concrete defects, all in the same two families:

**Misplaced authority:**
- `PlanStep.role` is set by the Planner. Per `AGENT_VISION.md` §7, role assignment is explicitly one of the *Orchestrator's* four structured per-step decisions ("which subagent to assign... is itself one LLM call['s]... structured field"), made fresh at dispatch time with the freshest state — not fixed upfront by the Planner, possibly several plan revisions stale.
- `context_requirements` (step-prep's chosen dependency slice) has no constraint that it be a subset of `PlanStep.depends_on`. Nothing stops the Orchestrator's own step-prep pass from pulling state the Planner never declared as a dependency — contradicting §7.2's own wording ("dependencies **the Planner declared**") and breaking the same least-privilege discipline correctly enforced for `tool_grant_override` (which *is* constrained to narrow, never widen, a role's tool ceiling).

**Dead fields** (computed, never consumed):
- `PlanStep.risk_level` — set by the Planner, read nowhere in the dispatch pipeline.
- `StepPrepOutput.reasoning_params` — computed by step-prep, but `SubagentContextPackage` has no field to carry it forward, and `subagents/builder.py` ignores it anyway, always using `role.default_reasoning_params` unconditionally.
- `PlannerInvocationOutput.anticipated_followup` — explicitly documented as "for the next Planner call's own context," but `orchestrator/loop.py` never threads it into the next invocation's input.

This is the same bug *class* found and fixed once already in Request Understanding (`contract.instructions` never actually reaching the model) — a field that exists in the schema, looks load-bearing, and is silently dropped somewhere between where it's produced and where it should matter. The redesign below is built to not repeat that pattern: every field either has a concrete consumer, or it doesn't exist.

---

## 2. What the Planner's job actually is

**Given only Request Understanding's output** (`in_scope`, `sub_asks`, `constraints`, `open_questions`, `implies_action_request`, `confidence`, plus the raw message/history for grounding) **— turn the set of distinct information-needs into a sequence of work items that, once executed and accumulated, provide enough grounded material to answer every one of them.** Nothing about *who* executes a step or *how much reasoning budget* it gets is the Planner's concern — that's the Orchestrator's, decided fresh at dispatch time.

### How each Request Understanding field drives planning

- **`sub_asks`** — planned *jointly*, never as independent per-ask sub-plans. Sub-asks routinely share underlying facts (e.g. two different concerns might both need the student's completed-courses record); planning them separately would duplicate steps fetching the same fact twice.
- **`constraints`** — not steps of their own. They get threaded into whichever step's *objective* they actually bear on, not attached indiscriminately to every step.
- **`open_questions`** — the Planner is the first layer that gets to *decide* something about an ambiguity Request Understanding only noticed: proceed with a stated, tracked assumption (recorded in `assumptions_to_verify` so it's auditable, not silently assumed), or treat it as genuinely blocking (`plan_status="blocked_needs_clarification"`).
- **`implies_action_request`** — if true, the plan must end in (or include) a step producing a *proposal*, never conclude by treating a state-changing action as already performed (the vision's `propose_action` human-confirm boundary, §5.1).
- **`confidence`** — a low value is a legitimate reason to schedule a resolving/verifying step early, before committing to a long dependent chain built on a shaky premise.

### Chunk sizing: adaptive means "everything currently knowable," not "few steps"

The Planner is invoked repeatedly, never producing the whole plan upfront (`AGENT_VISION.md` §3.1) — but "the next chunk" is **not** an artificially small or fixed number of steps. It's *everything currently fully and correctly specifiable*, whatever that number happens to be. The worked example below produces 6 steps in its first invocation because all 6 are genuinely independent of anything not yet discovered — deferring any of them to a later round would just be wasted latency, not genuine adaptivity. What must wait is only whatever step's *shape* — not just its timing — actually depends on a result that doesn't exist yet.

This is also why a plan should never be represented as a branching/conditional structure (a decision tree of "if step 2 shows X, do 3a, else 3b"). That would require pre-enumerating outcomes in advance — the same mistake `AGENT_VISION.md` §1 rejects for intents and tools, one level up. Branching happens across *time*, via re-invocation reacting to real results, never as an explicit structure inside one invocation's output.

---

## 3. What's in the Planner's output, and what deliberately isn't

| Field | In Planner output? | Why |
|---|---|---|
| `objective`, `depends_on`, `success_criteria`, `assumptions_to_verify` | Yes | Only the Planner's own reasoning can produce these; no mechanical shortcut exists. |
| `plan_status`, `plan_summary`, `clarification_question` | Yes | Same — genuine judgment. |
| `role` | **No** | The Orchestrator's decision, made fresh at dispatch (§7). |
| `risk_level` / reasoning-block params | **No** | The Orchestrator's decision (role defaults + step-prep's own judgment reading `success_criteria`/`assumptions_to_verify`). |
| `title` | **No** | Redundant with `objective`; a second, lower-stakes version of the "two descriptions that could drift" risk (§7.1's own reasoning for why `prompt_builder` must render, not re-decide). A display layer can truncate `objective`. |
| `anticipated_followup` | **No**, folded into `plan_summary` | A separate field risked becoming a second narrative that could quietly disagree with `plan_summary`. One narrative, not two. |
| explicit graph structure (nodes/edges) | **No**, as *output* from the LLM | See §5 — the LLM output stays adjacency-list style (safe for generation); an explicit graph is only ever *derived by code afterward*, never generated. |

### Role-inference needs a quality bar on `objective`, not a new field

It's tempting to add a "kind of work" hint (fetch/interpret/compute/simulate/compose) so the Orchestrator's role-assignment is easy — but that's role vocabulary by another name, re-opening the exact boundary just closed. The real fix is cheaper: since step-prep is meant to be small and cheap, the objective text itself needs to make the right role obvious from context alone. *"Compute the intersection between the course's dependents and the student's planned courses using already-retrieved facts"* makes role-assignment nearly mechanical; *"handle the Data Structures thing"* would not. This is a discipline on how objectives are written, not a schema change.

---

## 4. LLM output vs. final Planner output — these are not the same object

Mirrors a discipline already used once for Request Understanding (`user_goal` is never LLM output — it's rendered deterministically from `sub_asks`). Applied here more broadly: **the raw LLM output is post-processed by code before it becomes the Planner's actual output.**

### What the LLM produces

- `plan_status`, `plan_summary`, `clarification_question` — as-is.
- Per step: `objective`, `success_criteria`, `assumptions_to_verify` — as-is.
- Per step: `step_id` and `depends_on` — but only as **simple labels local to this one invocation's batch** (e.g. `"A"`, `"B"`), never a final identifier.

**Why `step_id` isn't trusted to the model directly:** it must be globally unique across the *whole plan's lifetime*, not just one invocation — and a collision doesn't fail loudly, it silently resolves a dependency to the wrong accumulated result (state lookups return the *most recent* match for a given id). That's exactly the kind of high-stakes bookkeeping that shouldn't depend on an LLM's own naming discipline holding across multiple separate calls with no shared counter. The model only has to solve the actually-hard problem (what depends on what, using labels it can trivially keep straight within one small batch); code solves the mechanical problem it's actually reliable at.

### What code does before accepting it as final

1. **Rewrite every local label into a globally-unique id** (e.g. `{invocation_number}{local_label}` → `"1a"`, `"1b"`, ...). Rewrite every `depends_on` reference the same pass — some point at local labels in this batch (translated), others may already be real global ids the model copied from what it was shown of the accumulated state (left as-is).
2. **Validate referential integrity** — every `depends_on` entry, after translation, must resolve to a real step (in this batch or already in state). A dangling reference is a hallucinated dependency.
3. **Validate acyclicity within the batch.** Cross-invocation cycles are structurally impossible (time prevents a step from depending on something that doesn't exist yet) — but two steps in the *same* batch mutually depending on each other is a real, checkable risk with no natural prevention.
4. **Hollow-result checks**, extending the same discipline built for Request Understanding: `plan_status="in_progress"` with empty `next_steps` is schema-valid but semantically empty (repair/fallback, not accepted). `plan_status="blocked_needs_clarification"` with no `clarification_question` — same.
5. **Mechanical cleanup** not worth asking the model to get right (e.g. deduping a repeated `depends_on` entry).
6. **Compute the derived graph package** (§5) — never asked of the model, assembled from the now-validated steps.

**Open, not resolved:** how code verifies a `plan_status="complete"` result isn't hollow, given `role` no longer lives in the output — there's no mechanical way left to check "is there a composition-flavored final step" the way the current skeleton does. Flagged, not decided.

---

## 5. The derived graph package — computed by code, never generated by the LLM

Attached to the *final* output, alongside the validated steps — pure derivation from `depends_on`, so it can never drift from the source of truth (same guarantee as `user_goal` in Request Understanding).

```json
"plan_graph": {
  "forward": { "step_id": ["its own depends_on, O(1)-lookup form"] },
  "dependents": { "step_id": ["steps that depend on it -- reverse edges"] },
  "execution_layers": [["steps safe to run concurrently"], ["next layer"], ...]
}
```

- **`forward`** — redundant with each step's own `depends_on`, just collected into one map for O(1) lookup instead of scanning the step list.
- **`dependents`** — genuinely new; nothing today tracks "what relies on this result." This is exactly what the Orchestrator needs for *"X just finished, what's newly unblocked"* and exactly what a replan needs for *"X turned out wrong, what's downstream of it is now suspect."*
- **`execution_layers`** — falls out of the same topological/cycle-check pass code already has to run for validation (§4.3) — not new work, just exposing a byproduct. Tells the Orchestrator directly: run layer 1 concurrently, then layer 2, etc.

**Why this doesn't reopen the "explicit graph is risky" concern raised earlier in discussion:** that concern was specifically about asking the *LLM* to generate two co-dependent structures (a node list and a separate edge list) that could fall out of sync while being written. This graph has no such risk — it's built entirely by code from already-validated data, after the fact. Encoding differs by direction for a reason: adjacency-per-step (what the LLM produces) is safe for *generation*; a fuller graph view (forward + reverse + layers) is safe and useful for *consumption*, and only code needs to produce it.

### On the input side (secondary invocations)

Today, a `PlanStep`'s `depends_on` is discarded after being used once to build that step's context package — nothing about *why* a result exists is preserved in accumulated state. For the Planner to reason over the plan-so-far as a graph on later invocations (not just a flat list of summaries), `depends_on` has to start surviving into whatever compact summary the Planner is shown each round — turning that summary into a real, growing, whole-plan graph (merged in incrementally, one invocation's `plan_graph` at a time) rather than something reconstructed from scratch by re-parsing prose each round.

---

## 6. Planner ↔ Orchestrator interface principles

Reasoned from the *concept* of what an Orchestrator does ("assigns subagents to complete steps, manages execution") — deliberately not from the current skeleton's specific (unfinished, naive) execution code, since that code isn't a settled design either.

- **No ordering requirement on `next_steps`.** A competent orchestrator resolves execution readiness from the dependency graph itself (the same way a build system or task scheduler does) — it doesn't need the producer to have pre-sorted anything. This directly motivates `execution_layers` existing as a first-class derived artifact rather than the Orchestrator needing to re-derive it.
- **`depends_on` must be complete, not approximate.** It's the *only* channel through which the Orchestrator can ever know a step is ready — under-declaring is unrecoverable downstream (nothing can widen it back).
- **`step_id` must stay unique across the plan's whole lifetime.**
- **`objective` must be precise enough that subagent-assignment is nearly mechanical**, regardless of what mechanism the Orchestrator eventually uses to make that call.
- **`success_criteria` / `assumptions_to_verify` must be concrete and checkable/falsifiable** — whatever monitoring mechanism exists needs something real to verify a result against, not a vague hedge.
- **No pre-declared failure branches.** Adaptive replanning (re-invoking the Planner with what actually happened) is how this system handles the unexpected — not conditional structure baked into a single plan output.
- **No parallelism flag needed beyond the graph itself** — safe concurrency is fully derivable from `dependents`/`execution_layers`.
- **No timeout/budget signal from the Planner** — resource allocation is the Orchestrator's own concern once it has picked a subagent for a step, not something the Planner can or should predict.

---

## 7. Worked example

Request Understanding output (real, live-tested) for *"What happens if I fail Data Structures this semester?"*:

```json
{
  "in_scope": true,
  "sub_asks": ["What are the consequences if I fail the Data Structures course this semester?"],
  "constraints": [],
  "open_questions": [],
  "implies_action_request": false,
  "confidence": 0.95
}
```

**A note on what this phrasing actually asks, since it's easy to get wrong:** *"what happens **if** I fail"* is explicitly conditional/hypothetical — the canonical what-if phrasing `AGENT_VISION.md` §3.3 names directly (the same constraint-search engine as semester-plan generation, parameterized by a hypothetically-perturbed starting state via `mutate_state`). It is **not** asking "is my grade actually finalized yet" — that concern belongs to a different, more anxious framing of a real, ambiguous situation ("I think I might be failing..."), not to a question already phrased as a hypothetical. Planning a step to check "is this a real fail yet" here would be answering a question that wasn't asked.

### Invocation 1 — LLM output (local labels)

```json
{
  "plan_status": "in_progress",
  "plan_summary": "Establishing the student's current state, Data Structures' curriculum position and retake policy, and its offering pattern -- and producing a hypothetical failed-state -- before projecting graduation impact, avoidance options, and regulatory risk.",
  "clarification_question": null,
  "next_steps": [
    {
      "step_id": "A",
      "objective": "Retrieve the student's current academic state: completed courses, current program/track, planned/remaining courses for upcoming semesters, and current academic standing (GPA, any active probation warning).",
      "depends_on": [],
      "success_criteria": ["Completed courses list", "Current program/track", "Planned courses for upcoming semesters", "Current GPA and any active standing warning"],
      "assumptions_to_verify": ["The student's profile and completed-course records are up to date"]
    },
    {
      "step_id": "B",
      "objective": "Resolve the exact Data Structures course record, and identify every course that lists it as a prerequisite (its dependents).",
      "depends_on": [],
      "success_criteria": ["Confirmed course record for Data Structures", "Complete list of dependent courses"],
      "assumptions_to_verify": ["'Data Structures' unambiguously refers to one course in this student's program"]
    },
    {
      "step_id": "C",
      "objective": "Determine the retake/failure policy for Data Structures: transcript permanence, retake-attempt limit, replace-vs-add grade -- checking both the general policy and any CS department-specific override.",
      "depends_on": [],
      "success_criteria": ["Transcript-permanence fact", "Retake-limit fact", "Replace-vs-add fact", "Exact wiki source cited for each", "Explicit statement on whether an override applies"],
      "assumptions_to_verify": ["No department-specific override exists unless explicitly found"]
    },
    {
      "step_id": "D",
      "objective": "Determine Data Structures' historical offering pattern (which term-types it has run in recent years) as a basis for predicting retake timing.",
      "depends_on": [],
      "success_criteria": ["Historical term-type pattern with basis period stated", "Explicit distinction between a reliable pattern and an irregular one"],
      "assumptions_to_verify": ["Past offering history is a reasonable basis for near-term prediction"]
    },
    {
      "step_id": "E",
      "objective": "Determine which of Data Structures' dependent courses (from B) are among the student's planned upcoming courses (from A).",
      "depends_on": ["A", "B"],
      "success_criteria": ["Subset of dependents intersecting with planned courses", "Explicit empty result if no overlap, not omitted"],
      "assumptions_to_verify": ["The student's planned courses reflect actual near-term intent"]
    },
    {
      "step_id": "F",
      "objective": "Produce a hypothetical version of the student's state in which Data Structures is marked failed this semester, all else unchanged.",
      "depends_on": ["A"],
      "success_criteria": ["Distinct hypothetical state, separate from the real one", "Differs from the real state only in Data Structures' status this semester"],
      "assumptions_to_verify": ["The current status being modified is a live/undetermined grade, not an already-passed or already-retaken record"]
    }
  ]
}
```

Why only these 6, not §10's full list of concerns: everything else (blocked-course impact on graduation timeline, retake-timing-informed delay projection, avoidance/substitution search, regulatory risk) genuinely depends on C, D, E, or F's actual results — planning it now would mean guessing. These 6 are the complete set of things answerable with zero unknowns remaining.

### Invocation 1 — final Planner output

Same steps, ids rewritten (`A`→`1a`, ... `F`→`1f`) and `depends_on` resolved, plus the derived graph:

```json
{
  "plan_status": "in_progress",
  "plan_summary": "...",
  "clarification_question": null,
  "next_steps": [
    { "step_id": "1a", "depends_on": [], "objective": "Retrieve the student's current academic state...", "...": "..." },
    { "step_id": "1b", "depends_on": [], "objective": "Resolve the exact Data Structures course record...", "...": "..." },
    { "step_id": "1c", "depends_on": [], "objective": "Determine the retake/failure policy...", "...": "..." },
    { "step_id": "1d", "depends_on": [], "objective": "Determine Data Structures' historical offering pattern...", "...": "..." },
    { "step_id": "1e", "depends_on": ["1a", "1b"], "objective": "Determine which dependent courses are on the student's planned path...", "...": "..." },
    { "step_id": "1f", "depends_on": ["1a"], "objective": "Produce a hypothetical failed-Data-Structures state...", "...": "..." }
  ],
  "plan_graph": {
    "forward": {
      "1a": [], "1b": [], "1c": [], "1d": [],
      "1e": ["1a", "1b"],
      "1f": ["1a"]
    },
    "dependents": {
      "1a": ["1e", "1f"],
      "1b": ["1e"],
      "1c": [], "1d": [], "1e": [], "1f": []
    },
    "execution_layers": [
      ["1a", "1b", "1c", "1d"],
      ["1e", "1f"]
    ]
  }
}
```

`execution_layers` tells the Orchestrator directly: run `1a`–`1d` concurrently; once those four are done, run `1e`/`1f` concurrently. Invocation 2 (not built out here) would use `1c`, `1d`, `1e`, `1f`'s results to run the actual consequence-projection chain (graduation-delay projection via `search_over_state` on `1f`'s hypothetical state, substitution/avoidance search, regulatory-risk check) — none of which was knowable until this round returned.

---

## 8. Open questions (flagged, not resolved)

- How code detects a hollow `plan_status="complete"` result now that `role` no longer lives in the output (§4, point 6).
- Whether a plan can get stuck in a way that isn't genuine ambiguity — a dead end no clarification would fix — and whether that needs its own `plan_status` value or can be handled by Composition gracefully explaining what couldn't be determined under `"complete"`. No concrete case has forced this yet; not inventing a fourth status speculatively.
