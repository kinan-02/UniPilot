# UniPilot — Agentic Features Roadmap

Last updated: 2026-06-28

Brainstorm and implementation queue for **autonomous, multi-agent** capabilities. Pick **one feature at a time**: plan → TDD → tests → security review → update `docs/architecture/ADVISOR_AGENTS.md` (or this file) → commit.

**Related docs**

- Current advisor architecture: `docs/architecture/ADVISOR_AGENTS.md`
- Course backlog (AI jobs, DEC-*): `docs/planning/FEATURE_BACKLOG.md`
- API contracts: `docs/API_SPEC.md`
- Mongo collections: `docs/DATABASE_SCHEMA.md`

**Already implemented (baseline)**

| Capability | Status |
|------------|--------|
| Retrieval orchestrator + graph tools | done |
| Profile specialist sub-agent (`consult_profile_agent`) | done |
| Synthesis agent | done |
| Summarized conversation history (`advisor_conversations`) | done |
| Optional agent trace on `POST /advisor/ask` | done |
| Deterministic engines: graduation progress, semester planner, academic risk | done |

---

## Core design pattern (reuse for every feature)

```
Student intent
  → Orchestrator (LLM + routing)
  → Specialist sub-agents (bounded tools only)
  → Deterministic validators (API / Mongo / graph = source of truth)
  → Synthesis or summary agent
  → Optional: async job (Redis + worker) when slow or multi-step
```

**Principle:** LLMs **plan and explain**; Python, graph engine, and existing APIs **decide** eligibility, credits, and risks.

**Delegation tool naming:** `consult_<domain>_agent(sub_question, reasoning)` on the parent orchestrator.

**MongoDB:** API owns persistence; AI service receives serialized envelopes (no direct DB access).

---

## Implementation tracker

Legend — Priority: **P0** (course-critical), **P1** (high value), **P2** (wow / stretch). Status: `todo` / `in-progress` / `done`.

| ID | Feature | Tier | Priority | Async | Status |
|----|---------|------|----------|-------|--------|
| AGT-1 | Async AI job infrastructure | 1 | P0 | Yes | done |
| AGT-2 | Planning Swarm (planner + progress + risk sub-agents) | 1 | P0 | Partial | done (v1 snapshots) |
| AGT-3 | What-If Simulation Council | 1 | P1 | Yes | done |
| AGT-4 | Explain-the-Engine agent | 1 | P1 | No | todo |
| AGT-5 | Regulation & Rights specialist | 2 | P1 | No | done |
| AGT-6 | Transcript Import Copilot | 2 | P1 | No | todo |
| AGT-7 | Prerequisite Unlock Strategist | 2 | P1 | No | todo |
| AGT-8 | Proactive Watchdog (worker/cron nudges) | 2 | P1 | Yes | todo |
| AGT-9 | Compliance Guard (verifier before response) | 2 | P1 | No | todo |
| AGT-10 | Decision Memory Layer | 2 | P2 | No | todo |
| AGT-11 | Multi-Agent Council (deliberation demo) | 3 | P2 | Optional | todo |
| AGT-12 | Schedule Negotiator | 3 | P2 | No | todo |
| AGT-13 | Office Hours Escalation Packet | 3 | P2 | No | todo |
| AGT-14 | Semester Scout (offering diff alerts) | 3 | P2 | Yes | todo |
| AGT-15 | Career Path Sketcher | 3 | P2 | No | todo |

Maps to course backlog: **AGT-1** → AI-1…AI-7; **AGT-3** → DEC-2; **AGT-10** → DEC-3; **AGT-15** → DEC-1 (lightweight).

---

## Recommended build order

1. **AGT-1** — Async jobs (unblocks long agent loops; graded requirement).
2. **AGT-2** — Planning Swarm (extends current advisor with minimal new surface).
3. **AGT-3** — What-If Simulation Council.
4. **AGT-4** — Explain-the-Engine (fast win on existing UIs).
5. **AGT-5** — Regulation specialist (clean sub-agent split from catalog).
6. **AGT-9** — Compliance Guard (before demo / submission).
7. Pick one **Tier 3** item for final report wow factor.

---

## Tier 1 — Course-aligned, high impact

### AGT-1 — Async AI job infrastructure

**Goal:** Long agent workflows do not block the API.

**Flow**

```
POST /ai/jobs → 202 + jobId
  → redis queue
  → worker (agent loop)
  → ai service
  → MongoDB job states (pending → processing → completed/failed)
GET /ai/jobs/{id} → status + result
```

**Agents**

| Agent | Role |
|-------|------|
| Job Supervisor | Enqueue, retry policy, timeout, failure messages |

**First job types**

- Full degree completion roadmap (multi-semester).
- Deep plan optimization (planner + progress + risk loop).
- Long wiki/regulation research.

**Acceptance**

- Rate limiting on enqueue + poll endpoints.
- JWT + ownership on job documents.
- Worker internal-only; only API exposed.

---

### AGT-2 — Planning Swarm

**Goal:** One student question triggers coordinated use of deterministic planners.

**Example queries**

- “Build a spring plan that keeps me on track and flags risks.”
- “What should I take next semester given my transcript?”

**Orchestrator:** existing retrieval agent (extended).

**New sub-agents (delegate via tools)**

| Sub-agent | Tools (API / internal) |
|-----------|-------------------------|
| Planner | `semester-plans/generate`, suggest-courses, suggest-schedule |
| Progress | `GET /graduation-progress`, curriculum graph |
| Risk | `POST /academic-risks/analyze` |
| Catalog | existing graph retrieval |
| Profile | existing `consult_profile_agent` |

**Synthesis:** merge planner JSON + progress gaps + risk severities into one answer.

**Acceptance**

- Orchestrator chooses sub-agents by intent (not every call runs all agents).
- Numbers in answer match API responses (Compliance Guard friendly).
- Unit tests with mocked API tools; integration test for one swarm path.

---

### AGT-3 — What-If Simulation Council

**Goal:** Structured scenario analysis (course backlog DEC-2).

**Example scenarios**

- Drop course X.
- Switch track / add minor.
- Summer overload.

**Agents**

| Agent | Role |
|-------|------|
| Simulation Orchestrator | Parse scenario → run deterministic diffs |
| Scenario Parser | NL → structured ops (`drop_course`, `add_course`, `change_track`) |
| Impact Narrator | Synthesis over before/after snapshots |

**Deterministic runner (API, not LLM)**

- Recompute graduation progress, plan, risk for hypothetical transcript/plan.

**Optional twist:** **Devil’s Advocate** sub-agent argues the opposite scenario.

**Mongo**

- `simulation_scenarios` (user-owned).
- `simulation_results` (immutable artifacts + summary).

**Acceptance**

- Async run for heavy scenarios (AGT-1).
- Summary stored; raw scenario params validated.

---

### AGT-4 — Explain-the-Engine agent

**Goal:** Natural-language explanation of deterministic outputs already in the app.

**Surfaces**

- Graduation progress page.
- Semester plan view.
- Academic risk report.

**Agent:** **Explainer** — reads JSON snapshot + optional wiki context; no new academic logic.

**API sketch**

- `POST /ai/explain` with `{ artifactType, artifactPayload }` or fetch by id server-side.

**Acceptance**

- Cannot change credits/eligibility numbers — narration only.
- Citations when referencing regulations.

---

## Tier 2 — Creative, practical

### AGT-5 — Regulation & Rights specialist

**Goal:** Policy-heavy questions separated from catalog/schedule retrieval.

**Topics:** grade appeals, ombudsman, leave of absence, student rights.

**Tools**

- `wiki_search`, `wiki_page`
- `cite_sources` (mandatory slugs in response)
- `suggested_contacts`

**Delegation:** retrieval orchestrator calls `consult_regulation_agent` when intent is policy/rights.

---

### AGT-6 — Transcript Import Copilot

**Goal:** Agent-assisted transcript PDF import (extends existing parse + commit).

**Flow**

```
parse preview
  → Reconciliation Agent (preview vs catalog)
  → explain unresolved rows + suggest fixes
  → user commits
```

**Tools:** catalog course lookup, completed-courses schema, parse preview JSON.

---

### AGT-7 — Prerequisite Unlock Strategist

**Goal:** Goal-oriented path to unlock a target course.

**Example:** “Shortest path to unlock 00440148?”

**Sub-agents**

- Graph Walker (prerequisite AST on `AcademicGraphEngine`)
- Profile (completed courses)
- Planner light (ordered mini-plan, not full semester grid)

---

### AGT-8 — Proactive Watchdog

**Goal:** Autonomous nudges without a user question.

**Triggers:** profile change, new semester plan, weekly cron.

**Checks**

- Credits behind track.
- Missing prerequisite for planned course.
- Open high-severity academic risks.

**Delivery:** `ai_recommendations` or `notifications` collection + optional email stub.

**Runs on:** worker (not request thread).

---

### AGT-9 — Compliance Guard

**Goal:** Meta-layer before any agent response reaches the client.

**Validates**

- Eligibility claims vs `evaluate_eligibility`.
- Credit counts vs graduation progress API.
- Course IDs exist in catalog/graph.
- No contradictions with retrieval blocks.

**On failure:** orchestrator revises, downgrades confidence, or adds contacts.

---

### AGT-10 — Decision Memory Layer

**Goal:** Unified memory across advisor summaries, simulations, recommendations (DEC-3).

**Retrieval:** before orchestrator runs, **Memory Agent** fetches relevant past summaries for the user.

**Sources**

- `advisor_conversations.summary`
- `simulation_results` (when built)
- `ai_recommendations` (when built)

---

## Tier 3 — Out-of-the-box (demo / final report)

### AGT-11 — Multi-Agent Council

**Goal:** Visible deliberation for ambiguous decisions.

| Agent | Stance |
|-------|--------|
| Optimist | Best-case path |
| Skeptic | Constraints, failure modes |
| Registrar | Regulations only, citations |
| Chair | Synthesis + confidence + dissent note |

Expose in optional `agentTrace` for grading demos.

---

### AGT-12 — Schedule Negotiator

**Goal:** When semester planner reports conflicts, propose alternatives.

- Swap candidates from catalog.
- Re-check prerequisites + risk.
- Present 2–3 Pareto options (lighter load vs faster progress).

---

### AGT-13 — Office Hours Escalation Packet

**Goal:** When retrieval returns `not_found`, package escalation for a human office.

**Output:** structured packet — question, summary, courses cited, missing info, suggested faculty contact (JSON or PDF stub).

---

### AGT-14 — Semester Scout

**Goal:** Event-driven intelligence on new offering JSON.

- Diff `courses_YYYY_SSS.json` vs previous semester.
- Notify users with bookmarked / maybe-list courses.

**Runs on:** data-engineering hook or worker after ingest.

---

### AGT-15 — Career Path Sketcher

**Goal:** Light DEC-1 — map track → electives → wiki career pages.

**Constraint:** catalog and wiki only; no invented career data.

**Mongo:** optional `career_goals` (later collection in schema).

---

## What to avoid

| Anti-pattern | Why |
|--------------|-----|
| Fully LLM-planned degrees without deterministic validation | Grading risk; incorrect requirements |
| Storing raw chat when summaries suffice | Contradicts advisor history design |
| Agents with no tools | Does not demonstrate real multi-agent systems |
| External web scraping | Stay on wiki vault + catalog + Mongo |
| AI service direct Mongo access | Breaks architecture boundary |

---

## Per-feature checklist (copy when starting an item)

- [ ] Update architecture diagram (`docs/architecture/ADVISOR_AGENTS.md` or new `AGENT_SYSTEM.md` if multiple orchestrators).
- [ ] API contract in `docs/API_SPEC.md` (routes, schemas, auth, rate limits).
- [ ] Mongo schema + indexes in `docs/DATABASE_SCHEMA.md` if new collections.
- [ ] Repository + service in `services/api`.
- [ ] Agent module(s) in `services/ai`.
- [ ] Unit + integration + security tests (≥80% coverage maintained).
- [ ] README run/test notes if commands change.
- [ ] Mark status in table above + `FEATURE_BACKLOG.md` if overlapping.

---

## Vision (one line for final report)

> UniPilot is a **multi-orchestrator academic OS**: the chat advisor, simulation council, and proactive watchdog share the same graph, profile envelope, and deterministic validators — LLMs coordinate; the backend decides.

---

## Change log

| Date | Change |
|------|--------|
| 2026-06-28 | AGT-1 done: `ai_jobs`, `/ai/jobs`, worker queue consumer, `advisor_deep_plan` job type |
| 2026-06-28 | Initial roadmap from agentic features brainstorm |
