# UniPilot AI — Multi-Agent System (MAS) Capability Map

Last updated: 2026-06-29
Status: **Design / brainstorm consolidation** (pre-planning). No implementation yet.

This document consolidates the autonomous Multi-Agent System (MAS) design for UniPilot:
the agent roster, the coordination protocol, the full capability catalog, data
dependencies, grounding/safety rules, testing strategy, and a phased roadmap.

It is the single source of truth for **what the MAS should be able to do** before we
write a per-feature plan (`.cursor/prompts/02-plan-feature.md`). It does **not** replace
`docs/PROJECT_CONTEXT.md`; where they conflict, PROJECT_CONTEXT and accepted ADRs win.

Related: `docs/PROJECT_CONTEXT.md` (§3, §3.1, §9–10), `docs/planning/FEATURE_BACKLOG.md`
(`AI-1..7`, `DEC-1..3`), `.cursor/rules/unipilot-ai.mdc`, `.cursor/rules/unipilot-security.mdc`.

---

## 0) Master feature & capability list

The complete set of features and capabilities the UniPilot MAS will have. Detailed
design for each lives in the sections below; the **tier** (v1 core / differentiator /
moonshot) and **phase** are defined in §8 and §13.

### A. Core agent runtime & platform
- A1. Asynchronous agent sessions — `POST /agent/sessions` enqueues a job, returns `202 + sessionId`.
- A2. Owner-scoped status/result retrieval — `GET /agent/sessions/:id` and history `GET /agent/sessions`.
- A3. Blackboard coordination runtime in the worker (shared session state in Redis/Mongo).
- A4. Propose → critique → veto → revise negotiation rounds with bounded `maxRounds` + step budgets.
- A5. Utility-based arbitration (explicit objective function over candidate decisions).
- A6. Deadlock handling via soft-preference constraint relaxation with logged trade-offs.
- A7. Deterministic pre-commit validator (rejects ungrounded or rule-violating decisions).
- A8. Persistent negotiation transcript + committed decisions in MongoDB.
- A9. Internal AI service integration (per-agent role prompts; never client-facing).
- A10. AI rate limiting, input validation, timeouts, and bounded retries.
- A11. Human approval gate for irreversible actions — `POST /agent/sessions/:id/approve`.
- A12. Human override capture — `POST /agent/sessions/:id/override`.

### B. Agent roster (specialized autonomous agents)
- B1. Orchestrator / Arbiter (commits the final decision).
- B2. Planner (proposes plans).
- B3. Catalog Scout (feasibility; can veto).
- B4. Risk Sentinel (safety/opportunity cost; can veto).
- B5. Student Advocate (soft preferences).
- B6. Request Analyst (classifies admin/retake requests; finds governing regulation).
- B7. Routing / Liaison (maps request → responsible office; looks up real contact).
- B8. Correspondence Drafter (drafts grounded emails/letters).
- B9. Red-team / Devil's Advocate (attacks the committed plan).
- B10. External Scout (gathers outside-world signals + stages external actions via MCP; no commit, no veto).

### C. Academic planning capabilities
- C1. Next-semester planning.
- C2. Full graduation-path planning (multi-semester).
- C3. What-if simulation (fail a course, switch track, leave a semester, add summer term).
- C4. Track / specialization recommendation.
- C5. Recovery / catch-up planning.
- C6. Schedule conflict resolution (weekly schedule, time-of-day preferences).
- C7. Prerequisite bottleneck / critical-path detection.
- C8. Graduation acceleration (including summer terms).

### D. "Your Representative" — administrative requests
- D1. Administrative-request routing + email draft (overload, prerequisite waiver, course
  substitution, retake permission, leave of absence, credit transfer, accommodations).
- D2. Bureaucracy Navigator (multi-step process decomposition, tracking, and per-step drafts).
- D3. Recommendation-letter concierge (request email + grounded "brag sheet").
- D4. Appeal / re-evaluation drafter.
- D5. Policy Q&A with citations (regulations RAG).
- D6. "No action needed" detection (decides when a request is unnecessary).

### E. GPA improvement & retake
- E1. Retake advisor (which passed courses to retake for max GPA gain per credit-slot).
- E2. GPA-counting-rule grounding (replace vs. average vs. last-attempt, from regulation).
- E3. Retake opportunity-cost analysis (graduation-delay trade-off; may advise against).
- E4. Retake-permission email draft (when approval required).

### F. Proactive & time-aware (acts unprompted)
- F1. Deadline Sentinel (monitors academic-calendar windows; pre-prepares paperwork).
- F2. Registration-day autopilot (assembles a cart at registration open; one-click approval).
- F3. Grade-watcher & probation early-warning (auto-opens a recovery session).

### G. Decision-making & analytics
- G1. GPA back-solver / target planner ("what grades do I need for GPA X").
- G2. Strategy portfolio (fastest / safest / most interesting options).
- G3. Contingency / Plan-B generation.
- G4. Workload forecasting (weekly effort estimate).

### H. Multi-agent mechanics
- H1. Red-team / Devil's Advocate review.
- H2. Live negotiation streaming.
- H3. "Why?" on demand (interrogate any decision from the transcript).
- H4. Self-evaluation / outcome-learning loop (refine utility weights after grades post).
- H5. Second opinion (re-run with different weight profiles).

### I. Interaction & explainability
- I1. Negotiation transcript ("show your work").
- I2. Counterfactual explanation of rejected plans.
- I3. Ranked alternatives.
- I4. Natural-language goal intake (parsed → validated structured goal).
- I5. Side-by-side plan comparison.

### J. Governance & safety
- J1. Hard vs. soft constraints (vetoes vs. negotiable preferences).
- J2. Deterministic pre-commit validator (no invented courses/prereqs/contacts/over-limit plans).
- J3. Bounded authority model (only Arbiter commits; only Scout/Sentinel veto).
- J4. Full audit trail + provenance on every decision.
- J5. Owner-scoped + rate-limited sessions.
- J6. Draft-only for irreversible actions (no auto-send / auto-register).
- J7. Human override that feeds back into future decisions.

### K. External-world connectors (via MCP)
External data is **advisory and untrusted** (never overrides MongoDB facts); external
**actions** are **human-approved** (same gate as draft-only). All connectors use minimal
OAuth scopes, env-loaded secrets, and are exercised only by the External Scout (B10).
- K1. Send + track admin emails (one-click approval; send the drafted petition, track replies, draft follow-ups).
- K2. Advisor meeting booker (find a free slot; draft + send the booking request).
- K3. Career-goal reverse planning (pull in-demand skills/roles; bias electives toward them).
- K4. Faculty-announcement & prereq-change watcher (detect cancellations/moves/prereq changes → reactive re-planning).
- K5. Research / lab matching (match interests to labs/papers/professors for thesis & grad-track students).

---

## 1) Purpose & guiding constraints

UniPilot already has four **deterministic, tested** academic engines:
`graduation_progress`, `semester_planner` (+ manual + weekly schedule + versioning),
`academic_risk` analyzer, and read-only `catalog`. The MAS does **not** replace them —
it **orchestrates them as effectors** while the LLM does only planning, negotiation, and
explanation.

Hard constraints inherited from project rules (non-negotiable):

| Constraint | Source | Implication for the MAS |
|---|---|---|
| The LLM must not invent courses, prereqs, credits, requirements, **or people** | `PROJECT_CONTEXT` §3.1 | Agents act only through deterministic tools; a validator gates every commit |
| Long AI work must be async | `unipilot-ai.mdc` | API enqueues a job (`202 + sessionId`); the **worker** runs the negotiation |
| Internal AI service only | `unipilot-ai.mdc` | LLM reasoning lives in the `ai` container; never client-facing |
| JWT + ownership + rate limiting + validation | `unipilot-security.mdc` | Sessions are owner-scoped, rate-limited, schema-validated |
| MongoDB is the system of record | `PROJECT_CONTEXT` §3.1 | Session state, transcript, and decisions persist in Mongo |

---

## 2) What "autonomous system" means here

The MAS is designed to satisfy the recognized properties of an autonomous system, and we
should be able to point at code for each in the final report.

| Property | How the MAS realizes it |
|---|---|
| Closed perceive → decide → act → observe loop | Blackboard rounds in the worker |
| Goal-directedness | Sessions are created from a student goal + constraints |
| Proactiveness (acts unprompted) | Event-driven sentinels (Deadline Sentinel, Grade-watcher) |
| Reactivity | Re-plans when the student's state changes |
| Persistence / statefulness | `agent_sessions` + transcript + committed decisions in Mongo |
| Self-monitoring & self-correction | Revise-on-critique; self-evaluation loop |
| Bounded authority | Only the Arbiter commits; only Scout/Sentinel may veto |

**Reference model:** the design maps onto the **MAPE-K autonomic loop**
(Monitor → Analyze → Plan → Execute over a shared Knowledge base) — cite this in the report.

**Autonomy level (decided): human-on-the-loop.** The Arbiter auto-commits decisions
*within the deterministic validator's sandbox*; the human can override afterward.
**Exception:** irreversible external actions (emailing real staff, registering) are
**draft-only / one-click human approval** — never auto-executed.

---

## 3) Agent roster

Each agent is a role-specific prompt to the internal `ai` service, paired with the
deterministic engine(s) it is allowed to call. Authority is deliberately split so that no
single agent can unilaterally decide.

| Agent | Viewpoint / goal | Wraps (effectors) | Authority |
|---|---|---|---|
| **Orchestrator / Arbiter** | Drive rounds, resolve conflicts, make the final call | utility function | **commit** |
| **Planner** | Propose a feasible plan that advances graduation | `semester_planner` | propose / revise |
| **Catalog Scout** | Is it real & offered? prereqs, offerings, requirement fit | `catalog` + `graduation_progress` | critique / **veto** (infeasible) |
| **Risk Sentinel** | Is it safe? overload, prereq risk, failure exposure, opportunity cost | `academic_risk` | critique / **veto** (unsafe) |
| **Student Advocate** | Does it respect soft preferences (load, days off, interests, target GPA)? | profile preferences | critique (no veto) |
| **Request Analyst** | Classify administrative/retake requests; find the governing regulation | regulations corpus (RAG) | propose / critique |
| **Routing / Liaison** | Map request type → responsible office/role; look up a **real** contact | `administrative_offices` directory | propose |
| **Correspondence Drafter** | Compose grounded, professional emails/letters (draft-only) | student record + regulation | propose |
| **Red-team / Devil's Advocate** *(optional)* | Attack the committed plan; surface failure modes | all read tools | critique |
| **External Scout** | Gather outside-world signals; stage external actions for approval | external MCP connectors | inform / stage (no commit, no veto) |

**Authority tiers:** hard veto (Scout, Sentinel) > soft pressure (Advocate, Red-team,
External Scout) > commit (Arbiter only). Liaison/Drafter/External Scout never send or act
autonomously — they produce drafts/staged actions for one-click human approval.

---

## 4) Coordination protocol — blackboard + propose / critique / revise

A shared **blackboard** (session state in Redis/Mongo) holds: goal, constraints, current
candidate decision, and all open critiques. Agents contribute in rounds.

```
                 ┌─────────────── BLACKBOARD (shared state) ───────────────┐
                 │  goal • constraints • candidate decision • open critiques │
                 └──────────────────────────────────────────────────────────┘
                        ▲            ▲            ▲            ▲
   ┌────────────────────┘   ┌────────┘   ┌───────┘   ┌────────┘
┌──┴──────┐        ┌─────────┴───┐ ┌──────┴─────┐ ┌───┴───────────┐
│ Planner │        │ Catalog Scout│ │RiskSentinel│ │StudentAdvocate│  (critics run in parallel)
└──┬──────┘        └─────────┬───┘ └──────┬─────┘ └───┬───────────┘
   │ propose                 │ veto/ok    │ veto/ok    │ critique
   └────────────────► ARBITER ◄───────────┴────────────┘
                        │  aggregate + decide (utility)
                        ▼
            consensus? ── no ──► next round (Planner revises)
                        │ yes / max rounds
                        ▼
            deterministic VALIDATOR → commit decision + persist transcript
```

**One round:** Planner proposes → critics independently post structured stances
(`approve` / `critique` / `veto` with `references[]`) → Arbiter aggregates. If an open
veto exists, Planner revises; if only soft critiques remain, Arbiter scores by utility and
decides whether to accept or run another round. Loop ends on **consensus** or **max rounds**.

**Decision rule (utility-based arbitration):**

```
U(plan) = w1·grad_progress_gain
        + w2·prereq_safety
        + w3·load_balance
        + w4·preference_match
        − w5·risk_score
```

**Deadlock policy:** if a hard veto persists and the Planner cannot satisfy it, the Arbiter
relaxes the **lowest-weighted soft preference only**, records the trade-off, and retries.
Hard requirements/safety vetoes are never relaxed.

**Termination guarantees:** hard `maxRounds` + per-agent step budget; the Arbiter always
commits the best-seen valid candidate at the cap.

---

## 5) Architecture mapping (no rule violations)

| Container | Role in the MAS | Host-exposed |
|---|---|---|
| `api` | Validate (Pydantic), rate-limit (Redis), enqueue job → `202 + sessionId`; serve owner-scoped status/result | Yes (only) |
| `redis` | Job queue + blackboard + pub/sub between agents | No |
| `worker` | Orchestration runtime: spins up agents, runs rounds, enforces budgets | No |
| `ai` | Internal LLM service; each agent = a role-specific prompt + tools | No |
| `mongo` | Persists `agent_sessions`, transcript, decisions, job lifecycle | No |

Satisfies "≥2 backend containers", "only API exposed", and "long AI work runs async".

---

## 6) Data model (new)

```text
agent_sessions
  _id, userId, type (planning|admin_request|retake|...), goal, constraints,
  autonomyLevel, status (pending|processing|completed|failed|awaiting_approval),
  finalDecision, utilityBreakdown, rounds, confidence, createdAt, updatedAt

agent_messages            # negotiation transcript (embedded or separate)
  sessionId, round, agentRole,
  action (propose|critique|veto|approve|revise),
  payload, rationale, references[]   # references MUST cite tool outputs

administrative_offices    # NEW grounding data (curated, provenance-flagged)
  _id, office, role, handlesRequestTypes[], officialEmail, scope (faculty|university),
  sourceRef, isCuratedPlaceholder

request_regulation_map    # request type → governing regulation → responsible office
  requestType, regulationRef, officeId, notes

external_actions          # staged/executed external MCP actions (audit + approval)
  _id, sessionId, userId, connector (email|calendar|web|research),
  action, payload, status (staged|approved|executed|failed|declined),
  externalRefs[], approvedBy, createdAt, executedAt
```

Reuses the AI-pipeline **job model** (`AI-3`) for queue states. `completed_courses`
already supports retakes via the unique `(userId, courseId, attempt)` index.

---

## 7) API surface (proposed)

| Method & route | Purpose | Notes |
|---|---|---|
| `POST /agent/sessions` | Start a MAS session (goal/type/constraints) | Validated, rate-limited → `202 + sessionId` |
| `GET /agent/sessions/:id` | Status + final decision + transcript | Owner-scoped |
| `GET /agent/sessions` | History | Owner-scoped, paginated |
| `POST /agent/sessions/:id/approve` | Human approval for irreversible actions | Drafts, retakes, registration |
| `POST /agent/sessions/:id/override` | Record a human override (feeds learning) | Optional |
| `GET /agent/sessions/:id/stream` | Live negotiation stream | Optional (Theme 4) |

All endpoints JWT-protected; AI endpoints rate-limited via shared Redis store (`AI-6`).

---

## 8) Capability catalog

Tier legend: **[core]** v1, **[diff]** differentiator, **[moon]** moonshot/stretch.
Every capability is grounded in MongoDB facts and gated by the validator.

### 8.1 Vertical A — Academic planning

| Capability | Tier | Agents | Data dependency |
|---|---|---|---|
| Next-semester planning | core | Planner, Scout, Sentinel, Advocate, Arbiter | existing |
| Full graduation-path planning | diff | + forward state simulation | existing |
| What-if simulation (fail / switch track / leave / summer) | diff | all (cloned state) | existing |
| Track / specialization recommendation | diff | all | existing |
| Recovery / catch-up planning | diff | all | existing |
| Schedule conflict resolution | core | Scout, Planner | offerings (existing) |
| Prerequisite bottleneck / critical-path detection | moon | Scout, Planner | existing |
| Graduation acceleration (incl. summer terms) | moon | all | offerings (existing) |

### 8.2 Vertical B — "Your Representative" (administrative requests)

Irreversible external action is always **draft-only / human-sent**. Contacts come **only**
from `administrative_offices` — never invented. Policy claims cite the regulations corpus.

| Capability | Tier | Agents | Data dependency |
|---|---|---|---|
| Admin-request routing + email draft (overload, waiver, substitution, retake permission, leave, transfer, accommodation) | diff | Analyst, Routing, Drafter, Scout, Advocate, Arbiter | **`administrative_offices` (new)** + regulations |
| Bureaucracy Navigator (multi-step process tracking + per-step artifacts) | diff | Analyst, Routing, Drafter | process/regulation map (new) |
| Recommendation-letter concierge (request email + grounded "brag sheet") | diff | Drafter, Scout | professor directory (new) or role-based |
| Appeal / re-evaluation drafter | diff | Analyst, Drafter | regulations |
| Policy Q&A with citations | core | Analyst (RAG) | **regulations RAG index (new)** |

A first-class autonomous behavior: the system may **decide no request is needed**
(e.g., the student already satisfies a requirement via cross-track equivalence).

### 8.3 Vertical C — GPA improvement / retake advisor

| Capability | Tier | Agents | Data dependency |
|---|---|---|---|
| Retake advisor (which passed courses to retake for max GPA gain per credit-slot) | diff | GPA Optimizer, Retake Analyst, Sentinel, Scout, Advocate, Arbiter | retake regulation (new) |
| Retake permission email (when required) | diff | Routing, Drafter | `administrative_offices` (new) |

**Grounded math (deterministic):**

```
Δ_course ≈ credits × (grade_new − grade_counted_now) / total_graded_credits
```

Two facts must be grounded, never guessed:
1. **Counting rule** (replace-highest vs. average vs. last-attempt) — from the Technion
   regulation; if absent, flag `manualReviewRequired` and cite the gap.
2. **Future grade is unknown** — treat as a what-if (student target or conservative
   scenario); never fabricate a predicted grade.

Trade-off framing (signature behavior): "Retaking X could raise GPA ~1.8 pts if you score
85+, but the Sentinel estimates a one-semester graduation delay. Approve, or see lighter
alternatives?" The Sentinel may legitimately **advise against** retaking.

### 8.4 Proactive & time-aware (acts unprompted)

| Capability | Tier | Agents | Data dependency |
|---|---|---|---|
| Deadline Sentinel (watch windows; pre-prep paperwork) | diff | Sentinel, Analyst, Routing, Drafter | **academic calendar (new)** |
| Registration-day autopilot (assemble cart at open; one-click approval) | moon | Planner, Scout | calendar + offerings |
| Grade-watcher & probation early-warning (auto-open recovery session) | diff | Sentinel, Planner | existing |

### 8.5 Smarter decision-making

| Capability | Tier | Agents | Data dependency |
|---|---|---|---|
| GPA back-solver / target planner ("grades needed for GPA X") | diff | GPA Optimizer | existing (transcript math) |
| Strategy portfolio (fastest / safest / most interesting) | diff | all | existing |
| Contingency / Plan-B generation | diff | Planner, Sentinel | existing |
| Workload forecasting (weekly effort estimate) | moon | Sentinel | difficulty signal (new/heuristic) |

### 8.6 Multi-agent mechanics (MAS-specific)

| Capability | Tier | Notes |
|---|---|---|
| Red-team / Devil's Advocate agent | diff | New agent that attacks the committed plan |
| Live negotiation streaming | diff | Stream the transcript; killer demo |
| "Why?" on demand (interrogate any decision) | core | Answers from the transcript |
| Self-evaluation / outcome-learning loop | moon | After grades post, refine utility weights |
| Second opinion (re-run with different weight profiles) | core | Risk-averse vs. aggressive |

### 8.7 Interaction & explainability

| Capability | Tier | Notes |
|---|---|---|
| Negotiation transcript ("show your work") | core | Structured record of every move |
| Counterfactual explanation of rejected plans | diff | "Plan B was vetoed for 19-credit overload" |
| Ranked alternatives | diff | Small portfolio instead of one answer |
| Natural-language goal intake | diff | Parsed → validated structured goal (never trusted raw) |
| Side-by-side plan comparison | core | Leverages existing plan versioning |

### 8.8 Governance & safety

| Capability | Tier | Notes |
|---|---|---|
| Hard vs. soft constraints | core | Feasibility/safety = veto; preferences = negotiable |
| Deterministic pre-commit validator | core | Rejects invented courses/prereqs/contacts/over-limit plans |
| Bounded authority model | core | Only Arbiter commits; only Scout/Sentinel veto |
| Full audit trail + provenance | diff | Each decision links to the tool outputs that justified it |
| Owner-scoped + rate-limited | core | JWT; a student only ever touches their own sessions |
| Draft-only for irreversible actions | core | No auto-send / auto-register; human approves |
| Human override that feeds back | diff | Overrides are first-class events |

### 8.9 External-world connectors (via MCP)

External data is **advisory + untrusted** (never overrides catalog/progress facts);
external **actions** require one-click human approval. Owned by the External Scout (B10).

| Capability | Tier | Agents | MCP / service | Guardrail |
|---|---|---|---|---|
| Send + track admin emails | diff | External Scout, Drafter, Routing | Gmail / Email MCP | Send only after `approve`; track replies; draft follow-ups |
| Advisor meeting booker | diff | External Scout, Drafter | Calendar + Email MCP | Slot read-only; booking request sent on approval |
| Career-goal reverse planning | diff | External Scout, Planner, Advocate | Job-market / web MCP | Advisory only; biases electives, never a hard input |
| Faculty-announcement & prereq-change watcher | diff | External Scout, Scout | Web / browser MCP | Read-only; cited; triggers reactive re-plan (no auto-action) |
| Research / lab matching | moon | External Scout, Advocate | arXiv / Semantic Scholar MCP | Advisory; cited; suggestions only |

---

## 9) Grounding & safety rules (must-hold invariants)

1. **No invented facts.** Courses, prereqs, credits, requirements, regulations — all from MongoDB.
2. **No invented people.** Contacts come only from `administrative_offices`; the validator
   rejects any draft addressed to an unverified recipient.
3. **Draft-only externally.** Never auto-email staff or auto-register. Generate a draft +
   `mailto:`/copy; the student sends. One-click human approval for any commit-to-institution.
4. **Cite everything.** Every critique and every email claim carries `references[]` to tool
   outputs (catalog/progress) or a cited regulation.
5. **Validate AI output as untrusted.** Schema-validate before persisting or returning.
6. **Fail safe on uncertainty.** Low confidence or missing data → escalate to the human with
   one specific question instead of guessing.
7. **External data is advisory; external actions are approved.** MCP results may *inform*
   the negotiation but can **never override** a MongoDB fact, and any outbound action
   (send email, book a meeting, watch a course) is staged by the External Scout and executed
   only after one-click human approval. Connectors use minimal OAuth scopes + env-loaded
   secrets; every external call/action is recorded in the audit trail.

---

## 10) Testing strategy (TDD, ≥80% coverage)

- **Unit:** each agent in isolation with a **mocked LLM** but **real deterministic tools**
  (e.g., Sentinel vetoes overload; Scout vetoes missing prereq; validator rejects a
  fabricated course / unverified contact).
- **Integration:** full negotiation driven by a **scripted mock LLM** → assert convergence,
  transcript persisted, ownership enforced, deadlock relaxation logged.
- **E2E:** enqueue → negotiate → poll result; admin vertical produces a draft (no send).
- **Stress:** many concurrent sessions + queue depth; bounded rounds hold under load.
- **Security:** `401/403/400/429`; cross-user isolation; no-fact-invention test; draft-only test.

---

## 11) Risks & mitigations

| Risk | Mitigation |
|---|---|
| Infinite debate / non-termination | Hard `maxRounds` + step budget; commit best-seen at cap |
| LLM cost/latency (agents × rounds) | Parallel critics; cache tool results per session; small model for critics, stronger for Arbiter |
| Hallucinated facts/contacts | Required `references[]` + deterministic pre-commit validator |
| Deadlock (perpetual veto) | Relax lowest-weighted soft preference only; log trade-off |
| Wrong retake/GPA counting rule | Ground in regulation; flag `manualReviewRequired` if absent |
| Embarrassing/wrong emails | Draft-only; student reviews and sends |
| Missing admin directory data | Start role-based; curated seed with provenance flags |
| Non-deterministic tests | Scripted mock LLM; keep deterministic engines real |

---

## 12) New data dependencies (the real cost)

| Data set | Needed by | Status / approach |
|---|---|---|
| Regulations RAG index | Policy Q&A, admin/retake/appeal verticals | Anticipated in §3.1; vault already contains regulations text |
| `administrative_offices` directory | All admin-request capabilities | **New**; curated + provenance-flagged; start role-based |
| `request_regulation_map` | Routing + Bureaucracy Navigator | **New**; curated |
| Academic calendar | Deadline Sentinel, registration autopilot | **New** |
| Professor directory | Recommendation-letter concierge | **New** or role-based |
| Course difficulty signal | Workload forecasting | **New**/heuristic; optional |
| Retake counting rule | Retake advisor | From regulations corpus |
| Email MCP connector (Gmail/Outlook) | Send + track admin emails, advisor booker | **New**; OAuth, send-on-approval |
| Calendar MCP connector | Advisor meeting booker | **New**; read slots, write-on-approval |
| Web / browser MCP connector | Announcement/prereq-change watcher, career signals | **New**; read-only, cited, advisory |
| Job-market / career MCP or source | Career-goal reverse planning | **New**; advisory only |
| arXiv / Semantic Scholar MCP | Research / lab matching | **New**; advisory only |

---

## 13) Phased roadmap

**Phase MAS-1 (core runtime + first vertical):** agent runtime in the worker, blackboard +
propose/critique/revise, utility arbitration, deterministic validator, transcript,
owner-scoped async API, and **next-semester planning**. Realizes `AI-1..7` + `DEC-1`.

**Phase MAS-2 (differentiators on the same runtime):** what-if (`DEC-2`), strategy portfolio,
contingency, second opinion, counterfactual explanation, "Why?" on demand, GPA back-solver.

**Phase MAS-3 (Your Representative vertical):** regulations RAG + Policy Q&A, then
admin-request routing + email draft, then Bureaucracy Navigator / appeal / rec-letter.

**Phase MAS-4 (GPA / retake vertical):** retake advisor + retake-permission email.

**Phase MAS-5 (proactive autonomy):** Deadline Sentinel, Grade-watcher/probation,
registration autopilot.

**Phase MAS-6 (adaptive / showcase):** self-evaluation learning loop, live negotiation
streaming, Red-team agent.

**Phase MAS-7 (external connectors):** External Scout agent + `external_actions` audit +
human-approval execution, then — in order — send/track admin emails (extends MAS-3),
advisor meeting booker, faculty-announcement & prereq-change watcher (feeds reactive
re-planning), career-goal reverse planning, and research/lab matching.

---

## 14) Open decisions (to resolve before planning)

- **Agent roster size for v1** — full 5 (Arbiter + Planner + Scout + Sentinel + Advocate) vs. lean.
- **First decision target** — next-semester (recommended) vs. multi-semester vs. what-if.
- **Capability selection per phase** — confirm the v1 cut from §8.
- **Technion retake/GPA counting rule** — confirm replace vs. average vs. last-attempt (blocks Vertical C math).
- **Admin directory sourcing** — named contacts vs. role-based for v1.
- **Streaming transport** — SSE vs. WebSocket (if live negotiation is in scope).
- **MCP connector providers** — which concrete servers for email (Gmail vs. Outlook),
  calendar, web, job-market, and research; and how secrets/OAuth are provisioned per student.

---

## 15) Backlog mapping

| Backlog item | Covered by |
|---|---|
| `AI-1` Redis job queue + worker consumer | MAS-1 runtime |
| `AI-2` Internal AI service integration | MAS-1 (`ai` per-agent prompts) |
| `AI-3` Job model + states | MAS-1 (`agent_sessions` + job lifecycle) |
| `AI-4` Enqueue endpoint (202 + job id) | MAS-1 (`POST /agent/sessions`) |
| `AI-5` Job status/result endpoint | MAS-1 (`GET /agent/sessions/:id`) |
| `AI-6` Rate limiting on AI endpoints | MAS-1 (shared Redis store) |
| `AI-7` AI response validation + timeouts/retries | MAS-1 (validator + bounded retries) |
| `DEC-1` Course/path recommendation | MAS-1 / MAS-2 |
| `DEC-2` What-if scenario analysis | MAS-2 |
| `DEC-3` Decision history per student | MAS-1 (`GET /agent/sessions`) |
