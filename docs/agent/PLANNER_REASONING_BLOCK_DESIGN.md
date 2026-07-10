# Planner reasoning-block design

**This document locks in the design of the Planner's internal reasoning-block architecture** —
how the Planner actually calls an LLM, not what it produces (that's `PLANNER_OUTPUT_DESIGN.md`,
which this document assumes and builds on). Like that document, it preserves the reasoning and the
mistakes each decision was chosen to avoid, not just the conclusions, and records what live
evaluation against a real LLM actually found — including two real prompt-quality bugs it caught
and fixed, since "good prompts" was the explicit bar this work was held to, not just "code that
runs."

This document describes the **implemented** state (unlike `PLANNER_OUTPUT_DESIGN.md`, which
described a target design ahead of implementation) — `planning/planner.py` and
`planning/schemas.py` are the actual current source of truth for exact field names and instruction
text; this document explains *why* they're shaped the way they are.

---

## 1. Why this migration happened

Before this work, the Planner ran on `reasoning/reasoning_block.py`'s `ReasoningBlock` — a single,
generic runtime shared by every component: a fixed 3-pass ("understand → draft → final") loop,
risk-level-driven iteration counts, and one shared response envelope
(`status`/`summary`/`key_factors`/`tool_requests`/`confidence`/`result: dict[str, Any]`) regardless
of what the caller actually needed. Request Understanding had already migrated off this onto
`reasoning_blocks/base.py`'s `BaseReasoningBlock` — an ABC where each component owns its own
`_run_internal` freely (single-shot, tool loop, self-reflection, multi-persona, whatever fits) and
returns a genuinely typed `Output`, not a dict.

The old runtime was actively costing the Planner correctness, not just elegance: `planner.py` had
to manually unpack `result.get("plan_status", ...)`, `result.get("next_steps") or []` from an
untyped blob, and the old `ReasoningBlock` itself carries a heuristic
(`_unwrap_repair_candidate`, sniffing dict keys like `"plan_id"`/`"user_goal"` to guess whether a
result is nested) that exists specifically because its generic envelope makes "is this the top-level
object or something wrapped inside it" ambiguous. `BaseReasoningBlock` removes the reason that kind
of hack needs to exist.

## 2. `RequestUnderstandingReasoningBlock` is the template, not a rule

The Planner's migration follows RU's own shape closely — same base class, same
`_run_internal`/`_to_output`/`_fallback_output`/`_failed_output` structure, same
`PromptContract`/`PromptRegistry` pattern. But three places diverge, each for a reasoned, specific
reason rather than by default:

### 2.1 Raw and final output stay separate types (RU collapses them)

RU has one output type, `RequestUnderstandingReasoningBlockOutput`, because RU's post-processing
(hollow-result checks) only ever needs what the LLM itself returned — nothing external.

The Planner's post-processing genuinely can't do that. `rewrite_step_ids` needs an invocation
number and the set of already-known global step ids (`PLANNER_OUTPUT_DESIGN.md` §4); neither is
derivable from the LLM's own response. So:

- `PlannerReasoningBlockOutput(BaseReasoningBlockOutput)` — what the block itself returns:
  `plan_status`, `plan_summary`, `clarification_question`, `next_steps: list[PlanStepDraft]` (local,
  unresolved labels).
- `PlannerInvocationOutput` — the final, code-validated type (unchanged from
  `PLANNER_OUTPUT_DESIGN.md`), built by `build_next_plan_steps()` *outside* the block, from
  `rewrite_step_ids` + `compute_plan_graph`.

This is a second, independent confirmation of `PLANNER_OUTPUT_DESIGN.md` §4's raw/final split — it
wasn't just the right call for the output *contract*, it maps onto a real seam in the reasoning-block
architecture too.

`check_hollow_result` (empty `next_steps` on `in_progress`, missing question on
`blocked_needs_clarification`) *did* move inside `_to_output`, alongside RU's own hollow-check —
it only needs `plan_status`/`next_steps`/`clarification_question`, all present in the LLM's raw
response, and the rewrite pass never drops whole steps (only edges), so the check is equally valid
before or after rewriting.

### 2.2 Fails closed, not open

RU's `_fallback_output` always fails **open**: pass the raw message through as the one sub-ask,
`in_scope=True`. That's safe because it's fully inert — worst case, a downstream layer wastes a
call on something that should've been declined.

The Planner can't inherit that posture. A fabricated `next_steps` list is a *dispatchable action*
against real state and tools, not an inert pass-through. Every failure path — a raised
`LLMAdapterError`, exhausted schema repair, a hollow result — resolves to
`plan_status="blocked_needs_clarification"` with a real (if canned) question, never a guess.
`status="completed"` even on this path, mirroring RU's own choice: a well-formed "must ask" result
is a valid, actionable output for the Orchestrator, not a hard failure.

### 2.3 Explicitly requests elevated reasoning

RU sets no `thinking_enabled`/`reasoning_effort`, deferring to the adapter's global default —
classification/scope-gating doesn't obviously need elevated reasoning. The Planner sets
`thinking_enabled=True, reasoning_effort="medium"` explicitly, because dependency-completeness is
real multi-step inference and `PLANNER_OUTPUT_DESIGN.md` §6 is explicit that under-declaring a
dependency is unrecoverable downstream — the stakes justify the cost differently than RU's task
does.

**Where this is set matters**: on `PlannerReasoningBlockInput.llm_call_parameters`, at the call
site in `build_next_plan_steps()` — not on the contract. `PromptContract` has no
`reasoning_effort`/`thinking_enabled` field at all; `_resolve_llm_call_parameters` in
`reasoning_blocks/base.py` only ever pulls `temperature` from the contract, everything else passes
through from the request only. This was confirmed by reading the base class directly, not assumed
— an earlier version of this design incorrectly reasoned these could live on the contract.

### 2.4 Sets its own request-level timeout/max_retries

Initially investigated and deliberately declined — `LLMCallParameters`' own docstring already
documented excluding timeout/retry-policy as "no evidenced need," and no hang had actually been
observed across 23 real live invocations at the time. Overridden by explicit instruction: the
Planner should bound its own calls regardless of whether a hang has happened yet, scoped so it
never affects any other component.

This touches more of the stack than `thinking_enabled`/`reasoning_effort` did, because neither
`LLMCallParameters` nor the adapter chain had a timeout/retry concept to plug into at all:
`LLMCallParameters` gained `timeout`/`max_retries` fields (§2.3's same pattern — `None` means "no
override," set only at a specific call site, never a contract default); `LLMAdapter`/`ChatLLMAdapter
.complete_json` gained matching parameters; `build_chat_llm`/`_cached_chat_llm` thread them into the
underlying `ChatOpenAI` construction.

**The client cache had to be widened, not just extended.** `_cached_chat_llm` is an `lru_cache`
keyed on resolved primitive values so identical configurations share one pooled client. Without
adding `timeout`/`max_retries` to that key, the *first* caller to request a given
(model, temperature, thinking_enabled, reasoning_effort) combination would silently win the cache
slot for everyone — a second caller asking for the same combination but a different timeout would
get the first caller's client, not its own. That would have violated the actual requirement
("shouldn't affect other layers") at the caching layer even with every parameter correctly declared
everywhere else.

**A second, real gap found while wiring this through**: `BaseReasoningBlock._repair_schema` built
its own `LLMCallParameters()` from scratch rather than the original caller's `block_input
.llm_call_parameters` — meaning schema-repair attempts silently ignored *every* per-request
override, not just a hypothetical timeout, including the Planner's already-existing
`thinking_enabled=True`/`reasoning_effort="medium"`. Fixed to inherit the original request's
parameters, verified with a test asserting every repair-loop call (not just the first pass) carries
the Planner's own settings.

Concrete values: `timeout=60.0` seconds, `max_retries=2`, set once in `planner.py` (`_TIMEOUT_SECONDS`
/`_MAX_RETRIES`). 60s gives real headroom over what `thinking_enabled=True` +
`reasoning_effort="medium"` calls have actually taken in live-eval (observed well under 30s) while
still bounding a genuine hang; `max_retries=2` makes explicit what the underlying SDK already
defaults to. Verified against the real adapter (not just the fake one, which can't validate that
`ChatOpenAI` actually accepts these kwargs) — one real Planner call and one real RU call, confirming
the Planner's timeout applies and RU's own calls are completely unaffected.

## 3. Single-shot, not a loop or a council

Considered and rejected, not defaulted to:

- **Self-reflection loop** (draft → critique → revise): rejected because the system's own
  invocation rhythm already provides cross-round correction — a bad decision in round N surfaces
  when round N+1 needs something that isn't there, or triggers a Monitor-driven replan. An
  intra-invocation critique loop pays LLM-call cost for something the architecture already buys for
  free. It would also target the wrong failure mode: the likeliest gap (an under-declared
  dependency) is an *omission*, and LLM self-critique is notably weak at catching its own omissions
  specifically, since it has no independent signal for what it silently didn't think of.
- **Multi-persona council/debate**: rejected on a stronger basis than cost. No natural, distinct
  personas exist for this task the way security/performance/correctness are genuinely different
  lenses in code review — manufacturing personas to fit the pattern isn't motivated by the task.
  Worse, reconciling multiple independently-generated plan drafts into one dependency graph
  reintroduces, one level up, exactly the "two co-dependent structures that could fall out of sync"
  risk `PLANNER_OUTPUT_DESIGN.md` §5 already designed against for LLM-generated graph structure.

If live evaluation (§5) ever shows a real, persistent gap, the narrowest justified next step is a
small, targeted second pass asking specifically "does any step need a fact not covered by its own
`depends_on`" — not a generic reflection loop. `BaseReasoningBlock`'s own design (each shape owns
`_run_internal` freely) makes this a contained future change, not a system-wide migration, which is
part of why starting simple here was low-risk.

## 4. LLM call parameters

| Parameter | Value | Why |
|---|---|---|
| `temperature` | 0.1 (contract default) | Matches RU — structured extraction with checkable output (`success_criteria`/`assumptions_to_verify` must be concrete and falsifiable) benefits from low variance, not creative diversity. |
| `thinking_enabled` / `reasoning_effort` | `True` / `"medium"` (set on the input, per invocation) | See §2.3. |
| `model` | unset (adapter global default) | No evidenced need for an override yet; `LLMCallParameters` still documents dropping speculative surface (`max_tokens`/`top_p`) for the same reason — add only when a concrete gap shows up. |
| `timeout` / `max_retries` | `60.0` / `2` (set on the input, per invocation) | See §2.4 — initially declined as speculative, added on explicit instruction, scoped so it never affects RU or any other component. |
| `default_risk_level` / `allowed_context_fields` / `pass_role_instructions` on `PromptContract` | set to RU's same inert defaults | Confirmed unread by `BaseReasoningBlock`'s actual code path — only the old `ReasoningBlock` ever consumed them. Not a live behavioral choice; flagged as shared cleanup debt on `PromptContract` itself, out of scope for this component alone (affects RU's contract too). |

### 4.1 Provider translation is centralized to one file

Prompted by a real, concrete question: development uses one foundation model (DeepSeek), the actual
submission/presentation uses another (a GPT-5-family model) — would the Planner's/RU's own files
need editing for that swap? They shouldn't, and mostly didn't need to: each layer already only ever
expresses *intent* through `LLMCallParameters` (§2.3, §2.4), never a provider-specific shape. The
one place that wasn't yet properly isolated was the *translation* from that intent into an actual
provider's wire format, in `llm_client.py`'s `_cached_chat_llm` — it had exactly one hardcoded
branch (`extra_body={"thinking": {"type": "disabled"}}` to turn reasoning off), which happens to be
DeepSeek's own documented API shape, silently assumed to be universal.

Fixed by extracting `_apply_reasoning_kwargs(kwargs, *, provider, thinking_enabled,
reasoning_effort)` as the one function that branches on `Settings.agent_llm_provider` (a new,
explicit setting — inferring provider from `base_url` contents was considered and rejected as more
fragile than naming it directly). Re-examining the evidence rather than assuming: `reasoning_effort`
passed as a direct kwarg turns out to need *no* per-provider translation at all — it's both
DeepSeek's own confirmed-working mechanism (exercised across every live Planner call this project
has made) and OpenAI's own documented parameter for the same concept. The only genuinely
provider-specific piece is the "disabled" opt-out shape, which must never be sent to a provider that
doesn't recognize it (unlike the original code's optimistic assumption that an unrecognized field is
harmlessly ignored). `temperature` is deliberately passed through exactly as requested, never forced
to a fixed value for any provider — if a provider ever rejects a given temperature, that should
surface as a real API error to investigate, not be silently rewritten underneath the caller.

A model/provider swap is now: edit `.env` (key, endpoint, model, `AGENT_LLM_PROVIDER`), and only if
the new provider's mechanism is genuinely novel, add one branch to `_apply_reasoning_kwargs`. No
other file needs to change. Verified against the actually-configured provider with two real calls
(RU, Planner) after the refactor, not just the fake-adapter unit tests added alongside it
(`test_llm_client_reasoning_kwargs.py`).

Two ideas considered and explicitly deferred pending evidence, not built speculatively: bumping
`reasoning_effort` higher specifically on replan invocations (`replan_reason is not None`), and
scaling it with the `confidence` signal now flowing in from RU. Both are plausible; neither has
evidence behind it yet.

## 5. Live evaluation: what it actually found

`tests/agent_core/test_planning_planner_live_eval.py` mirrors
`test_request_understanding_live_eval.py`'s pattern (`pytest -m live`, real `ChatLLMAdapter`,
property-based assertions, deselected by default). This is the only way "are the prompts actually
good" gets a real answer rather than an inferred one — and it caught two genuine prompt gaps, not
just validated the code.

### 5.1 Missing proactive state-fetching for hypothetical/what-if requests

First real run on `PLANNER_OUTPUT_DESIGN.md` §7's own worked example ("what happens if I fail Data
Structures this semester?") produced a well-formed but incomplete 2-step plan (course record +
failure policy) — it never fetched the student's own current academic state, even though the
design doc's own worked-example reasoning says that belongs in round 1 regardless of what the other
facts turn out to say (needed either way for computing dependent-course intersections or the
hypothetical failed state).

Fixed by adding an explicit contract instruction: a hypothetical/what-if request almost always
needs the student's own state fetched as one of the first steps. Re-run on the identical case
confirmed the fix directly — the plan grew to 3 steps, with the student-state fetch first and a
downstream step correctly declaring a dependency on it.

### 5.2 Conservative same-round chunking

A two-sub-asks case ("what courses do I still need" + "am I on track to graduate") initially
produced only fact-gathering steps (profile, record, requirements) and stopped there, deferring the
actual comparison/computation to a later round — even though those computation steps' *shape*
(compare two lists; check progress against a target term) was already fully determined, just not
their *results*. This under-uses `PLANNER_OUTPUT_DESIGN.md` §2's "everything currently knowable, not
an artificially small batch" principle.

Fixed by adding an instruction: if a step's objective can already be fully and precisely written,
include it in the same batch even if it depends on another same-round step's result — only wait
when the step's own *shape* can't yet be determined. Re-run on the same case produced a fully
elaborated plan (fetch → fetch → compare → assess) reaching `plan_status="complete"` in one round.

### 5.3 Confirmed good, comprehensively, after both fixes

A final run exercised all 6 cases together with both fixes active (not just the individual case
that exposed each gap), with full output inspected, not just pass/fail:

- Hypothetical/hard hypothetical query: independent fact-fetches followed by a synthesis step
  depending on all of them.
- Simple single-fact query: correctly trivial, one step, `complete`.
- Genuine ambiguity: blocks with a specific, helpful clarification question (not boilerplate).
- Action request: fetch → eligibility check → a single step that *either* proposes registration
  *or* explains why it can't proceed — never assumes success, satisfies
  `PLANNER_OUTPUT_DESIGN.md` §2's "must end in a proposal, never conclude the action already
  happened" requirement as one well-defined step, not as forbidden plan-level branching.
- Two-overlapping-sub-asks: a clean 4-step DAG with correct, non-duplicated dependencies.
- Existing-state reuse across invocations: correctly referenced the prior global id rather than
  re-fetching or inventing a new local label for it.

### 5.4 A real gap found, but explicitly out of scope

The existing-state case exposed that the Planner has to *guess* at what a prior step actually
returned when reasoning about it — because `orchestrator/loop.py`'s `_build_state_index` today
summarizes a completed step as `f"{status} ({output_schema_name})"` (e.g.
`"succeeded (generic_step_output_v1)"`), with no actual semantic content. This is real,
evidence-backed, and materially limits the Planner's ability to reason about prior results — but it
lives in the orchestrator skeleton, which is disposable and explicitly out of scope for this work
(confirmed directly, not assumed). Recorded here so it isn't lost before that skeleton gets rebuilt.

### 5.5 Full-flow verification, and a real bug found by broadening coverage

Every case in §5.1–§5.4 constructed `PlannerInvocationInput` by hand — never actually called
`understand_request()` and fed its real output through `planner_input_from_understanding()`. That
left the real RU-output → Planner-input boundary completely unexercised against real RU output. A
second live-eval file, `test_turn_live_eval.py`, closes this: raw user message → real RU call →
real mapping → real Planner call, no hand-crafted intermediate objects anywhere. Expanded to 15
diverse cases (prerequisite chains, multi-semester planning, academic-standing risk, minor
feasibility, borderline scope, long rambling multi-concern messages, genuine constraints,
conversation-history follow-ups, direct comparisons) — roughly RU's own established scale (15
cases) rather than the original 6.

Every output was read directly, not just checked for pass/fail. Result: consistently sophisticated,
correctly-sequenced multi-step plans across nearly all 15 — constraint-threading, action-request
safety (fetch → verify → propose, never assumes success), and scope-boundary decisions (including a
genuinely hard borderline case, not just an obvious decline) all held up under real, varied input.

Broadening coverage this way surfaced one real, previously-latent bug in `rewrite_step_ids`:

**Global step-id collisions were never actually guarded against.** `local_to_global` was built as
`{draft.step_id: f"{invocation}{draft.step_id.lower()}" for draft in drafts}` — keyed by the raw
label, but the *value* only depended on the lowercased label. Two drafts with case-differing labels
("A" and "a"), or the model reusing the same local label for two different drafts, would silently
collapse into one identical `step_id` — corrupting every downstream dict keyed by step_id
(`compute_plan_graph`'s `forward`/`dependents`, cross-invocation lookups against
`plan_graph_so_far`). One live case (`long_rambling_multi_concern`) used ten *descriptive* local
labels (`"student_record"`, `"data_structures_policy"`, ...) instead of the contract's instructed
short letters — harmless that run purely because none of the ten happened to collide, not because
anything prevented it.

Fixed in code, not the prompt — consistent with `PLANNER_OUTPUT_DESIGN.md` §4's own argument for why
id-rewriting is code-owned in the first place ("the model only has to solve the actually-hard
problem... code solves the mechanical problem it's actually reliable at"). `rewrite_step_ids` now
assigns and checks global ids per-draft, disambiguating any collision with a numeric suffix and
logging it, never silently merging or dropping a step. Global id uniqueness is now a hard,
code-enforced invariant regardless of what labeling discipline the model actually follows.

A second, milder finding from the same broadened run: `academic_standing_risk` recurred the exact
conservative-chunking pattern §5.2 already fixed once — stopping at two parallel fact-gathering
steps (GPA record, probation policy) without including the comparison step, even though its shape
(compare a value against a threshold) was already fully known. Not a correctness bug — the plan was
still valid, just needed one extra round-trip the architecture already tolerates — but a direct
recurrence of the exact pattern the earlier instruction targets is a stronger signal than ordinary
run-to-run variance. Fixed with a second, concrete instruction covering the specific shape that
failed (comparing a retrieved value against a retrieved threshold/limit), verified by re-running
that exact case: the fixed run correctly added the comparison step, depending on both fact-gathering
steps, in the same round.

### 5.6 Durable evidence, not just terminal output

Every live-eval call now runs through `LoggingLLMAdapter`/`LiveEvalLog`
(`tests/agent_core/live_eval_logging.py`) — a thin, test-only wrapper around the real adapter that
records every prompt, param set, and raw + parsed response, written to
`tests/agent_core/live_eval_logs/*.json` on test-file teardown. Earlier live-eval runs in this
project's history only existed as transient terminal output, inspected once and then lost — this
makes the actual evidence behind "the Planner produces good plans" something reviewable after the
fact, not just a paraphrase of it.

## 6. Deliberately out of scope

Per direct instruction: the current orchestrator implementation
(`orchestrator/loop.py`/`step_prep.py`, `subagents/builder.py`) is disposable skeleton, not a
design constraint for this work and not something this migration builds on. Concretely staying
unfixed, tracked rather than silently dropped:

1. `step_prep.py`'s `context_requirements` isn't constrained to a subset of `PlanStep.depends_on`.
2. `StepPrepOutput.reasoning_params` is computed but never consumed.
3. `orchestrator/loop.py`'s `_build_state_index` gives the Planner too-thin summaries of prior
   results (§5.4).
4. `PromptContract`'s vestigial fields, shared with RU (§4's table).
5. Real Orchestrator-side role assignment — `orchestrator/loop.py`'s `_stopgap_role_for_step`
   keyword heuristic stands in; the real decision (likely its own reasoning-block call, per
   `AGENT_VISION.md` §7) is separate follow-up work, decided the same way this document's own
   design was — deliberately, not bolted on.

`build_next_plan_steps()`'s external signature (`planner_input`, `llm_adapter`, `block_id`,
`invocation`) is unchanged from before this migration, so none of the above required touching
`orchestrator/loop.py` at all.
