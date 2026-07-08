# UniPilot Agent — current state

How the live agent system works (as of 2026-07-04). Full design contract: [`Agent_spec.md`](../../Agent_spec.md). RAG tuning: [`RAG_FINE_TUNING_SPEC.md`](RAG_FINE_TUNING_SPEC.md), results: [`RAG_EVALUATION_RESULTS.md`](RAG_EVALUATION_RESULTS.md).

## What it is

A **conversation agent** for Technion students. Students chat at **`/agent`**; the backend is JWT-protected under **`/agent/conversations`**.

**Design rule:** deterministic academic services own truth (graduation progress, catalog, offerings, transcript, plans). The LLM may classify intent, extract preferences, and explain results—it must not invent requirements or silently write student data.

The old multi-agent negotiation stack (`services/mas`, `/agent/sessions`) has been **removed**.

## Service extraction — the agent now runs in its own container

Everything under "orchestrator / intent / entities / context / retrieval /
workflows / response / reasoning / task understanding" described below now
lives in **`services/agent/`** — a separate, internal-only FastAPI service,
never exposed to the host (only `api`/`web` are). `api` keeps:

- The public `/agent/conversations/*` **routes** (auth, rate limiting, JWT).
- Conversation **CRUD** (create/list/get) and message **persistence** for
  the incoming user message — pure Mongo, no LLM/reasoning involved.
- Action **confirm/reject execution** (the actual write for `save_semester_plan`
  / `import_completed_courses`) — unchanged.

```
Browser (/agent)
  useAgentChat + SSE (agentStream.ts)
       │
       ▼
api   POST /agent/conversations/{id}/messages?stream=true
  agent_conversation_service.stream_message_turn
    1. look up conversation, persist the user message (api's own Mongo)
    2. forward the turn to the agent service and stream its SSE straight through
       │  POST http://agent:3003/turn  (X-Internal-Service-Token)
       ▼
agent  orchestrator.run_agent_turn
  1. classify intent (rules → optional LLM fallback)
  2. resolve entities + load conversation memory
  3. build task plan (intent → workflow)
  4. build AgentContextPack (agent's own direct Mongo + wiki RAG)
  5. run workflow (deterministic services; 3 calls stay in api — see below)
  6. compose / optionally LLM-enhance response
  7. persist assistant message (agent's own Mongo) + stream SSE events
       │
       ▼
UI renders text, structured blocks, activity steps, proposed actions
```

Non-streaming clients can omit `stream=true` and receive a single JSON envelope with the same final payload (`text`, `blocks`, `proposedActions`, etc.) — unchanged.

### Data access split

`agent` has its **own direct MongoDB connection** (same physical database as `api`):

- **Read-only** (by convention) on shared academic/student collections: `courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`, `completed_courses`, `student_profiles`, `semester_plans`.
- **Full read/write** on its own collections: `agent_conversations`, `agent_messages`, `agent_runs`, `agent_steps`, `agent_tool_calls`, `agent_action_proposals`.
- It **never** performs the actual write for a proposed action — only creates an `agent_action_proposals` document; `api`'s existing confirm/reject routes execute the write against that same collection.

Three pieces of computation intentionally **stay in `api`** (behind new `/internal/agent/*` endpoints, `X-Internal-Service-Token`-protected) rather than being duplicated into `agent`, because they're complex, actively-evolving business rules also used by `api`'s own plain REST endpoints:

| Endpoint | Wraps | Why it stays in `api` |
|----------|-------|------------------------|
| `GET /internal/agent/graduation-audit/users/{id}` | `graduation_audit_service` + `graduation_progress_calculator` | Same engine as `GET /graduation-progress` |
| `POST /internal/agent/semester-plan-options/users/{id}` | `semester_planning_service` generation | Same engine as `/semester-plans/generate` |
| `GET /internal/agent/course-requirement-contribution` | `requirement_contribution_service` (pool/matrix matching) | Same engine used by catalog/requirement endpoints |

Everything else `agent` needs (catalog lookups, offerings, completed courses, student profile, semester plans, degree-program resolution, transcript-course matching, course-question analysis) is either a direct read from its own Mongo connection or a small, stable, duplicated pure function — no other new endpoints were needed.

## Layers and code map

| Layer | Location | Responsibility |
|-------|----------|----------------|
| UI shell | `services/web/src/pages/AgentPage.tsx` | Layout: sidebar, chat, context panel, composer |
| UI components | `services/web/src/components/agent/*` | Bubbles, blocks, motion, composer, sidebar |
| Client API | `services/web/src/api/agentConversations.ts`, `hooks/useAgentChat.ts`, `lib/agentStream.ts` | Create conversations, stream messages, confirm/reject actions |
| HTTP routes (api) | `services/api/app/routes/agent_conversations.py` | CRUD conversations, messages, cancel run, confirm/reject actions |
| Proxy (api → agent) | `services/api/app/services/agent_conversation_service.py`, `app/clients/agent_service_client.py` | Persist user message, forward turn to `agent`, stream SSE through |
| Internal computation endpoints (api) | `services/api/app/routes/internal_agent.py` | Graduation audit, semester-plan generation, requirement contribution |
| `/turn` endpoint (agent) | `services/agent/app/routes/turn.py` | Internal-only entry point that calls `run_agent_turn` |
| Orchestrator | `services/agent/app/agent/orchestrator.py` | One turn = one run; budgets for steps/tools |
| Intent | `intent_router.py`, `llm_intent_classifier.py` | Rules-first classification; optional LLM fallback |
| Planning | `task_planner.py` | Intent → workflow name + read-only / confirmation flags |
| Entities / memory | `entity_resolver.py`, `conversation_memory.py` | Course numbers, semesters, preferences; assumptions across turns |
| Context | `context_builder.py`, `context_validator.py` | Assemble `AgentContextPack`; fail partial → clarification |
| Retrieval | `services/agent/app/retrieval/*` | Profile, catalog, offerings, hybrid wiki (BM25 + embeddings) — all via `agent`'s own direct Mongo |
| Agentic RAG | `query_decomposer.py`, `retrieval_refiner.py`, `wiki_context_merger.py`, `retrieval_gaps.py` | Multi-step wiki retrieval when enabled |
| Workflows | `services/agent/app/agent/workflows/` | Intent-specific execution |
| Response | `response_composer.py`, `llm_response_composer.py`, `*_response_builder.py` | Text + structured blocks + actions |
| Prompts | `llm_prompts.py` | Centralized LLM system/user prompts |
| Reasoning runtime | `services/agent/app/agent/reasoning/` | Shared multi-pass `ReasoningBlock` (see Phase 1 section below) |
| Task Understanding | `services/agent/app/agent/task_understanding/` | Diagnostic richer-task-understanding agent (see Phase 3 section below) |
| Capability Registry | `services/agent/app/agent/capabilities/` | Typed catalog of workflows/agents/tools/APIs + source-of-truth hierarchy (see Phase 4 section below) |
| Context Compiler | `services/agent/app/agent/context_compiler/` | Minimal, capability-specific context packs (see Phase 4 section below) |
| Planner Agent | `services/agent/app/agent/planner/` | Diagnostic capability-aware execution-plan generator (see Phase 5 section below) |
| Supervisor Runtime | `services/agent/app/agent/supervisor/` | Shadow-only task-graph execution mechanics for a `PlannerOutput`, incl. real read-only workflow adapters, a post-context live-vs-shadow validation layer, and a narrow controlled promotion experiment (see Phase 6/7/8/9 sections below) |
| Specialist Agents | `services/agent/app/agent/specialists/` | Read-only, `ReasoningBlock`-powered specialist workers callable by the supervisor runtime, shadow-only, with deterministic output validation + workflow comparison, and an optional deterministic tool observation layer (see Phase 10/11/12 sections below) |

Everything below this point (Phases 1–3) describes internals that are unchanged in *behavior*, just relocated to `services/agent/`; file paths in those sections are relative to `services/agent/app/` unless noted otherwise.

## One turn in detail

Each user message creates:

1. A **user message** document (and optional PDF attachments).
2. An **agent run** (`agent_runs`) with status `running` → `completed` / `failed` / `requires_user_confirmation`.
3. **Steps** (`agent_steps`) for UI activity (“Understanding your request”, “Gathering academic context”, workflow steps).
4. Optional **tool calls** (`agent_tool_calls`), e.g. `context_builder`.
5. An **assistant message** with text, blocks, warnings, suggested prompts, assumptions, sources.

### 1. Intent classification

`classify_intent` (`intent_router.py`) matches Hebrew/English patterns for:

| Intent | Typical triggers |
|--------|------------------|
| `graduation_progress_check` | “what am I missing”, התקדמות, credits left |
| `transcript_import` | upload/import transcript, ייבא גיליון |
| `semester_plan_generation` | build/plan semester, תכנן סמסטר |
| `semester_plan_modification` | modify plan, remove Friday, lighter plan |
| `course_question` / `prerequisite_check` | can I take X, offered, prerequisites |
| `requirement_explanation` | explain requirement/bucket/elective |
| `general_academic_question` / `catalog_search` | fallback grounded Q&A |
| `unknown_or_unsupported` | empty or unmatched |

If rules are low-confidence and `AGENT_LLM_INTENT_FALLBACK_ENABLED` is on, `llm_intent_classifier` may override.

### 2. Entities and memory

`resolve_entities` pulls course numbers, semester codes, credit limits, avoid-days, etc., and merges them into the conversation’s stored `entities`.

`load_conversation_memory` brings recent turns and **assumptions** (e.g. “assuming next semester is 2025-2”) so later messages stay consistent.

### 3. Task plan

`build_task_plan` maps intent → workflow:

| Intent | Workflow |
|--------|----------|
| graduation_progress_check | `graduation_progress_workflow` |
| course_question, prerequisite_check | `course_question_workflow` |
| transcript_import, completed_courses_update | `transcript_import_workflow` |
| semester_plan_generation / modification | `semester_planning_workflow` |
| requirement_explanation | `requirement_explanation_workflow` |
| everything else | `general_academic_workflow` |

Write-oriented intents set `requires_confirmation=True` so the UI expects a confirm step before persistence.

### 4. Context pack (`AgentContextPack`)

`build_agent_context_pack` loads, in parallel where possible:

- **User context** — profile, degree, catalog year, completed courses (Mongo)
- **Academic context** — graduation progress, catalog rules, offerings for target semester
- **Wiki context** — hybrid retrieval with an intent-specific **retrieval profile** (token budgets, BM25/semantic weights)

When agentic retrieval is enabled (`AGENT_AGENTIC_RETRIEVAL_ENABLED`):

1. Decompose the query into sub-queries  
2. Retrieve wiki snippets per attempt  
3. Merge + detect gaps  
4. Optionally refine and re-retrieve  
5. Optional LLM retrieval validation (`AGENT_LLM_VALIDATION_ENABLED`)

`validate_context_pack` may mark status `partial` (e.g. missing degree). The orchestrator then returns a **clarification** response instead of running the full workflow.

### 5. Workflow execution

Each workflow implements `run(database, context, user_message)` and yields:

- Intermediate `StreamEvent`s (`agent.step.*`) for the activity timeline  
- A final `AgentResponse` (text + blocks + optional `proposed_actions`)

Workflows call existing API services (graduation calculator, catalog, transcript parser, semester plan suggestions)—they do not reimplement academic rules.

### 6. Response finalization

1. Deterministic `compose_response` / workflow builders attach blocks and sources.  
2. If `AGENT_LLM_EXPLANATION_ENABLED`, `enhance_response_with_llm` rewrites **explanation text** only, grounded on the structured payload and context (prompts in `llm_prompts.py`).  
3. Assistant message is persisted; SSE emits `message.delta` / `message.completed`, `structured_output`, `action.proposed`, then `run.completed`.

If `proposed_actions` is non-empty, run status is **`requires_user_confirmation`**.

## Streaming events (SSE)

| Event | UI effect |
|-------|-----------|
| `agent.step.started` / `completed` / `failed` | Activity timeline |
| `tool.started` / `tool.completed` | Tool activity (e.g. context builder) |
| `message.delta` | Streaming assistant text |
| `message.completed` | Final text |
| `structured_output` | Cards (progress, courses, plans, warnings, sources) |
| `action.proposed` | Confirm / reject buttons |
| `run.completed` / `run.failed` | End of turn |

Client: `useAgentChat` applies events into a live turn, then refetches history when the run finishes.

## Structured blocks (UI)

Rendered by `AgentBlocks.tsx`:

| Block | Used for |
|-------|----------|
| `RequirementSummaryBlock` / `RequirementBucketBlock` | Graduation progress |
| `CourseRecommendationBlock`, `PrerequisiteStatusBlock`, `OfferingStatusBlock` | Course questions |
| `TranscriptReviewBlock` | Parsed transcript preview |
| `SemesterPlanOptionsBlock`, `SchedulePreviewBlock` | Plan options + weekly preview |
| `ConfirmationBlock` | Explicit confirm UI |
| `WarningBlock`, `SourceSummaryBlock` | Warnings and provenance |

## Confirmation and writes

Nothing that mutates student records is applied inside the workflow alone.

1. Workflow creates an **action proposal** (`agent_action_proposals`) with type + payload.  
2. SSE sends `action.proposed`; UI shows Confirm / Reject (chat and context panel).  
3. Client calls:
   - `POST .../actions/{actionId}/confirm`
   - `POST .../actions/{actionId}/reject`

Implemented write actions today:

| Action type | Effect |
|-------------|--------|
| `commit_transcript_import` | Persist reviewed transcript rows |
| `save_semester_plan` | Save chosen plan option as a semester plan draft |

Profile/degree/preference updates are classified but not fully wired as write actions yet.

## Persistence (Mongo)

| Collection | Contents |
|------------|----------|
| `agent_conversations` | Per-user threads; title, entities, assumptions |
| `agent_messages` | User/assistant messages; blocks, warnings, actions, sources |
| `agent_runs` | One run per turn; intent, status, retrieval metadata |
| `agent_steps` | Human-readable step log for the run |
| `agent_tool_calls` | Tool invocations (e.g. context builder) |
| `agent_action_proposals` | Pending/confirmed/rejected write proposals |

Ownership is always scoped by `userId` from the JWT.

## HTTP API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/agent/conversations` | Create conversation |
| `GET` | `/agent/conversations` | List conversations |
| `GET` | `/agent/conversations/{id}` | Conversation + messages |
| `POST` | `/agent/conversations/{id}/messages` | Send message (`?stream=true` for SSE); supports multipart PDF |
| `POST` | `/agent/conversations/{id}/runs/{runId}/cancel` | Cancel in-flight run |
| `POST` | `/agent/conversations/{id}/actions/{actionId}/confirm` | Confirm write |
| `POST` | `/agent/conversations/{id}/actions/{actionId}/reject` | Reject write |

Auth: Bearer JWT. Rate limits apply to agent/AI-style endpoints via shared API config.

## LLM configuration

Requires `OPENAI_API_KEY` (and optional `OPENAI_BASE_URL` / `OPENAI_CHAT_MODEL`). Flags in `.env.example`:

| Flag | Default intent | Role |
|------|----------------|------|
| `AGENT_LLM_EXPLANATION_ENABLED` | on when key set | Natural-language explanation over structured results |
| `AGENT_LLM_INTENT_FALLBACK_ENABLED` | on when key set | Intent when rules are unsure |
| `AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED` | on when key set | Preferences (avoid days, credit caps) from chat |
| `AGENT_LLM_VALIDATION_ENABLED` | off | Optional retrieval/answer validation |
| `AGENT_AGENTIC_RETRIEVAL_ENABLED` | on | Multi-step wiki retrieval |

Embeddings for wiki RAG use **separate** `EMBEDDING_*` settings (often a different provider/billing path than chat). All `AGENT_LLM_*`, `OPENAI_*`, and `EMBEDDING_*` settings now belong to the `agent` service (`services/agent/app/config.py`) — `api` no longer reads any of them.

Pytest (in `services/agent/tests/`) sets LLM agent flags **off** for determinism.

## Frontend behavior

- **Empty state:** suggested prompts (graduation, transcript, plan, requirements, course, schedule).  
- **Streaming:** activity steps, typing dots, stream cursor, then blocks.  
- **Context panel:** profile summary, pending actions, assumptions, sources/warnings from the latest turn.  
- **Composer:** text + optional PDF; stop button while streaming.  
- **Motion:** `motion` package with `prefers-reduced-motion` respected.

Nav label “UniPilot Agent” → `/agent`. Path `/agents` redirects to `/agent`.

## How to run

1. `docker compose up --build`  
2. Register / log in; set degree + catalog year on profile  
3. Open `/agent`  
4. Chat in Hebrew or English; attach a transcript PDF for import flows  

## Not implemented yet

- `agent_artifacts` collection  
- Write actions for profile / degree / preference updates (beyond transcript + semester plan)  
- Per-plan-option `requirementCoverage` in all plan blocks  
- Reintroducing multi-agent negotiation (intentionally retired)  
- `services/agent` test coverage is ~78% (below the 80% gate `api` enforces) — reasoning/workflows/retrieval/capabilities/context_compiler/planner/supervisor are well covered; `app/main.py`, a few repository edge branches, and some catalog-matching paths still need tests.
- A few `services/agent` tests have a few seconds of incidental latency from a DNS-resolution attempt to a non-routable hostname during local (non-Docker) runs.

## Reasoning runtime foundation (Phase 1)

`services/agent/app/agent/reasoning/` adds a shared, multi-pass LLM reasoning
runtime (`ReasoningBlock`) — the single call path for LLM-powered agent
components. It reuses the existing `app.agent.llm_client` chat model helpers
(no duplicate OpenAI client setup), runs 2–3 structured reasoning passes with
JSON-schema validation + a repair loop, and returns only structured
summaries (`decision_summary`, `key_factors`, `warnings`, etc.) — never raw
chain-of-thought. See tests in `services/agent/tests/agent/reasoning/` for the
exact contract.

## Reasoning runtime migration — Phase 2

The four existing LLM features now run internally through `ReasoningBlock`
instead of one-shot chat-model calls. Public function names, feature flags,
and fallback behavior are unchanged — this was a compatibility migration,
not a behavior change:

| Feature | Function (unchanged signature) | Contract |
|---------|-------------------------------|----------|
| Intent fallback | `llm_intent_classifier.classify_intent_with_llm_fallback` | `intent_classifier_v1` |
| Preference extraction | `llm_preference_extractor.extract_planning_preferences` | `preference_extractor_v1` |
| Retrieval validation | `llm_answer_validator.validate_retrieval_with_llm` (now a coroutine; `context_builder.py` awaits it directly instead of `asyncio.to_thread`) | `answer_validator_v1` |
| Response explanation | `llm_response_composer.enhance_response_with_llm` / `stream_llm_explanation_deltas` | `response_composer_v1` |
| Grounded general/catalog answers | `workflows/general_academic_workflow._grounded_llm_answer` (found during the Phase 2 call-site sweep; reuses `response_composer_v1`) | `response_composer_v1` |

Each still respects its existing flag (`AGENT_LLM_INTENT_FALLBACK_ENABLED`,
`AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED`, `AGENT_LLM_VALIDATION_ENABLED`,
`AGENT_LLM_EXPLANATION_ENABLED`) and falls back to the exact same
deterministic/rules-based result when the flag is off or the LLM is
unavailable — `ReasoningBlock`/`ChatLLMAdapter` is now the single place that
knows whether an LLM is actually configured, so callers no longer duplicate
an `agent_llm_available()` pre-check.

`app/agent/reasoning/prompt_registry.py` gained four role-specific prompt
contracts (`intent_classifier_v1`, `preference_extractor_v1`,
`answer_validator_v1`, `response_composer_v1`), reusing the existing prompt
text in `llm_prompts.py` rather than duplicating it. A guard test
(`tests/agent/reasoning/test_no_direct_llm_calls.py`) scans `app/agent/` and
`app/retrieval/` for direct LLM call patterns outside
`app/agent/reasoning/llm_adapter.py` (and the low-level `llm_client.py` /
`llm_json.py` it depends on).

**Still not changed:** the orchestrator, workflows, intent routing, `/agent`
route/SSE behavior, and structured block/action shapes are all the same as
before. Production architecture is still not autonomous or multi-agent —
deterministic academic services still own truth; the LLM still only
classifies, extracts preferences, validates, and explains.

**Known pre-existing limitation carried forward:** `_grounded_llm_answer` in
`general_academic_workflow.py` has never been gated by an
`AGENT_LLM_*_ENABLED` flag (only by whether an LLM is configured at all) —
that predates this migration and is a candidate flag-consistency cleanup for
a later phase, not something Phase 2 changed.

## Task Understanding Agent — Phase 3

`services/agent/app/agent/task_understanding/` adds `TaskUnderstandingAgent`
(`understand_user_task`), a diagnostic agent that produces a richer,
structured understanding of a student's request than the rules-first intent
classifier: normalized goal, primary/secondary intents, task category and
complexity, a recommended **autonomy level** (0–5, see
`AUTONOMY_LEVEL_DESCRIPTIONS`), a suggested next layer
(`deterministic_workflow` / `planner` / `clarification` / `unsupported`),
missing context, clarifying questions, and write-confirmation risk.

It uses `ReasoningBlock` exclusively (contract `task_understanding_v1`, risk
`medium`, 3 reasoning passes) — it never calls an LLM directly, never
creates write actions, never retrieves large academic context (only a
capped/minimal context: latest message, up to 6 recent messages, existing
entities/assumptions, deterministic intent/entities, a compact profile
summary, and attachment *metadata* — never attachment contents, full
catalog, transcript rows, or degree requirements), never runs a workflow,
and never decides the final answer.

A `normalizer` reconciles the LLM's output against the existing
`AgentIntent` enum: an unsupported `primary_intent`/`secondary_intents`
value is dropped with a warning and replaced by the deterministic intent (or
`unknown_or_unsupported`) — the agent can never invent a new intent value.
It also flags a strong LLM/deterministic intent disagreement and applies a
conservative explicit-write heuristic on top of whatever the LLM reported.

**It is diagnostic only — not the production routing authority.**
`intent_router.py`, `task_planner.py`, `context_builder.py`, and workflow
selection are unchanged; the live `/agent` response, SSE events, structured
blocks, and action proposals are all still produced exactly as before.

**Feature flags** (both default safe/off, no `OPENAI_API_KEY` required for
either to be inert):

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_TASK_UNDERSTANDING_ENABLED` | `false` | When `false`, nothing in the orchestrator changes and `understand_user_task` returns its deterministic fallback immediately without touching `ReasoningBlock`. |
| `AGENT_TASK_UNDERSTANDING_DRY_RUN` | `true` | Reserved for Phase 4 (whether the output may eventually influence routing). In Phase 3 the agent always runs diagnostic-only regardless of this flag's value. |

**Dry-run orchestrator integration (added):** when the enabled flag is on,
`orchestrator.run_agent_turn` calls `run_task_understanding_dry_run(...)`
once per turn — right after intent classification, entity resolution, and
conversation memory load, before task-plan/workflow selection. The result is
never used to pick a workflow or shape the response; it is only logged
(`task_understanding_dry_run_result`) and attached to the existing free-form
`agent_runs.retrievalMetadata.taskUnderstanding` field (no schema/migration
needed). The call is wrapped so a failure inside it can never break a live
turn. (Coverage note: `understand_user_task` itself has thorough unit
coverage in `tests/unit/test_task_understanding_agent.py`; a dedicated
orchestrator-level flag-on/flag-off SSE-equivalence test for *this specific*
dry-run call was not carried over during the service extraction — the
equivalent pattern is exercised for the Phase 4 capability-diagnostics call
below, in `tests/integration/test_capability_diagnostics.py`.)

## Capability Registry + Context Compiler — Phase 4

Two new, purely deterministic, database/LLM-free packages prepare for Phase
5 dynamic planning without changing any live routing or response behavior:

```
services/agent/app/agent/capabilities/
  schemas.py           CapabilityDescriptor, IO/permission/context contracts
  registry.py          CapabilityRegistry (list/get/require/find_by_*)
  default_registry.py  build_default_capability_registry() — 26 capabilities
  source_of_truth.py   SOURCE_OF_TRUTH_HIERARCHY + rank/compare helpers
  diagnostics.py        optional orchestrator diagnostic hook (see below)

services/agent/app/agent/context_compiler/
  schemas.py            ContextCompilationRequest, CompiledContext
  context_sections.py   the 14 named context sections + forbidden-by-default keys
  reducers.py            pure functions that cap/sanitize each section
  compiler.py            compile_context / compile_context_for_capability
```

**Capability Registry.** `build_default_capability_registry()` returns a
fresh, fully-populated `CapabilityRegistry` describing, as metadata only
(nothing here is executable yet):

- The **6 live workflows** (`graduation_progress_workflow`,
  `course_question_workflow`, `transcript_import_workflow`,
  `semester_planning_workflow`, `requirement_explanation_workflow`,
  `general_academic_workflow`) — `type="workflow"`, `enabled=True`.
- **10 future specialist-agent placeholders** for Phase 5+
  (`task_understanding_agent` — already live, `enabled=True` — plus 9
  `enabled=False` placeholders: `planner_agent`,
  `graduation_progress_agent`, `course_catalog_agent`,
  `semester_planning_agent`, `transcript_import_agent`,
  `requirement_explanation_agent`, `general_academic_rag_agent`,
  `validator_agent`, `response_composer_agent`) — `type="specialist_agent"`.
- The concrete deterministic **`context_validator`** (`type="validator"`)
  and **`response_composer`** (`type="composer"`) that exist today.
- **Tools/retrieval/internal APIs**: `context_builder`,
  `wiki_hybrid_retrieval`, `agentic_wiki_retrieval`, `transcript_parser`,
  `action_proposal_creator`, and the three `api`-side internal endpoints
  (`graduation_audit_internal_api`, `semester_plan_options_internal_api`,
  `course_requirement_contribution_internal_api`).

Every write-sensitive capability (`transcript_import_workflow`,
`semester_planning_workflow`, `action_proposal_creator`, and their Phase 5+
specialist-agent counterparts) declares `write_scope="proposal_only"` and
`can_execute_writes=False` — no capability besides `api`'s own confirm/reject
routes may ever declare `write_scope="direct_write"`.

**Source of truth.** `source_of_truth.py` defines an explicit 9-level trust
hierarchy (`deterministic_api_business_rules` → … →
`llm_interpretation`, most to least trusted) plus
`get_source_of_truth_rank`/`compare_source_trust`/`is_higher_trust` helpers.
Nothing calls these yet — they exist for a future validator/conflict-
resolution step (Phase 5+).

**Context Compiler.** `compile_context_for_capability(request, registry=...)`
takes a `ContextCompilationRequest` (the union of everything potentially
available: user message, task understanding, deterministic intent/entities,
conversation summary/recent messages/entities/assumptions, profile summary,
attachment metadata, `AgentContextPack` summary, wiki snippets, previous
subtask results, and a free-form `extra_context` bucket) and a target
capability name, and returns a `CompiledContext` containing **only** the
sections that capability's `CapabilityContextContract.allowed_context_sections`
permits (fail-closed: an empty allow-list includes nothing).
`forbidden_context_sections` always wins over `allowed_context_sections`.
Deterministic reducers (`reducers.py`) cap recent messages and wiki snippets,
strip attachment contents/full transcript rows/full catalog dumps unless a
capability explicitly opts in, always strip binary blobs (`raw_pdf_bytes`)
and raw Mongo-shaped nested documents (`raw_mongo_document`) regardless of
capability settings, and truncate oversized strings/lists. Every omission of
a would-be-forbidden field produces a compact warning
(`"omitted_forbidden_context: <key>"`) on the result. Not wired into any
live workflow's actual execution — workflows still receive the full
`AgentContextPack` exactly as before.

**Optional diagnostic integration (added, low-risk).** Reuses the existing
`AGENT_TASK_UNDERSTANDING_ENABLED` flag — no new flag was introduced.
Immediately after the Phase 3 dry-run produces a summary,
`orchestrator.run_agent_turn` also calls
`capabilities.diagnostics.build_capability_diagnostics(...)`, which builds a
fresh default registry, looks up capabilities matching the task
understanding's `primaryIntent`, compiles context for `planner_agent`, and
returns a compact summary (`matchedCapabilities`, `targetCapability`,
`includedSections`, `omittedSections`, `warnings`, `estimatedItems` — never
the raw compiled context payload). This is attached to the same free-form
field as Phase 3, `agent_runs.retrievalMetadata.capabilityDiagnostics`,
alongside the existing `taskUnderstanding` key. The call is wrapped in a
broad `except Exception` so a bug here can never break a live turn, and,
like Phase 3, it never selects a workflow, never changes the response, and
emits no new SSE event types. Verified in
`tests/integration/test_capability_diagnostics.py`: flag-off omits both
metadata keys, flag-on attaches a compact `capabilityDiagnostics` summary,
and — critically — toggling the flag produces byte-identical `text`,
`structured_output` blocks, `proposed_actions`, and SSE event-type sequence.

**Tests added:** `tests/unit/test_capability_registry.py` (18 cases —
default-registry construction, required workflow/specialist-agent/internal-
API coverage, duplicate rejection, `get`/`require`/`find_by_*`/`find_enabled`
behavior, write-scope safety), `tests/unit/test_context_compiler.py` (21
cases — allowed/forbidden sections, capping, forbidden-key stripping with
opt-in overrides, sanitization of oversized/nested/binary values, the 3
capability-specific context contracts named in the Phase 4 spec, unknown-
capability and disabled-capability handling), `tests/unit/test_source_of_truth.py`
(8 cases — hierarchy ordering, rank stability, unknown-source handling,
comparison helpers), and `tests/integration/test_capability_diagnostics.py`
(3 cases, described above). The existing direct-LLM-call guard
(`tests/agent/reasoning/test_no_direct_llm_calls.py`) still passes unchanged
— Phase 4 adds zero LLM calls.

**Not done in Phase 4 (intentionally):** neither package controls workflow
selection, executes a capability, or resolves a source-of-truth conflict —
that is Phase 5+ (Planner Agent) and Phase 6+ (supervisor orchestration)
work. The registry does not yet assign `source_of_truth_rank` to every
capability (the field exists and is tested for type-safety, but populating
it meaningfully is deferred until a real consumer — the future validator —
needs it).

## Planner Agent — Phase 5

`services/agent/app/agent/planner/` adds `PlannerAgent`
(`build_execution_plan`), a diagnostic agent that converts a
`TaskUnderstandingOutput` into a structured, capability-aware execution
plan — a task graph of subtasks, dependencies, required context sections,
success criteria, and validation requirements — instead of the current
hardcoded `intent -> workflow` mapping.

```
services/agent/app/agent/planner/
  schemas.py         PlannerInput, PlannerOutput, PlannerSubtask
  agent.py           build_execution_plan() — the main entry point
  normalizer.py       validates/repairs the LLM's plan against CapabilityRegistry
  legacy_mapping.py   maps task_planner.py workflow names -> capability names
  diagnostics.py       optional orchestrator diagnostic hook (see below)
```

It uses `ReasoningBlock` exclusively (contract `planner_agent_v1`, risk
`high`, 3 reasoning passes) — it never calls an LLM directly, never
executes a subtask/tool/workflow, never creates an action proposal, and
never answers the user directly. Its prompt/context is deliberately minimal:
the user message, the Phase 3 task understanding output, deterministic
intent/entities, conversation entities/assumptions, a compact enabled-only
`CapabilityRegistry` summary, the current deterministic `TaskPlan` (as
`legacy_workflow_plan`), and a profile summary — never full academic
context, raw catalog data, or transcript rows.

**Deterministic fallback.** When the feature flag is off, the LLM is
unavailable, reasoning fails, or the LLM's plan can't be normalized into
something usable, `build_execution_plan` returns a single-subtask plan that
mirrors the *current* deterministic `task_planner.py` selection
(`execution_mode="deterministic_workflow"`, one subtask running the mapped
capability, `source="deterministic_fallback"`) — the planner never leaves
the caller without a plan.

**Normalization (`planner/normalizer.py`).** The LLM's raw plan is treated
as untrusted input and reconciled against the live `CapabilityRegistry`
before use:

- Every subtask's `capability_name` must exist **and be enabled** in the
  registry — an unknown or disabled (Phase 4 placeholder) capability's
  subtask is dropped with a warning, not silently kept or invented.
- Subtask ids must be unique; duplicates are dropped.
- Dependencies must reference a surviving subtask id and never point at
  themselves; invalid edges are stripped with a warning.
- The dependency graph is checked for cycles (DFS-based); a cycle makes the
  whole plan unusable and triggers the deterministic fallback.
- `required_context_sections` are filtered to known
  `context_compiler.context_sections` values.
- `primary_intent` must be a supported `AgentIntent` value (same
  reconcile-or-fall-back-to-deterministic-intent pattern as Phase 3's
  `TaskUnderstandingAgent`).
- A `propose_action` subtask, or one whose title/objective reads like an
  explicit write ("save", "commit", "import", "update", etc.), forces
  `requires_user_confirmation=True` at both the subtask and plan level and
  upgrades `write_risk` to at least `"possible"` (`"explicit"` when the
  *user's own message* used an explicit write verb) — mirroring the same
  heuristic already used in `task_understanding/normalizer.py`.
- If every subtask in a candidate plan was invalid, or a cycle survives
  edge-stripping, normalization returns `None` and `build_execution_plan`
  falls back to the deterministic plan.

**Context Compiler usage.** The planner never executes a subtask, but
`planner/diagnostics.py` runs `context_compiler.compile_context_for_capability`
for each planned subtask to *preview* what that capability's
`CapabilityContextContract` would actually let through — included sections,
omitted sections, warnings, and a rough item count only. The raw compiled
context payload is never included in the stored preview.

**It is diagnostic/dry-run only — not the production planning authority.**
`task_planner.py`'s `intent -> workflow` mapping, `intent_router.py`,
`context_builder.py`, and workflow selection are all unchanged; the live
`/agent` response, `/turn` contract, SSE events, structured blocks, and
action proposals are produced exactly as before Phase 5.

**Feature flags** (both default safe/off, no `OPENAI_API_KEY` required for
either to be inert — independent of the Phase 3/4 flag):

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_PLANNER_ENABLED` | `false` | When `false`, `build_execution_plan` returns the deterministic fallback plan immediately without touching `ReasoningBlock`. |
| `AGENT_PLANNER_DRY_RUN` | `true` | Phase 5 **always** runs diagnostic-only regardless of this flag's value — if it's ever set to `false`, a `planner_dry_run_disabled_but_execution_not_implemented_in_phase5` warning is added to the plan instead of silently ignoring the misconfiguration (there is no execution engine yet). |

**Dry-run orchestrator integration (added).** Independently of the Phase
3/4 flag, when `AGENT_PLANNER_ENABLED=true`, `orchestrator.run_agent_turn`
calls `run_planner_dry_run(...)` once per turn — right after the
deterministic `task_plan = build_task_plan(classification)` line (so the
`legacy_workflow_plan` summary reflects the actual live selection). It
works with or without Phase 3 having run (falls back to
`deterministic_intent` + `legacy_workflow_plan` when there's no task
understanding summary). The result is never used to pick a workflow or
shape the response — only logged (`planner_dry_run_result`) and attached to
`agent_runs.retrievalMetadata.plannerDiagnostics` (a compact summary:
status, plan id, execution mode, primary intent, subtask count/capability
names, confirmation/write-risk, missing context, warnings, confidence, and
per-subtask context previews — never raw compiled context or chain-of-
thought). The call is wrapped so a failure inside it can never break a live
turn. Verified with a dedicated integration test comparing flag-off and
flag-on runs of the same message: identical `text`, `blocks`, `warnings`,
`proposedActions`, and SSE event-type sequence
(`tests/integration/test_planner_diagnostics.py`).

## Supervisor Orchestrator Runtime — Phase 6

`services/agent/app/agent/supervisor/` adds a runtime that takes a
normalized `PlannerOutput` (Phase 5) and executes its subtask graph
**mechanics** — dependency ordering, per-subtask context compilation,
handler dispatch, blackboard updates, retries, budgets, and compact
diagnostics — as a controlled shadow run. It is **shadow/dry-run only**:
every built-in Phase 6 handler is a safe stand-in that validates a
capability and previews its context, then reports "not executed yet" —
nothing here calls a real workflow, a real internal API, writes to Mongo,
or creates an action proposal. Real capability execution is Phase 7 work.

```
services/agent/app/agent/supervisor/
  schemas.py           SupervisorRunInput/Output, SubtaskExecutionRecord, SubtaskResult, ExecutionBudget
  errors.py             typed structural errors (invalid plan, duplicate id, unknown dependency, cycle)
  graph.py               ExecutionGraph — validates + orders PlannerSubtask dependencies
  blackboard.py          SupervisorBlackboard — compact, sanitized run-scoped shared state
  handlers.py             DryRunCapabilityHandler, ContextPreviewHandler, UnsupportedCapabilityHandler
  handler_registry.py     SubtaskHandlerRegistry — resolves a handler by capability name/type
  controller.py           decide_next_action() — deterministic continue/retry/skip_dependents/fail_run
  budgets.py               BudgetTracker — enforces max_subtasks/retries/runtime/context-previews
  runtime.py               run_supervisor_shadow() — the main entry point
  diagnostics.py           optional orchestrator diagnostic hook (see below)
```

**Execution graph (`graph.py`).** `ExecutionGraph.build(subtasks)` validates
unique subtask ids, that every `depends_on` references an existing subtask,
and that no dependency cycle exists (DFS-based detection) — raising a typed
`errors.py` exception for any violation, which the runtime turns into a
`status="failed"` output rather than raising. `topological_order()` (Kahn's
algorithm) produces a single, deterministic, dependency-respecting
execution order — ties between simultaneously-ready subtasks are broken by
original plan declaration order. Phase 6 always executes **sequentially**
through that order; no concurrency was introduced.

**Blackboard (`blackboard.py`).** `SupervisorBlackboard` holds only compact
summaries for one run: the original message, a compact plan summary (id,
execution mode, primary intent, subtask count — never the raw subtask
graph), profile summary, per-subtask results, warnings/errors/assumptions/
sources, and validation notes. Every value passed to `add_subtask_result`
is run through the same deterministic sanitizer the Phase 4
`ContextCompiler` uses (`context_compiler.reducers.sanitize_context_value`)
as defense-in-depth against a misbehaving handler trying to stuff something
large/unsafe in — no raw LLM prompts, chain-of-thought, raw compiled
context, raw PDFs/transcript rows, full catalog dumps, or large Mongo
documents are ever stored.

**Handlers (`handlers.py`, `handler_registry.py`).** Three built-in,
always-safe handlers:

| Handler | Used for | Behavior |
|---------|----------|----------|
| `DryRunCapabilityHandler` (default) | Any enabled capability without a more specific handler | Confirms the capability + compiled context, returns a `"completed"` result with `output_summary.dryRun=true` and a message noting real execution is deferred to Phase 7 |
| `ContextPreviewHandler` | `retrieval`/`validator`/`composer` capability types | Reports only the compiled-context preview (included/omitted sections, estimated items) — no capability-specific "work" is even simulated |
| `UnsupportedCapabilityHandler` | Unknown or disabled capability names | Always returns `"skipped"` with a `unsupported_capability` warning — never raises |

`SubtaskHandlerRegistry.resolve(capability_name, capability_type)` checks a
per-name override first, then a per-type default, then falls back to the
registry's own default handler — Phase 7 can register real
workflow-adapter/specialist-agent handlers by capability name without
changing this interface.

**Controller (`controller.py`).** `decide_next_action` is a small,
deterministic decision function (no LLM) that maps a subtask's result +
budget state to one of `continue` / `retry` / `skip_dependents` /
`fail_run`: a completed/skipped subtask continues; a failed subtask retries
while budget remains; otherwise a single-subtask plan's failure fails the
whole run, while a multi-subtask plan's failure only skips that subtask's
dependents (independent branches still complete). No optional LLM
controller contract was added in Phase 6 — the spec allows one only if
purely optional/disabled-by-default, and a deterministic controller was
sufficient and simpler.

**Budgets (`budgets.py`).** `BudgetTracker` enforces
`max_subtasks`/`max_retries_per_subtask`/`max_total_retries`/
`max_runtime_ms`/`max_context_previews` (defaults: 20 / 1 / 5 / 30000 / 20).
Exceeding `max_subtasks` or `max_runtime_ms` stops the run immediately
(remaining subtasks marked `skipped`, `status="budget_exceeded"`).
Exceeding the **shared** `max_total_retries` budget specifically (as
opposed to a subtask simply using up its own smaller per-subtask retry
allowance) also stops the whole run as `budget_exceeded` — a subtask
running out of only its own per-subtask retries just fails and lets
independent branches continue (`completed_with_warnings`).

**Context Compiler usage.** For every subtask (up to
`max_context_previews`), the runtime calls
`context_compiler.compile_context_for_capability` using the subtask's
`capability_name` and stores only a compact preview on its
`SubtaskExecutionRecord.context_preview` (`includedSections`,
`omittedSections`, `warnings`, `estimatedItems`) — never the raw compiled
context, in `SupervisorRunOutput` or in orchestrator diagnostics.

**It is shadow/dry-run only — not the production execution authority.**
`task_planner.py`'s `intent -> workflow` mapping, `intent_router.py`,
`context_builder.py`, and live workflow execution are all unchanged; the
live `/agent` response, `/turn` contract, SSE events, structured blocks,
and action proposals are produced exactly as before Phase 6.

**Feature flags** (both default safe/off, no `OPENAI_API_KEY` required for
either to be inert — independent of the Phase 3/4/5 flags):

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_SUPERVISOR_ENABLED` | `false` | When `false`, the orchestrator never calls `run_supervisor_shadow`. |
| `AGENT_SUPERVISOR_DRY_RUN` | `true` | Phase 6 **always** runs shadow-only regardless of this flag's value — if it's ever set to `false`, a `supervisor_dry_run_disabled_but_execution_not_implemented_in_phase6` warning is added instead of silently ignoring the misconfiguration (there is no real execution engine yet). |

**Dry-run orchestrator integration (added).** When
`AGENT_SUPERVISOR_ENABLED=true`, `orchestrator.run_agent_turn` calls
`run_supervisor_dry_run(...)` right after the Phase 5 planner call — but
**only** when planner diagnostics actually produced a plan (there is no
subtask graph to run otherwise; the Phase 5 flag does not need to be on for
this, since `build_plan_with_diagnostics` — a small Phase 6 refactor of the
Phase 5 integration that also returns the full `PlannerOutput`, not just
its compact summary, alongside the unchanged `plannerDiagnostics` value —
already falls back to a deterministic single-workflow plan on its own). The
result is never used to pick a workflow or shape the response — only
logged (`supervisor_dry_run_result`) and attached to
`agent_runs.retrievalMetadata.supervisorDiagnostics` (status, plan id,
execution mode, subtask count, completed/failed/skipped subtask ids,
capabilities used, warnings/errors, a small budget snapshot, and a context-
preview count — never raw compiled context or chain-of-thought). The call
is wrapped so a failure inside it can never break a live turn. Verified
with a dedicated integration test comparing flag-off and flag-on runs of
the same message: identical `text`, `blocks`, `warnings`,
`proposedActions`, and SSE event-type sequence
(`tests/integration/test_supervisor_diagnostics.py`).

## Real Capability Handlers / Workflow Adapters — Phase 7

Phase 6's Supervisor Runtime could only ever run safe, always-successful
*dry-run* handlers. Phase 7 adds real execution — still shadow-only — for a
small, explicitly reviewed set of **provably read-only** workflows, using
the exact same live workflow code the production orchestrator already
calls.

```
services/agent/app/agent/supervisor/
  workflow_adapters.py    ReadOnlyWorkflowAdapterHandler — executes a real workflow
  output_summarizer.py     summarize_agent_response() — compact AgentResponse -> dict
  safety.py                 can_shadow_execute_capability() — the hard safety gate
  shadow_compare.py          compare_live_and_shadow_result() — standalone utility (not yet wired)
```

**Capability execution metadata (`capabilities/schemas.py`).** Every
`CapabilityDescriptor` gained a `execution: CapabilityExecutionMetadata`
field (`execution_supported`, `shadow_execution_supported`, `handler_name`,
`side_effect_level: "none"|"proposal"|"write"|"unknown"`,
`safe_for_shadow_execution`) — defaulting to fully conservative
(non-executable, `side_effect_level="unknown"`, unsafe). A capability is
never safe for real execution by omission; it must be explicitly marked
safe in `default_registry.py` after a manual code review.

**Manually reviewed (`default_registry.py`), by reading every workflow's
source in `app/agent/workflows/`:**

| Workflow | Reviewed finding | `execution` metadata |
|----------|------------------|----------------------|
| `graduation_progress_workflow` | Never writes to Mongo, never creates a proposal | `side_effect_level="none"`, `safe_for_shadow_execution=True`, `handler_name="read_only_workflow_adapter"` |
| `course_question_workflow` | Same | Same |
| `requirement_explanation_workflow` | Same | Same |
| `general_academic_workflow` | Same (may call `ReasoningBlock` for `catalog_search`/general questions — the existing, unconditional, pre-Phase-7 Phase 2 migration; no new LLM call was added) | Same |
| `transcript_import_workflow` | Calls `create_agent_action_proposal(...)` on every successful run | `side_effect_level="proposal"`, `safe_for_shadow_execution=False`, `handler_name=None` |
| `semester_planning_workflow` | Calls `create_agent_action_proposal(...)` once per plan option on every successful run | Same as above |

**Safety gate (`safety.py`).** `can_shadow_execute_capability(capability)`
is the single, fail-closed decision point — `True` only when **all** of:
`enabled`, `execution.shadow_execution_supported`,
`execution.safe_for_shadow_execution`, `execution.side_effect_level == "none"`,
`permissions.can_execute_writes is False`,
`permissions.can_create_action_proposals is False`, and
`permissions.write_scope == "none"`. This is checked **every time**, not
just at registry-construction time — even a hypothetical custom registry
that mapped an unsafe capability name to the real adapter is still refused
by the runtime.

**Workflow adapter (`workflow_adapters.py`).**
`ReadOnlyWorkflowAdapterHandler` looks up the real workflow via
`workflows.registry.get_workflow` (the exact live lookup — injectable for
tests) and calls its existing `run(database, context=..., user_message=...)`
async-generator interface, collecting every intermediate `StreamEvent` and
discarding it (never emitted anywhere, never persisted) until it yields the
final `AgentResponse`. Defense in depth: if that response unexpectedly
carries any `proposed_actions` (should be unreachable given the safety
gate), the result is discarded and marked `"failed"` rather than trusted.
Requires a real `database` + `AgentContextPack` via `SupervisorRuntimeContext`
— never reconstructs either from compiled context; without them it reports
a clean `"skipped"` result instead of guessing.

**`SupervisorRuntimeContext`.** A small model bundling the real,
non-serializable runtime objects (`database`, `agent_context_pack`) a real
handler may need. `allow_side_effects` and `shadow_execution` are hard
Phase 7 invariants enforced by Pydantic validators — they are forced to
`False`/`True` respectively no matter what a caller passes in, so no call
site can ever accidentally flip them.

**Output summarizer (`output_summarizer.py`).**
`summarize_agent_response(response, workflow_name=...)` converts a real
`AgentResponse` into a compact dict: `shadowExecuted`, `workflowName`,
`responseType`, a ~240-character `textPreview`, `blockCount`/`blockTypes`,
`warningCount`, `sourceCount`, `proposedActionCount`/`hasProposedActions`,
and a warnings-derived `confidence` — never the full response text, full
blocks, raw proposed-action payloads, or raw sources.

**Handler resolution (`runtime.py`, `handler_registry.py`).** New setting
`AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` (default `false`). When `false`,
handler resolution is byte-for-byte Phase 6 (every workflow-type capability
gets `DryRunCapabilityHandler`). When `true`, **every** `workflow`-type
capability — not only ones pre-registered with a real adapter — is routed
through the safety gate: unsafe capabilities get an explicit `"skipped"`
result with a `shadow_execution_not_safe_for_capability: <name>` warning
(never a silent dry-run fallback); safe capabilities get the real adapter
if a usable `SupervisorRuntimeContext` was supplied, or the safe dry-run
fallback (with an explanatory warning) if not.

**Orchestrator integration — deliberately *not* fully wired yet.** The
Phase 6 diagnostic call site in `orchestrator.run_agent_turn` runs *before*
the live `AgentContextPack` is built, and the spec's own guidance was to
prefer the safer option when in doubt. Rather than reorder the live turn or
add a second call site, Phase 7 keeps the existing call site **exactly**
where it is and does not pass it a populated `SupervisorRuntimeContext` —
so `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true` changes nothing about a
live turn today (verified by a dedicated integration test). The full
Phase 7 infrastructure is real and fully tested end-to-end — directly
against `run_supervisor_shadow`/`run_supervisor_dry_run` with an explicitly
constructed `SupervisorRuntimeContext` (a real mongomock database + a real
`AgentContextPack`) — proving `graduation_progress_workflow` genuinely
executes and `semester_planning_workflow` is genuinely refused. Wiring a
populated context into the live orchestrator call, and wiring
`shadow_compare.py` (see below), are explicit **Phase 8 follow-ups**.

**Shadow comparison (`shadow_compare.py`) — utility only, not wired.**
`compare_live_and_shadow_result(...)` deterministically compares a live
`AgentResponse` against a shadow handler's compact summary (block types,
warning counts, proposed-action counts) and flags any mismatch or any
shadow-side proposed action as unsafe — no LLM call, no semantic text
comparison, no raw text/blocks stored. Fully implemented and tested but not
called from any live/diagnostic path yet — same Phase 8 follow-up as above.
The `AGENT_SUPERVISOR_SHADOW_COMPARE_ENABLED` flag exists and is documented
but is not yet read by any code path.

**No new settings for `general_academic_workflow`'s existing LLM call.**
It may call `ReasoningBlock` (the existing, unconditional Phase 2 migration
— not gated by any dedicated flag, a pre-existing inconsistency noted back
in Phase 2) when shadow-executed; no new LLM call was added for Phase 7,
and every test exercising this path uses `OPENAI_API_KEY=None` (fails
safely to deterministic baseline text, no network call).

**Tests added:** `tests/unit/test_supervisor_shadow_safety.py` (20 cases —
`can_shadow_execute_capability` against the real default registry and
synthetic descriptors, missing-runtime-context fallback, defense-in-depth
against an unsafe capability with a caller-registered real adapter, and the
Phase 7 static safety scan: no Mongo writes, no proposal creation, no
confirm/reject calls, no direct LLM calls anywhere in the package),
`tests/unit/test_supervisor_workflow_adapters.py` (11 cases — fake
read-only workflows, SSE-event collection/discard, compact summarization,
hard rejection of unexpected proposed actions, safe failure on a raising or
response-less workflow), `tests/unit/test_supervisor_output_summarizer.py`
(10 cases), `tests/unit/test_supervisor_shadow_compare.py` (7 cases), and
`tests/integration/test_supervisor_real_handler_diagnostics.py` (7 cases —
live-turn behavior unchanged with the flag on or off, plus direct
end-to-end proof that the real adapter executes
`graduation_progress_workflow` and refuses `semester_planning_workflow`
against a real mongomock database).

## Supervisor Shadow Compare + Validation — Phase 8

Phase 7 left two things deliberately unfinished: the live orchestrator never
supplied a populated `SupervisorRuntimeContext` (so real handlers never ran
automatically), and `shadow_compare.py` was a standalone, unwired utility.
Phase 8 adds the missing **post-context hook** and a **deterministic
validation layer** on top of it — still fully diagnostic, still never
affecting the live response.

```
services/agent/app/agent/supervisor/
  validation_schemas.py   ValidationIssue, ShadowComparisonSummary, SupervisorValidationResult
  validation.py            validate_shadow_run() — 6 deterministic validators, never an LLM call
  shadow_compare.py        + build_comparison_summary() — run-level live-vs-shadow comparison (Phase 7's
                            compare_live_and_shadow_result() is unchanged, single-capability-only)
  compare_diagnostics.py   build_supervisor_validation_metadata() — compact dict for retrievalMetadata
  post_context_runner.py  run_post_context_shadow_compare() — the new post-workflow orchestrator hook
```

**Orchestrator wiring — this time it *is* wired.** Unlike Phase 6/7's
supervisor diagnostic call (which runs *before* the live `AgentContextPack`
exists), Phase 8 adds a second call in `orchestrator.run_agent_turn`, placed
*after* the live workflow already produced its `AgentResponse` (before
`_finalize_response`'s LLM text rewrite — blocks/warnings/proposed_actions
are never touched by that rewrite, so comparing pre- or post-enhancement
makes no difference for anything Phase 8 compares). At that point a real
`database` and `AgentContextPack` are both available, so
`run_post_context_shadow_compare` can build a fully populated
`SupervisorRuntimeContext` and let Phase 7's real read-only handlers
genuinely execute. Gated by `AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED`
(default `false`) — when off, the call returns `None` immediately with zero
extra DB/workflow/LLM work, so live turn behavior and latency are unchanged
by default. The clarification early-return path (no workflow ever runs) is
deliberately **not** wired — there is no live workflow result to compare.

**Validation models (`validation_schemas.py`).** `ValidationIssue` (`code`,
`severity: "info"|"warning"|"error"`, `message`, `details`),
`ShadowComparisonSummary` (live/shadow block types & counts, warning counts,
proposed-action counts, source counts, `shadow_status`/`shadow_plan_id`,
`shadow_failed_subtasks`/`shadow_skipped_subtasks`,
`unsafe_capabilities_attempted`, `safe_match`), and
`SupervisorValidationResult` (`status: "passed"|"passed_with_warnings"|"failed"|"skipped"`,
`safe_to_promote`, `comparison`, `issues`, `warnings`, `diagnostics`). None of
these fields carry chain-of-thought — a fixed `FORBIDDEN_DIAGNOSTIC_KEYS`
tuple (`chain_of_thought`, `scratchpad`, `raw_context`, `raw_blocks`, etc.)
is actively scanned for by `validation.py`, not just avoided by convention.

**Run-level comparison (`shadow_compare.build_comparison_summary`).**
Aggregates every subtask's compact `result_summary` across an entire
`SupervisorRunOutput` (not just one capability, unlike Phase 7's
`compare_live_and_shadow_result`) against the live `AgentResponse` — block
type union, summed block/warning/proposed-action/source counts, plus
`shadow_status`/`shadow_plan_id`/failed & skipped subtask lists. A subtask
counts as an **unsafe attempt** only when it genuinely ran for real
(`shadowExecuted=True`) *and* either its capability's own
`execution.side_effect_level != "none"` (looked up from an optional
`capability_registry` argument — the ground truth
`safety.can_shadow_execute_capability` is built from) or its output visibly
carried/attempted proposed actions. A capability that was correctly
*skipped* (the normal, safe Phase 7 outcome for `transcript_import_workflow`
/ `semester_planning_workflow`) is never flagged as an unsafe attempt — that
is the desired behavior, not a bug. Never stores raw text, raw blocks, raw
sources, or proposed-action payloads.

**Deterministic validators (`validation.py`), all pure/synchronous/no I/O:**

| Rule | Issue code | Severity |
|------|-----------|----------|
| Shadow produced any proposed action | `shadow_proposed_actions_detected` | error |
| A capability with non-`"none"` side effects actually ran (or looked like it tried to) | `unsafe_capability_shadow_execution_detected` | error |
| Live/shadow block **type sets** differ | `shadow_block_type_mismatch` | warning |
| Live/shadow block **counts** differ drastically (≥3×) despite matching types | `shadow_block_type_mismatch` | warning |
| Live/shadow proposed-action **counts** differ | `proposed_action_count_mismatch` | error |
| Live/shadow warning **counts** differ | `warning_count_mismatch` | warning |
| Shadow run itself ended `failed` | `shadow_execution_failed` | error |
| Shadow run itself ended `budget_exceeded` | `shadow_execution_failed` | warning |
| A `diagnostics` payload contains a forbidden raw/chain-of-thought-shaped key | `forbidden_diagnostic_payload_detected` | error |

Both sides having zero blocks is always a clean pass — a block-type/count
mismatch is *never* escalated past `warning`, per spec ("do not fail unless
the mismatch indicates a dangerous or impossible result"). Overall `status`
is `"failed"` if any issue is `error`, else `"passed_with_warnings"` if any
is `warning`, else `"passed"`. When `AGENT_SUPERVISOR_VALIDATION_ENABLED=false`,
no validator runs at all — `validate_shadow_run` returns `status="skipped"`,
`safe_to_promote=False` immediately, though a comparison may still have been
built and attached.

**`safe_to_promote` — diagnostic-only, conservative by construction.** Only
ever `True` when `status == "passed"` (zero issues, not even warnings), the
shadow run itself reported `completed`/`completed_with_warnings`, *and* the
compared result was read-only on both sides (zero proposed actions live and
shadow). Nothing in Phase 8 reads this flag to change routing, execution, or
the response — it exists purely for a future promotion decision.

**`general_academic_workflow` is excluded from real post-context execution
by default.** It is read-only (never writes, never proposes) but may call an
LLM through the existing, already-approved `ReasoningBlock` path — real
executing it on every turn purely for shadow comparison would add real LLM
cost/latency with no safety benefit, and risked accidentally looking like a
"new" LLM call site. `CapabilityExecutionMetadata` gained a new, orthogonal
field for this: `operationally_expensive_for_shadow_execution` (independent
of `safe_for_shadow_execution` — the capability still passes every
`safety.can_shadow_execute_capability` check). `runtime._select_handler`
checks this flag *before* even looking at `runtime_context` availability and
falls back to the safe dry-run handler with a
`real_shadow_execution_skipped_operationally_expensive: <name>` warning —
so no flag combination in Phase 8 can trigger a new LLM call from this path.
A dedicated test (`test_supervisor_post_context_runner.py`) plus the
existing whole-package direct-LLM-call static scan both cover this.

**Compact diagnostics (`compare_diagnostics.build_supervisor_validation_metadata`).**
Attached to `agent_runs.retrievalMetadata.supervisorValidation` — `status`,
`safeToPromote`, `liveWorkflowName`, `shadowPlanId`, `shadowStatus`,
`safeMatch`, a capped `issues` list (`code`/`severity` only, never full
`details`), block type lists, and every count above. Never the raw workflow
response, raw supervisor output, raw compiled context, or raw prompts.

**Handling proposal/write workflows.** If the live workflow was
`transcript_import_workflow` or `semester_planning_workflow`, the
post-context runner still runs supervisor graph *mechanics*, but Phase 7's
existing safety gate refuses real execution of that capability (an explicit
`"skipped"` result, never a silent dry-run trusted as real) — validation
passes as long as nothing was actually attempted/proposed; it would fail
loudly (`unsafe_capability_shadow_execution_detected` and/or
`shadow_proposed_actions_detected`) if that gate were ever bypassed. No
`agent_action_proposals` document is ever created by this path — verified by
a dedicated integration test asserting the collection stays empty.

**Tests added:** `tests/unit/test_supervisor_validation.py` (24 cases — all
6 validators, block-mismatch edge cases, forbidden-key scanning at nested
depths, `safe_to_promote` truth table, `validation_enabled=False`
short-circuit), `tests/unit/test_supervisor_shadow_compare_validation.py`
(11 cases — run-level aggregation, no-raw-payload guarantees, the
`capability_registry`-driven unsafe-attempt signal, a skipped-unsafe-capability
false-positive guard, an end-to-end comparison→validation→metadata check),
`tests/unit/test_supervisor_post_context_runner.py` (13 cases — flag
on/off, missing planner_output/live_response short-circuits, the
`SupervisorRuntimeContext` invariants, no-SSE/no-mutation guarantees, a
supervisor-failure-never-raises check, unsafe-workflow skip, missing-context
fallback, and the `general_academic_workflow` no-real-execution guarantee),
`tests/integration/test_supervisor_shadow_compare_diagnostics.py` (6 cases —
flag on/off response/SSE parity through a real `run_agent_turn`, compact
metadata attachment, a direct-call proposal-workflow-skip check against a
real mongomock database asserting zero created proposals, a
supervisor-failure-does-not-fail-the-turn check, and a forbidden-payload
scan of the actual persisted `retrievalMetadata`), plus an extended static
safety scan (`test_supervisor_shadow_safety.py`) confirming none of the five
new files contain a Mongo write, `create_agent_action_proposal(`,
confirm/reject, or a direct LLM call token.

## Controlled Supervisor Promotion — Phase 9

Phase 8 produced `safe_to_promote` data but never acted on it. Phase 9 adds
the first (and, deliberately, only) controlled experiment that actually lets
a supervisor-executed candidate become the turn's final answer — for exactly
one workflow, behind two flags, off by default, with the legacy
deterministic path always running first and always the fallback.

```
services/agent/app/agent/supervisor/
  promotion_schemas.py     PromotionMode, PromotionDecision, PromotionBlockReason, ShadowCandidateBundle
  promotion.py              evaluate_promotion_decision(), check_candidate_response_safety()
  promotion_diagnostics.py  build_supervisor_promotion_metadata() — compact dict for retrievalMetadata
```

**Hard-restricted to `graduation_progress_workflow`, always, by construction.**
`promotion.eligible_promotion_workflows(settings)` intersects a hardcoded
`_HARD_ALLOWED_PROMOTION_WORKFLOWS = frozenset({"graduation_progress_workflow"})`
with whatever `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` is configured to —
misconfiguring that setting (e.g. adding `semester_planning_workflow` to it)
can never widen eligibility, only narrow it (e.g. disabling promotion
entirely by configuring an empty list). `evaluate_promotion_decision`
independently re-checks this on every call; there is no other code path
that can promote a different workflow.

**Flags (`app/config.py`):**

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_SUPERVISOR_PROMOTION_ENABLED` | `false` | Master on/off switch. |
| `AGENT_SUPERVISOR_PROMOTION_MODE` | `off` | `off` → skipped; `shadow_only` → evaluation still runs (so diagnostics exist) but always returns `status="skipped"`; `promote_validated` → the real gate sequence runs and can actually promote. Any unrecognized value falls back to `"off"`. |
| `AGENT_SUPERVISOR_PROMOTION_WORKFLOWS` | `graduation_progress_workflow` | Configured allowlist — see the hard-cap note above. |

When `AGENT_SUPERVISOR_PROMOTION_ENABLED=false`, `post_context_runner` never
even builds a promotion decision — `retrievalMetadata` has no
`supervisorPromotion` key at all (byte-for-byte Phase 8 behavior). When
`true`, a decision is always attached (even `shadow_only`'s `"skipped"` one),
so the flag's effect is itself observable in diagnostics without ever
touching the response.

**The promotion gate (`promotion.evaluate_promotion_decision`), in order:**

1. `AGENT_SUPERVISOR_PROMOTION_ENABLED`/`_MODE` — `off`/disabled →
   `status="skipped"`; `shadow_only` → `status="skipped"`.
2. Workflow name must be in the hard-capped eligible set (`workflow_not_eligible_for_promotion` otherwise) — checked before anything else, so an ineligible workflow (`transcript_import_workflow`, `semester_planning_workflow`, `course_question_workflow`, `requirement_explanation_workflow`, `general_academic_workflow`) is blocked immediately with a single, clear reason.
3. Supervisor validation must exist, be `status="passed"` (not even `passed_with_warnings`), and `safe_to_promote=True` (`validation_missing`/`validation_not_passed`/`validation_not_safe_to_promote`).
4. No unsafe capability attempted (`unsafe_capability_attempted`) — redundant with (3) today (an unsafe attempt always makes validation `"failed"`) but checked independently as defense in depth.
5. Zero proposed actions on the live side (`live_response_has_proposed_actions`) and the candidate side (`candidate_response_has_proposed_actions`, or `candidate_response_summary_missing` if there's no candidate summary at all).
6. Live and candidate block types (`block_types_mismatch`) and counts (`block_count_mismatch`) must match exactly.
7. The supervisor output must have actually included the target capability (`supervisor_output_capability_mismatch`), have no failed subtasks (`supervisor_subtask_failed`), and never have touched a write/proposal capability name anywhere in its execution path (`write_or_proposal_capability_in_path` — defense in depth; unreachable for a real graduation-progress plan).
8. No forbidden raw/chain-of-thought-shaped key anywhere across the live/candidate/supervisor-output summaries (`forbidden_diagnostic_payload_detected`, via the same `validation_schemas.scan_for_forbidden_keys` Phase 8 uses).
9. A full in-memory candidate `AgentResponse` must exist and pass `check_candidate_response_safety` — type-correct `proposed_actions`/`warnings`/`used_sources`, present and structurally valid `blocks`, no forbidden payload anywhere in the candidate's own `model_dump()`, and (when a live response is given) exactly matching block types/counts one more time at the raw-object level.

Only when **every** check above passes does `evaluate_promotion_decision`
return `status="promoted", promoted=True`. Every gate is independently
testable and none of them ever raises — malformed/unexpected input at any
point degrades to `status="failed"` instead.

**Candidate capture (`workflow_adapters.ReadOnlyWorkflowAdapterHandler`).**
Gained an optional `candidate_sink: dict[str, AgentResponse] | None`
constructor parameter (`None` by default — zero behavior change for every
Phase 7/8 caller). When supplied, the handler stashes the full, already
proposed-action-checked `AgentResponse` into that plain in-memory dict,
keyed by capability name, *after* its own existing safety checks pass —
never included in the `SubtaskResult`/`SupervisorRunOutput` it returns,
never persisted anywhere.

**Wiring (`post_context_runner.py`).** Only when promotion could plausibly
apply (`AGENT_SUPERVISOR_PROMOTION_ENABLED=true`, mode is
`"promote_validated"`, the live workflow is in the eligible set, **and**
`AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true` — a candidate can only ever
come from a genuinely real execution) does the runner build its own handler
registry with a `candidate_sink`-carrying `ReadOnlyWorkflowAdapterHandler`
registered for that one capability name; every other case reuses
`run_supervisor_shadow`'s own default registry exactly as Phase 8 did. The
runner returns a `PostContextShadowCompareOutcome` dataclass (this replaced
Phase 8's bare `dict | None` return — an internal, non-persisted contract
change) bundling `validation_metadata`, `promotion_metadata`, and — only
when promoted — the in-memory `promoted_response`.

**Final response selection (`orchestrator.py`).** The live workflow always
runs first and produces `final_response` exactly as before. A new
`selected_response` local defaults to `final_response`; it is only ever
reassigned to `post_context_outcome.promoted_response` when that field is
not `None` (i.e. only after a `status="promoted"` decision). `selected_response`
then flows through the *exact same* `_finalize_response` →
`_persist_assistant_message` → `_emit_final_response_events` →
`complete_agent_run` path Phase 1–8 already used — no new SSE event types,
no new persistence path, no change to structured block or proposed-action
schemas. When promotion flags are off (the default), `selected_response is final_response`
always, so behavior is byte-for-byte unchanged.

**Metadata (`promotion_diagnostics.build_supervisor_promotion_metadata`).**
Attached to `agent_runs.retrievalMetadata.supervisorPromotion`: `status`,
`promoted`, `workflowName`, `mode`, and a capped `reasons` list (`code`/
`severity` only — `PromotionBlockReason.details` is never serialized here).
Never the raw candidate response, raw live response, raw blocks/text, or
raw context.

**Tests added:** `tests/unit/test_supervisor_promotion.py` (17 cases —
`check_candidate_response_safety` against real `AgentResponse`s and
duck-typed malformed stand-ins, plus the hard-capped eligible-workflow-set
guarantees), `tests/unit/test_supervisor_promotion_gate.py` (25 cases — every
gate individually, the full `off`/`shadow_only`/`promote_validated` mode
matrix, the happy "promoted" path, and a never-raises check against
completely malformed inputs), `tests/unit/test_supervisor_promotion_diagnostics.py`
(5 cases — metadata shape, capping, and no-raw-payload guarantees),
`tests/integration/test_supervisor_promotion_integration.py` (11 cases —
flag-off/shadow-only response parity through a real `run_agent_turn`,
failed-validation and malformed-candidate and handler-failure fallback, the
real "promoted" happy path against seeded graduation-progress fixtures, a
direct-call proof that `transcript_import_workflow`/`semester_planning_workflow`
are refused before any real execution, an empty-`agent_action_proposals`
check, SSE-sequence parity, and a compact/sanitized-diagnostics scan), plus
an extended static safety scan (`test_supervisor_shadow_safety.py`)
confirming none of the three new files contain a Mongo write,
`create_agent_action_proposal(`, confirm/reject, or a direct LLM call token.

## Specialist Agent Wrappers — Phase 10

Every prior phase reused the *existing* deterministic workflows for real
shadow execution (Phase 7) and promotion (Phase 9). Phase 10 adds the
architecture's originally-intended missing layer: structured,
`ReasoningBlock`-powered **specialist agents** the supervisor runtime can
call directly for a subtask — still fully shadow-only, still never
affecting the live response.

```
services/agent/app/agent/specialists/
  schemas.py               SpecialistAgentInput / SpecialistAgentOutput / SpecialistToolObservation
  base.py                   run_specialist_reasoning() — shared ReasoningBlock call + fallback + safety stripping
  context.py                 build_agent_context_pack_summary() — compact AgentContextPack -> dict
  output_summarizer.py       summarize_specialist_output() — compact SubtaskResult.output_summary shape
  safety.py                   is_specialist_agent_safe() — the fail-closed gate (mirrors supervisor/safety.py)
  registry.py                  SpecialistAgentRegistry / build_default_specialist_agent_registry()
  graduation_progress_agent.py   run_graduation_progress_agent()
  course_catalog_agent.py         run_course_catalog_agent()
  requirement_explanation_agent.py run_requirement_explanation_agent()
  supervisor_handler.py       SpecialistAgentHandler — the new SubtaskHandler
```

**Three read-only specialists implemented** (exactly the Phase 10 spec's
list, no more): `graduation_progress_agent`, `course_catalog_agent`,
`requirement_explanation_agent`. **Deliberately not implemented**:
`transcript_import_agent`, `semester_planning_agent`, and any future
`action_proposal_agent`/`profile_update_agent` — those may involve writes or
proposed actions.

**Models (`schemas.py`).** `SpecialistAgentInput` (subtask id/agent
name/objective/user message, compiled context, dependency outputs,
`deterministic_observations` — always `[]` in Phase 10, no tool-execution
loop is wired yet — success criteria, validation requirements, `dry_run`)
and `SpecialistAgentOutput` (status, result, decision summary, key
findings, missing context, warnings, validation notes, sources, confidence,
`proposed_actions`). `proposed_actions` is a hard invariant enforced by a
Pydantic field validator that forces it to `[]` unconditionally — not just
by convention, and not dependent on any specialist implementation being
correct.

**Every specialist only ever calls the LLM through `ReasoningBlock`
(`base.run_specialist_reasoning`).** Each of the three specialist modules is
a ~20-line wrapper supplying its own prompt contract name, JSON output
schema, risk level, and constraints/success criteria to that one shared
helper, which:
1. Logs (and appends a warning to whatever it eventually returns) if
   `dry_run=False` was misconfigured — Phase 10 never executes anything
   besides a `ReasoningBlock` call regardless.
2. Returns the fixed deterministic fallback (`status="skipped"`,
   `confidence=0.0`, `warnings=["specialist_reasoning_unavailable_or_failed"]`,
   `proposed_actions=[]`) immediately, with zero LLM/network call, when
   `AGENT_SPECIALIST_AGENTS_ENABLED=false`.
3. Otherwise calls `ReasoningBlock.run(...)`; any exception, a non-`completed`
   status, or a schema-invalid result all degrade to that same fallback —
   never raises.
4. On a valid result, defensively strips any `proposed_actions` key the raw
   LLM result might carry (unreachable via the schema sent to the LLM,
   which has no such property, but checked anyway) and adds a
   `specialist_proposed_actions_blocked` warning if it ever did, before
   `SpecialistAgentOutput`'s own field validator forces it to `[]` regardless.

**Prompt contracts (`reasoning/prompt_registry.py`) — `specialist_graduation_progress_v1`
/ `specialist_course_catalog_v1` / `specialist_requirement_explanation_v1`.**
All three share the exact same "must"/"must not" instruction set (verbatim
per the Phase 10 spec: solve only the assigned subtask, use only supplied
context, never invent academic rules/catalog facts/prerequisites/offerings/
completed courses/transcript rows/degree requirements, never claim a write
happened, never create action proposals, never expose chain-of-thought,
return only valid JSON) and the same `allowed_context_fields`
(`objective`, `user_message`, `compiled_context`, `dependency_outputs`,
`deterministic_observations`, `success_criteria`, `validation_requirements`)
— only the role line, risk level (`graduation_progress`: high;
`course_catalog`/`requirement_explanation`: medium), and output schema name
differ. Risk level `high`/`medium` both resolve to 3 reasoning iterations
per `ReasoningBlock`'s existing defaults (all three also explicitly set
`default_min/max_iterations=3`).

**Output schemas (`reasoning/task_schemas.py`) —
`SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA` /
`SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA` /
`SPECIALIST_REQUIREMENT_EXPLANATION_OUTPUT_SCHEMA`.** Identical shape,
matching `SpecialistAgentOutput` minus `agent_name`/`subtask_id` (set by
Python) and minus `proposed_actions` (the LLM is never even offered that
property — `additionalProperties: false`).

**Capability registry (`capabilities/default_registry.py`).** The three
specialist descriptors flipped from Phase 4/5's `enabled=False` placeholder
to `enabled=True` with new execution metadata (`type="specialist_agent"`,
`execution_supported=True`, `shadow_execution_supported=True`,
`safe_for_shadow_execution=True`, `side_effect_level="none"`,
`handler_name="specialist_agent_handler"`) — `transcript_import_agent`/
`semester_planning_agent` remain `enabled=False`/unsafe, unchanged.

**Safety gate (`specialists/safety.py`).** `is_specialist_agent_safe(capability)`
mirrors `supervisor/safety.py`'s `can_shadow_execute_capability` exactly, for
the `specialist_agent` capability type: `True` only when `enabled`,
`type == "specialist_agent"`, `shadow_execution_supported`,
`safe_for_shadow_execution`, `side_effect_level == "none"`,
`can_execute_writes is False`, `can_create_action_proposals is False`, and
`write_scope == "none"` all hold.

**Handler (`specialists/supervisor_handler.SpecialistAgentHandler`) —
always registered, self-gating.** Unlike Phase 7's real workflow adapter
(conditionally registered only when `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true`),
`SpecialistAgentHandler` is *always* the handler resolved for the three
specialist capability names in `handler_registry.build_default_handler_registry`
— `AGENT_SPECIALIST_AGENTS_ENABLED` is checked inside the handler itself,
which returns a safe `"skipped"` `SubtaskResult` (never calling
`ReasoningBlock`) when off. Before ever calling a specialist, the handler
independently re-checks `is_specialist_agent_safe` (defense in depth) and
resolves the specialist function via `SpecialistAgentRegistry`. It builds a
compact `SpecialistAgentInput` from: the subtask's own objective/success
criteria/validation requirements, `blackboard.get_dependency_outputs(...)`
for `dependency_outputs`, the existing (sparse, preview-only) `compiled_context.context`
merged with a compact camelCase `AgentContextPack` summary
(`specialists.context.build_agent_context_pack_summary`) when a real
`runtime_context.agent_context_pack` is available (i.e. only from the Phase
8/9 post-context path — the earlier Phase 6/7 diagnostic call site never
supplies one, so specialists only ever see the sparse preview there). Converts
the specialist's `SpecialistAgentOutput` into a `SubtaskResult` via
`specialists.output_summarizer.summarize_specialist_output` — `agentName`,
`status`, `confidence`, `keyFindingCount`, `warningCount`, `sourceCount`,
`missingContextCount`, `hasProposedActions`, a capped `resultKeys` list, and
a ~240-character `decisionSummaryPreview` — never the full `result` payload,
raw compiled context, or raw prompts. A specialist exception is caught and
becomes a normal `status="failed"` `SubtaskResult`, never crashing the run.

**Settings threading bugfix (`handler_registry.py`/`runtime.py`).** While
wiring this, found and fixed a latent gap: `build_default_handler_registry`
previously never received the caller's `Settings`, so any
`SpecialistAgentHandler` it built always fell back to the process-wide
cached `get_settings()` singleton instead of honoring a `Settings` object
explicitly passed into `run_supervisor_shadow` (as tests, and the Phase 8/9
post-context runner, already do for other purposes). `build_default_handler_registry`
now accepts an optional `settings` parameter, and `run_supervisor_shadow`/
`post_context_runner.py` both thread their own resolved `cfg` through it.
This has no effect on any previously-passing test (none depended on the old,
incorrect behavior) and is covered by a new integration test.

**Planner interaction — no change made, none needed.** The Planner Agent
(Phase 5, LLM-driven, off by default) may now legitimately choose one of the
three specialist capabilities in a plan, since they show up in
`_summarize_capabilities`'s enabled-only view. This is safe by construction:
supervisor output remains diagnostic/shadow-only, and Phase 9 promotion's
hard-coded eligible-workflow set is `{"graduation_progress_workflow"}` (the
*workflow*), never `graduation_progress_agent` (the *specialist*) — verified
by a dedicated test. No planner test needed a deterministic-fake-plan
workaround; every existing planner/supervisor/capability test already ran
with `OPENAI_API_KEY=None` (deterministic fallback only), so real specialist
selection by an LLM was never exercised by the existing suite.

**Tests added:** `tests/unit/test_specialist_agent_schemas.py` (9 cases),
`tests/unit/test_specialist_agent_registry.py` (9 cases),
`tests/unit/test_graduation_progress_specialist.py` (10 cases),
`tests/unit/test_course_catalog_specialist.py` (9 cases),
`tests/unit/test_requirement_explanation_specialist.py` (9 cases) — all five
using a fake `ReasoningBlock`, no real LLM call —
`tests/unit/test_specialist_agent_safety.py` (17 cases, incl. a
`specialists`-package-wide static safety scan),
`tests/unit/test_specialist_agent_handler.py` (15 cases),
`tests/agent/reasoning/test_specialist_prompt_contracts.py` (30 cases), and
`tests/integration/test_specialist_agents_supervisor_diagnostics.py` (12
cases — specialist capabilities appearing in a real `run_supervisor_shadow`
call, the handler's compact-summary shape, a graceful no-real-LLM fallback
through the full handler→`ReasoningBlock`→`ChatLLMAdapter` path, a
specialist-failure-does-not-break-the-turn check, flag on/off response/SSE
parity through a real `run_agent_turn`, and confirmation that specialist
agent names can never enter the Phase 9 promotion-eligible set). Also
extended `test_supervisor_shadow_safety.py` with a whole-`specialists`-package
static scan.

## Specialist Output Validation + Compare — Phase 11

Phase 10 added specialist agents but never checked their output against
anything trustworthy. Phase 11 adds the missing evidence layer: a
deterministic validator for one specialist output on its own, and a
deterministic structural comparison against the corresponding live
deterministic workflow's `AgentResponse` — both purely diagnostic, both
wired into the *existing* Phase 8 post-context hook rather than a new call
site.

```
services/agent/app/agent/specialists/
  validation_schemas.py   SpecialistValidationIssue / SpecialistOutputValidationResult /
                            WorkflowSpecialistComparison / SpecialistCompareDiagnostics /
                            WORKFLOW_TO_SPECIALIST_AGENT
  validation.py            validate_specialist_output() — 7 deterministic validators
  compare.py                compare_workflow_and_specialist() — structural live-vs-specialist compare
  diagnostics.py            build_specialist_compare_diagnostics() / build_specialist_validation_metadata()
```

**Models (`validation_schemas.py`).** `SpecialistValidationIssue` (code,
severity, message, details), `SpecialistOutputValidationResult` (status,
`safe_to_consider`, agent name, subtask id, issues), `WorkflowSpecialistComparison`
(workflow/specialist names, `comparable`, `safe_match`, live block types,
specialist result keys, warning/source counts, issues), and
`SpecialistCompareDiagnostics` (aggregate status/`safe_to_consider` plus the
full list of comparisons and validation results for one turn). Reuses Phase
8's `scan_for_forbidden_keys`/`FORBIDDEN_DIAGNOSTIC_KEYS` (re-exported as
`FORBIDDEN_SPECIALIST_KEYS`) rather than keeping a second, divergent list —
that shared tuple gained four Phase 11 additions: `raw_prompt`,
`system_prompt`, `user_prompt`, `full_blocks`.

**Validators (`validation.py`), all pure/synchronous/no I/O, run against
either a real `SpecialistAgentOutput` or its compact summary dict
(`output_summarizer.summarize_specialist_output`'s shape — the only form
`SupervisorRunOutput.subtask_records[].result_summary` actually holds):**

| Rule | Issue code | Severity |
|------|-----------|----------|
| `proposed_actions` non-empty (or summary `hasProposedActions=true`) | `specialist_proposed_actions_detected` | error |
| Forbidden raw/chain-of-thought-shaped key anywhere in the output or diagnostics | `forbidden_specialist_payload_detected` | error |
| Confidence missing or outside `[0, 1]` | `invalid_specialist_confidence` | error |
| Confidence `< 0.6` | `low_specialist_confidence` | warning |
| Status outside the 5 allowed values | `invalid_specialist_status` | error |
| Status is `"failed"` | `specialist_status_reported_failed` | warning |
| `missing_context` non-empty | `specialist_missing_context` | warning |
| `status="completed"` with an empty `result` | `specialist_empty_result` | warning |
| A result key looks scope-unrelated (conservative substring match — e.g. `graduation_progress_agent` returning a `transcript_rows`-shaped key) | `specialist_scope_violation_suspected` | warning |

A specialist reporting `status="failed"` (via Phase 10's own fallback,
`confidence=0.0`) triggers exactly two warnings (`specialist_status_reported_failed`
+ `low_specialist_confidence`) and nothing else — the aggregate status
becomes `"passed_with_warnings"`, never crashes, and `safe_to_consider` is
`False`, matching the spec's rule 4 without any special-casing. Overall
`status` is `"failed"` if any issue is `error`, else `"passed_with_warnings"`
if any is `warning`, else `"passed"`; `safe_to_consider` is `True` only when
`status == "passed"` (zero issues at all). Never raises: malformed/
unexpected input (wrong type, missing fields) degrades to a `status="failed"`
result with a `specialist_output_malformed` issue.

**Comparison (`compare.py`).** `compare_workflow_and_specialist(...)`
structurally compares a live `AgentResponse` against a comparable
specialist's compact summary — live block types, specialist result keys,
warning/source counts, proposed-action presence, missing-context presence,
confidence sufficiency. `specialist_agent_for_workflow(...)` uses the fixed,
diagnostic-only mapping:

| Workflow | Comparable specialist |
|----------|----------------------|
| `graduation_progress_workflow` | `graduation_progress_agent` |
| `course_question_workflow` | `course_catalog_agent` |
| `requirement_explanation_workflow` | `requirement_explanation_agent` |

`general_academic_workflow`, `transcript_import_workflow`, and
`semester_planning_workflow` are deliberately absent from the mapping —
never comparable in Phase 11 (the first is operationally
expensive/LLM-heavy per Phase 8; the other two are write/proposal
workflows). An unknown/absent/mismatched-agent-name comparison returns
`comparable=False` with an informational issue explaining why, never an
exception. Never compares full text semantically, never calls an LLM.

**Wiring — extends the existing Phase 8 hook, no new call site
(`supervisor/post_context_runner.py`).** After `run_supervisor_shadow`
already produced `shadow_output` (for Phase 8's own validation), and only
when `AGENT_SPECIALIST_VALIDATION_ENABLED` and/or `AGENT_SPECIALIST_COMPARE_ENABLED`
are `true`, `build_specialist_compare_diagnostics` scans
`shadow_output.subtask_records` for specialist-agent results (recognized by
capability name **and** the presence of the `agentName` key their compact
summary always has — defense in depth against a same-named coincidence),
validates each, optionally compares each against `live_response`, and the
compact result is attached to
`PostContextShadowCompareOutcome.specialist_validation_metadata` →
`orchestrator.py` → `agent_runs.retrievalMetadata.specialistValidation`.
Imported lazily inside the function body (mirroring `handler_registry.py`'s
own lazy specialists import) purely to avoid a module-load-order-dependent
circular import between `supervisor` and `specialists` — verified safe in
both import orders. Never modifies `selected_response`, never emits an SSE
event, never touches promotion.

**Specialist output only ever exists when the (LLM-driven, off-by-default)
Planner Agent chooses a specialist capability.** The deterministic planner
fallback never does — every test here that needs a specialist subtask to
validate/compare injects one via a monkeypatched `orchestrator.build_plan_with_diagnostics`
returning a fake `PlannerOutput`. This is safe to do in tests because the
live workflow selection (`task_planner.build_task_plan`) is completely
independent of the planner's output — injecting a fake plan changes only
what the *shadow* run does, never what the student actually sees, as the
parity tests directly confirm.

**Compact diagnostics (`diagnostics.build_specialist_validation_metadata`).**
Attached to `agent_runs.retrievalMetadata.specialistValidation` — `status`,
`safeToConsider`, `validationCount`, `comparisonCount`, a capped `issues`
list (`code`/`severity` only), `agents` (sorted, deduplicated), and a
`comparisons` list (workflow/specialist names, `comparable`, `safeMatch`,
live block types, specialist result keys, warning counts). Never the raw
specialist `result`, raw live response, full blocks, or full text.

**`safe_to_consider` — diagnostic-only, conservative by construction, at
both levels.** `SpecialistOutputValidationResult.safe_to_consider` is
`True` only when that one output's `status == "passed"`.
`SpecialistCompareDiagnostics.safe_to_consider` is `True` only when at
least one specialist output was actually validated, *every* validation
passed cleanly, and *every* comparable comparison reported
`safe_match=True`. Nothing in Phase 11 reads either flag to change
behavior — specialist output remains unpromotable (Phase 9's hard-coded
eligible-workflow set is still exactly `{"graduation_progress_workflow"}`,
never a specialist agent name).

**Tests added:** `tests/unit/test_specialist_output_validation.py` (22
cases — all 7 validators, the failed-status special case, malformed/
unexpected-input safety, no-raw-payload guarantee),
`tests/unit/test_specialist_workflow_compare.py` (17 cases — the fixed
mapping, unknown/missing/mismatched-agent non-comparable cases, safe-match
truth table, no-raw-text/blocks guarantees), `tests/unit/test_specialist_validation_diagnostics.py`
(11 cases — diagnostics-builder aggregation, compact metadata shape, issue
capping, forbidden-payload detection through the full pipeline), and
`tests/integration/test_specialist_validation_diagnostics.py` (8 cases —
flag on/off response/SSE parity through a real `run_agent_turn` with an
injected specialist plan, compact metadata attachment, a real comparable
workflow/specialist pair, a specialist-failure-does-not-break-the-turn
check, a defense-in-depth proposed-actions-blocked check, a forbidden-payload
scan of the actual persisted `retrievalMetadata`, and confirmation that
specialist agent names can never enter the Phase 9 promotion-eligible set).
Also extended `test_specialist_agent_safety.py` with a Phase-11-specific
static scan of the four new files.

## Specialist Tool Observation Layer — Phase 12

Phase 10 gave specialists a stable `deterministic_observations` input slot
but never populated it (`SpecialistToolObservation` list was always `[]`).
Phase 12 adds the missing, deliberately narrow layer: a deterministic,
bounded, read-only observation-gathering step that runs *before* a
specialist's `ReasoningBlock` call — still fully shadow-only, still never
affecting the live response.

```
services/agent/app/agent/specialists/tools/
  schemas.py               SpecialistObservation / SpecialistObservationRequest /
                             SpecialistObservationBundle
  registry.py               ObservationDescriptor / SpecialistObservationRegistry /
                              build_default_observation_registry() / SPECIALIST_ALLOWED_OBSERVATIONS
  adapters.py                Pure extraction of raw fragments from an already-built
                               AgentContextPack / compiled_context / dependency_outputs
  summarizers.py              Pure, capped shaping of those raw fragments into compact dicts
  observation_builder.py       build_specialist_observations() — the single entry point
  safety.py                     sanitize_observation_payload() — forbidden-key stripping
```

**Core design — deterministic gathering, not an LLM tool-call loop.**
Exactly the "Phase 12 implementation mode" the plan called for: no
LLM-requested tool calls are wired at all (that remains a possible Phase 13
follow-up, explicitly deferred). Instead, `SpecialistAgentHandler` (still
the same Phase 10 handler) now optionally builds a
`SpecialistObservationBundle` from data it already has on hand —
`compiled_context`, `dependency_outputs` (other subtasks' compact output
summaries), and the real `AgentContextPack` when a populated
`runtime_context` is available (only ever true from the Phase 8/9
post-context path, same caveat as Phase 10's own `agent_context_pack_summary`
wiring) — and passes the result into `SpecialistAgentInput.deterministic_observations`
before calling the specialist. **Never rebuilds context, never adds a new
internal API call, never duplicates retrieval.**

**Registry (`registry.py`) — 10 observations, fixed allowed-specialist
mapping.** `profile_summary`, `completed_courses_summary`,
`graduation_audit_summary`, `requirement_bucket_summary`,
`course_catalog_summary`, `prerequisite_summary`, `offering_summary`,
`requirement_contribution_summary`, `wiki_snippet_summary`,
`conversation_assumption_summary` — every one registered with
`read_only=True`/`side_effect_level="none"` (there is no way to construct a
write/proposal observation through this registry; no such fields exist on
`ObservationDescriptor`). Per-specialist allowlists (in registry order):

| Specialist | Allowed observations |
|---|---|
| `graduation_progress_agent` | profile, completed courses, graduation audit, requirement buckets, conversation assumptions |
| `course_catalog_agent` | profile, completed courses, course catalog, prerequisites, offering, requirement contribution, wiki snippets, conversation assumptions |
| `requirement_explanation_agent` | profile, requirement buckets, course catalog, requirement contribution, wiki snippets, conversation assumptions |

**Observation builder (`observation_builder.build_specialist_observations`)
— never raises, always bounded.** For each observation name allowed for the
requesting specialist (intersected with an optional caller-supplied
allowlist, then capped at `min(request.max_observations, 20)` — the `20`
is a fail-closed hard ceiling independent of any caller/config value):
1. A small per-observation adapter (`adapters.py`) pulls a raw fragment
   from the already-built `AgentContextPack` (e.g.
   `academic_context["course"]`, `user_context["profile"]`) or, for
   `profile_summary` only, falls back to the specialist's own already-reduced
   `compiled_context["profile_summary"]` when no pack is available.
   `graduation_audit_summary` additionally checks `dependency_outputs` for
   an already-computed audit-shaped dependency result — it never calls the
   graduation-audit internal API itself.
2. If no raw fragment is found, the observation is `status="missing"` with
   warning `observation_source_unavailable` — never a crash, never an
   invented value.
3. Otherwise a summarizer (`summarizers.py`) hand-picks a small, known-safe
   set of fields into a capped dict (e.g. `summarize_course_catalog` only
   ever keeps `id`/`courseNumber`/`title`/`credits`/`facultyId` — never the
   full catalog document).
4. The resulting summary is sanitized (`safety.sanitize_observation_payload`)
   before being attached — see below.

A per-observation adapter/summarizer exception degrades that single
observation to `status="failed"`, never breaks the bundle or the caller.

**Safety (`safety.py`) — reuses the existing shared forbidden-key list.**
`FORBIDDEN_OBSERVATION_KEYS` is `FORBIDDEN_DIAGNOSTIC_KEYS`
(`app.agent.supervisor.validation_schemas`) — the same tuple Phase 11's
`FORBIDDEN_SPECIALIST_KEYS` already re-exports, not a third, divergent
list; it already matches the Phase 12 spec's forbidden-key list verbatim
(`context`, `compiled_context`, `raw_context`, `raw_prompt`,
`system_prompt`, `user_prompt`, `raw_response`, `raw_text`, `full_text`,
`raw_blocks`, `full_blocks`, `proposed_action_payload`, `transcript_rows`,
`full_catalog`, `raw_pdf_bytes`, `chain_of_thought`, `hidden_reasoning`,
`private_reasoning`, `scratchpad`, `thoughts`). `sanitize_observation_payload`
recursively walks every observation summary (any nesting depth, including
inside lists) and omits any forbidden key, adding one
`forbidden_observation_payload_omitted:<key>` warning per omission — never
raises on a malformed payload. Individual descriptors (e.g.
`wiki_snippet_summary`) can also declare extra forbidden keys (`content`,
so only the already-truncated `preview` field can ever appear).

**Integration point — `SpecialistAgentHandler` only, no other call site
changed.** `SpecialistAgentHandler._build_observation_bundle` is the single
new method: returns `None` immediately (zero extra work) when
`AGENT_SPECIALIST_OBSERVATIONS_ENABLED=false`, and never raises into `.run()`
even if observation-building unexpectedly fails. When enabled, its
`SpecialistObservationBundle` is converted into a list of the existing
Phase 10 `SpecialistToolObservation` model (which gained one new, safely
defaulted field: `status`, mirroring `SpecialistObservationStatus`) —
`"failed"` observations are dropped, `"available"`/`"missing"` ones are
kept so the specialist can see (and, per its updated prompt contract,
report) what's missing without inventing a value for it.

**Output summarization (`supervisor_handler._observation_metadata`) —
compact metadata only, folded into the existing Phase 10 summary shape.**
`observationCount` (available only), `observationNames`,
`observationWarningCount` (bundle + per-observation warnings, combined),
`missingObservationCount` — never the raw `summary` of any observation.
Exactly the shape the Phase 12 spec's example diagnostics JSON shows.
Nothing new is added to `agent_runs.retrievalMetadata` — like Phase 10/11's
own compact fields, this lives only in `SubtaskResult.output_summary`
(`SupervisorRunOutput.subtask_records[].result_summary`), the same place
`agentName`/`status`/`resultKeys` already live.

**Prompt contracts (`reasoning/prompt_registry.py`) — four new instructions,
same three specialist contracts, no schema change.** All three specialist
prompt contracts gained: "You may use deterministic_observations as trusted
read-only observations.", "If an observation conflicts with the compiled
context, prefer the deterministic observation and surface the conflict in
warnings.", "Do not invent observations.", "Do not request unavailable
tools." — the existing "must not perform writes"/"must not create proposed
actions" instructions already covered those two points, so they weren't
duplicated. `allowed_context_fields` is unchanged (`deterministic_observations`
was already listed there since Phase 10).

**Feature flags (`config.py`) — off by default, fail-closed.**
`AGENT_SPECIALIST_OBSERVATIONS_ENABLED` (default `false`) is the master
switch; `AGENT_SPECIALIST_OBSERVATION_MAX_COUNT` (default `8`) bounds how
many observations one specialist call may receive
(`Settings.resolved_agent_specialist_observation_max_count()` always
clamps to `>= 0`, on top of the builder's own hard `20` ceiling). Neither
flag requires `OPENAI_API_KEY` — observation building never calls an LLM.

**Existing behavior is byte-for-byte unchanged when the flag is off.**
`test_handler_stores_compact_summary_only` (Phase 10, unmodified) still
asserts the exact original `output_summary` key set, and still passes —
confirming `deterministic_observations` stays `[]` and no new summary keys
appear whenever `AGENT_SPECIALIST_OBSERVATIONS_ENABLED` is unset/false.

**Static safety scan extended, not duplicated.** The existing Phase
10 whole-`specialists`-package scan
(`test_specialist_agent_safety.py::test_static_scan_no_writes_proposals_confirm_reject_or_direct_llm_calls`)
now uses `rglob` instead of `glob`, so it automatically covers
`specialists/tools/` too; a dedicated `test_specialist_observation_safety.py`
scan additionally checks the tools package alone and confirms it never
constructs/calls `ReasoningBlock`.

**Tests added:** `tests/unit/test_specialist_observation_schemas.py` (11
cases), `tests/unit/test_specialist_observation_registry.py` (19 cases),
`tests/unit/test_specialist_observation_builder.py` (21 cases),
`tests/unit/test_specialist_observation_safety.py` (14 cases, incl. a
`specialists/tools`-package static safety scan), and
`tests/unit/test_specialist_observation_integration.py` (10 cases — the
`SpecialistAgentHandler` <-> observation-layer wiring, using the same fake-
`ReasoningBlock`/fake-registry pattern as `test_specialist_agent_handler.py`)
— 75 new unit cases total, no real LLM call anywhere. Plus
`tests/integration/test_specialist_observations_supervisor_diagnostics.py`
(12 cases — flag on/off `run_supervisor_shadow` diagnostics parity, real
observation extraction from a populated in-memory `AgentContextPack`, every
specialist capability, missing-observation resilience, forbidden-payload
sanitization end-to-end, a full live-turn SSE/text/blocks/actions parity
check, and confirmation that no write/action-proposal/direct-LLM-call was
ever introduced).

**Limitations / Phase 13 follow-ups.** `graduation_audit_summary` can only
ever be `"available"` today when a future workflow starts writing a
`graduationAudit` key into `AgentContextPack.academic_context`, or when a
dependency subtask's output summary happens to carry audit-shaped fields
directly — Phase 12 deliberately does not add a new internal API call to
fetch it fresh (would duplicate `graduation_progress_workflow`'s own call
and add cost/latency to a still-diagnostic-only path). No LLM-requested
tool-call loop exists yet — `allowed_observations`/`max_observations` on
`SpecialistObservationRequest` exist as the request-shaping seam a future,
carefully bounded version of that loop could use, but nothing today lets
the LLM itself choose which observations to fetch.

## Specialist Tool-Request Loop — Phase 13

Phase 12 gave specialists a deterministic, read-only observation-gathering
step that runs *before* their `ReasoningBlock` call, but no way for a
specialist to ask for more once that call started. Phase 13 closes that gap
narrowly: specialists may now request *bounded, read-only* observations from
the same fixed Phase 12 registry — still fully shadow-only, still never
affecting the live response.

```
services/agent/app/agent/specialists/tools/
  tool_loop_schemas.py     SpecialistObservationToolRequest / SpecialistObservationToolResult /
                             SpecialistToolLoopDiagnostics
  tool_requests.py          validate_tool_requests() — deterministic per-request validation
  tool_loop.py               run_specialist_tool_loop() — one-round validate+build executor
  tool_loop_safety.py         find_forbidden_argument_keys() / is_requested_observation_safe()
  tool_loop_diagnostics.py     build_tool_loop_diagnostics_summary() — compact summary
```

**Core design — the specialist's only "tool" is a Phase 12 observation
name.** Phase 1's `ReasoningBlockOutput` already supports
`status="needs_tool"` + `tool_requests` (a `ReasoningToolRequest` list) —
Phase 2–12 callers never used it because nothing consumed a `needs_tool`
result except the generic early-exit/fallback path. Phase 13 is the first
consumer: when a specialist's `ReasoningBlock` pass returns `needs_tool` and
`AGENT_SPECIALIST_TOOL_LOOP_ENABLED=true`, `specialists/base.py` reads
`tool_requests`, treats each `tool_name` as a requested *observation name*
(never an arbitrary tool/function), validates it, builds only the approved
ones, appends them to `deterministic_observations`, and re-runs
`ReasoningBlock` once for that round's final pass — up to a hard-capped
number of rounds. There is no second observation system and no new
tool-execution engine: the tool loop is a thin, validated front door onto
the exact same `observation_builder.build_specialist_observations` Phase 12
already audited.

**Request validation (`tool_requests.validate_tool_requests`) — deterministic,
never raises.** A request is approved only when *all* hold:
1. `observation_name` (the request's `tool_name`) is a real, registered
   Phase 12 observation (`SpecialistObservationRegistry.get`).
2. It is allowed for the requesting specialist
   (`SPECIALIST_ALLOWED_OBSERVATIONS`, unchanged from Phase 12).
3. The descriptor is genuinely read-only/no-side-effect
   (`tool_loop_safety.is_requested_observation_safe`) — defensive, since the
   registry can only ever construct such descriptors, but checked anyway.
4. It was not already supplied — either already present in
   `deterministic_observations` before this round, or requested more than
   once in the same round (first occurrence wins, deterministically).
5. `arguments` carries no forbidden key at any nesting depth
   (`tool_loop_safety.find_forbidden_argument_keys`, reusing the same
   `FORBIDDEN_OBSERVATION_KEYS`/`FORBIDDEN_DIAGNOSTIC_KEYS` tuple Phase
   11/12 already use).
6. The request falls within `max_requests_per_round` (position-based, not
   approval-based — mirrors `observation_builder`'s own slice-then-warn
   budget pattern).

Rejections carry one of five deterministic warning shapes:
`tool_request_unknown_observation:<name>` (status `"unavailable"`),
`tool_request_not_allowed_for_specialist:<name>`,
`tool_request_duplicate_observation:<name>`,
`tool_request_forbidden_arguments:<key>`, and `tool_request_budget_exceeded`
(status `"rejected"` for all four). A malformed request (missing/empty
name, non-dict `arguments`, wrong type entirely) is coerced defensively or
silently dropped before validation — never raises.

**Round execution (`tool_loop.run_specialist_tool_loop`) — validate, then
build, nothing else.** For every approved name, builds a
`SpecialistObservationRequest` restricted to exactly those names and calls
the existing Phase 12 `build_specialist_observations` — the same sanitized,
capped, `status="available"|"missing"|"failed"` result shape Phase 12
already produces. `"available"` observations become new
`SpecialistToolObservation`s ready to merge into
`deterministic_observations`; everything else (missing/failed/rejected) is
tracked as names-only for diagnostics. This module never imports
`ReasoningBlock` and never calls an LLM — the static safety scan
(`test_specialist_tool_loop_safety.py`) confirms it.

**Round loop (`specialists/base.py`) — the single shared orchestration
point.** `run_specialist_reasoning` (used by all three specialists) now:
1. Runs the first `ReasoningBlock` pass exactly as before Phase 13.
2. If `status == "needs_tool"` and the loop is enabled, runs up to
   `Settings.resolved_agent_specialist_tool_loop_max_rounds()` rounds: each
   round validates+builds observations for the *current* `tool_requests`,
   merges any newly-approved observations into `deterministic_observations`,
   and re-runs `ReasoningBlock` once more — even when zero requests were
   approved, so the specialist still gets a chance to answer (or report
   `needs_more_context`) with whatever is already available, rather than
   being stuck.
3. Falls through to the exact same completion/fallback logic that existed
   before Phase 13 (`status != "completed" or not schema_valid or result is
   None` → the Phase 10 fallback `status="skipped"` output) — a
   still-`needs_tool` result after the rounds are exhausted, a
   `needs_more_context` result, and a `failed` result are all handled
   identically to before, just with a `tool_loop_diagnostics` attached when
   the loop actually ran.

No specialist file (`graduation_progress_agent.py`/`course_catalog_agent.py`/
`requirement_explanation_agent.py`) duplicates any of this — each only gained
one new, optional `agent_context_pack` passthrough parameter (needed so the
loop can build *new* observations the same way Phase 12's initial bundle
already does, from the real, already-built `AgentContextPack`, not just its
compact summary).

**Budgets (`config.py`) — fail-closed, hard-capped regardless of
configuration.** `resolved_agent_specialist_tool_loop_max_rounds()` clamps
to `[0, 2]` (configured default `1`); `resolved_agent_specialist_tool_loop_max_requests_per_round()`
clamps to `[0, 8]` (configured default `4`). Exceeding either budget never
raises — extra requests are rejected with `tool_request_budget_exceeded`,
and exhausting all rounds while still `needs_tool` resolves to
`SpecialistToolLoopDiagnostics.status="budget_exceeded"` (the specialist's
own `SpecialistAgentOutput.status` still degrades to the ordinary Phase 10
fallback in that case, exactly like any other non-`"completed"` `ReasoningBlockOutput`).

**Diagnostics (`SpecialistAgentOutput.tool_loop_diagnostics` /
`tool_loop_diagnostics.build_tool_loop_diagnostics_summary`) — compact,
names-only, only present when the loop actually ran.**
`SpecialistAgentOutput` gained one new, safely-defaulted (`None`) field,
`tool_loop_diagnostics`, set only when the first `ReasoningBlock` pass
returned `needs_tool` *and* the loop is enabled — every other call path
leaves it `None`, so `output_summarizer.summarize_specialist_output`'s
existing fixed key set is completely unaffected when the loop never
engages (confirmed by the still-unmodified, still-passing
`test_handler_stores_compact_summary_only`). When it does engage,
`supervisor_handler.SpecialistAgentHandler.run` folds in exactly 7 compact
keys — `toolLoopStatus`, `toolLoopRoundsUsed`, `requestedObservationCount`,
`approvedObservationCount`, `rejectedObservationCount`,
`requestedObservationNames`, `rejectedObservationNames` — never raw
tool-request arguments, never a raw observation `summary`.

**Prompt contracts (`reasoning/prompt_registry.py`) — nine new instructions,
same three specialist contracts, no schema change.** All three specialist
prompt contracts gained instructions describing exactly the Phase 13
contract: `tool_requests` may only name a real observation (`tool_name` =
the observation name, `purpose` required), never an arbitrary tool, write,
or proposed action; never a raw catalog dump, transcript row, PDF, raw
context, or full block; and to prefer `missing_context`/a warning over
guessing when the needed observation isn't available. `allowed_context_fields`
is unchanged — `deterministic_observations` already covers the augmented
list on the final pass.

**Safety scan — extended, with one necessary, documented deviation.** The
existing whole-`specialists`-package recursive scan
(`test_specialist_agent_safety.py::test_static_scan_no_writes_proposals_confirm_reject_or_direct_llm_calls`)
already covers all 5 new `tools/` files unmodified (it uses call/path-shaped
tokens like `confirm_action(`/`reject_action(`/`/confirm`/`/reject`, not bare
words). A new, dedicated `test_specialist_tool_loop_safety.py` additionally
scans exactly those 5 files, and `test_specialist_observation_safety.py`'s
existing `tools/`-scoped scan was updated to use the same call/path-shaped
tokens *for the Phase 13 files specifically* (still bare-word for the older
Phase 12 files) — necessary because
`SpecialistToolRequestStatus = "rejected"`/`rejected_observations`/etc. are
legitimate request-validation vocabulary that would otherwise false-positive
against a literal bare `"reject"` substring scan, a different concept
entirely from the write-action confirm/reject flow those tokens exist to
catch. No file gained a real `confirm_action(`/`reject_action(`/`/confirm`/
`/reject`/write/direct-LLM call site.

**Existing behavior is byte-for-byte unchanged when the flag is off.**
`AGENT_SPECIALIST_TOOL_LOOP_ENABLED` defaults to `false`; when off, a
`needs_tool` `ReasoningBlockOutput` degrades to exactly the same Phase 10
fallback as before Phase 13 existed — confirmed by
`test_disabled_tool_loop_preserves_phase12_fallback_behavior` (`ReasoningBlock.run`
is called exactly once, never a second time) and the integration suite's
flag-off/flag-on SSE/text/blocks/actions parity check.

**Tests added:** `tests/unit/test_specialist_tool_request_models.py` (22
cases), `tests/unit/test_specialist_tool_request_validation.py` (15 cases),
`tests/unit/test_specialist_tool_loop.py` (20 cases — round-executor +
`base.run_specialist_reasoning` orchestration with a fake, queue-based
`ReasoningBlock`), `tests/unit/test_specialist_tool_loop_integration.py` (8
cases — all three real specialist agents, per-specialist allowlist
enforcement inside the loop, compact-diagnostics shape, and Phase 11
validation/compare still working after a tool-loop round), and
`tests/unit/test_specialist_tool_loop_safety.py` (13 cases — static scan +
`tool_loop_safety` helper unit tests) — 78 new unit cases total, no real LLM
call anywhere. Plus `tests/integration/test_specialist_tool_loop_supervisor_diagnostics.py`
(8 cases — flag on/off `run_supervisor_shadow`/live-turn parity, real tool-loop
engagement via a monkeypatched fake `ReasoningBlock`, rejected/missing
observation surfacing, and confirmation that no raw content, write, or
action proposal is ever introduced).

**Limitations / Phase 14 follow-ups.** The loop only ever runs once
`ReasoningBlockOutput.status == "needs_tool"` on the *first* pass — a
specialist that only realizes it needs more data on a later internal pass
still exits early via the existing Phase 1 `needs_tool`/`needs_more_context`
early-exit behavior in `reasoning_block.py`, which Phase 13 does not change.
The specialist prompt contracts describe the tool-request contract, but
nothing here evaluates *how well* specialists actually use it (that would
require running a real LLM, out of scope for a shadow-only, no-`OPENAI_API_KEY`-
required phase). As before, specialist output — with or without a tool-loop
round — remains diagnostic-only; Phase 14 can revisit a controlled
specialist-promotion experiment (Phase 11's `safe_to_consider` evidence) now
that specialists have a slightly richer (but still fully bounded) way to
answer.

## Controlled Specialist Text Promotion — Phase 14

Phase 11 built the evidence (`safe_to_consider`) that a specialist output
might be trustworthy; Phase 14 is the first, deliberately narrow use of that
evidence to actually affect a student-visible turn — but only ever
`AgentResponse.text`, and only ever for `graduation_progress_agent`.

```
services/agent/app/agent/specialists/
  text_promotion_schemas.py    SpecialistTextPromotionReason / SpecialistTextPromotionDecision /
                                  SpecialistTextPromotionMode / SpecialistTextPromotionStatus
  text_promotion.py             evaluate_specialist_text_promotion() / build_text_promoted_response() /
                                  eligible_text_promotion_agents() / eligible_text_promotion_workflows()
  text_promotion_diagnostics.py  build_specialist_text_promotion_metadata() — compact summary
  answer_text_safety.py           check_answer_text_safety() — deterministic marker/phrase scan
```

**Core design — text-only promotion, never full-response promotion.** Unlike
Phase 9 (which swaps the *entire* candidate `AgentResponse`), Phase 14 never
lets a specialist's blocks, warnings, sources, or proposed actions reach a
student — `build_text_promoted_response` copies the live
`graduation_progress_workflow` response and replaces only `.text`, using the
exact same `model_copy(update=...)` immutable-copy pattern already used
throughout the orchestrator (e.g. `final_response.model_copy(update={"message_id": ...})`).
The deterministic workflow remains the sole source of academic truth for
every structured field; only the *explanation* may come from the specialist.

**Precedence with Phase 9 — deterministic, never both.** Two promotion
systems must never modify the same turn independently. `post_context_runner.py`
evaluates Phase 9 workflow promotion first (unchanged); Phase 14 receives
`workflow_promotion_already_promoted=bool(promoted_response is not None)`
and, when `True`, blocks immediately with
`workflow_promotion_already_selected_response` before any other gate runs —
it never even looks at the specialist output in that case.

**Reusing the existing shadow specialist output — no second pass.**
`SpecialistAgentHandler` (Phase 10, unchanged interface otherwise) gained one
new, optional constructor parameter: `specialist_output_sink: dict[str,
SpecialistAgentOutput] | None`. When supplied, `.run()` captures the *full*
in-memory `SpecialistAgentOutput` for that call, keyed by agent name — never
included in the `SubtaskResult` it returns, never persisted. `post_context_runner.py`
only ever constructs a sink-carrying `SpecialistAgentHandler` (overriding the
capability registration `handler_registry.py` always makes by default) when
`AGENT_SPECIALIST_TEXT_PROMOTION_MODE=promote_validated` and the live
workflow is `graduation_progress_workflow` — the exact same, single
`run_supervisor_shadow` call Phase 8/11 already make is reused; Phase 14
never runs a second specialist pass, mirroring `ReadOnlyWorkflowAdapterHandler`'s
own Phase 9 `candidate_sink` pattern exactly.

**The gate (`text_promotion.evaluate_specialist_text_promotion`) — ~20 strict
conditions, blocking on *any* reason regardless of severity.** Mirrors
`supervisor.promotion.evaluate_promotion_decision`'s own structure and its
"any reason blocks, severity is classification metadata only" rule:
1. `AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED=true` and
   `AGENT_SPECIALIST_TEXT_PROMOTION_MODE=promote_validated` (otherwise
   `status="skipped"`, exactly like Phase 9's own `"off"`/`"shadow_only"`
   short-circuit).
2. No workflow candidate already promoted this turn (see precedence above).
3. `workflow_name == "graduation_progress_workflow"` and
   `specialist_agent_name` is in the hardcoded-intersected eligible set —
   `_HARD_ALLOWED_TEXT_PROMOTION_AGENTS = {"graduation_progress_agent"}`, so
   `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` can only ever narrow eligibility,
   exactly like Phase 9's own `_HARD_ALLOWED_PROMOTION_WORKFLOWS`.
4. The existing Phase 11 `specialist_validation_metadata` for that specific
   specialist record is present, `status == "passed"`, and `safeToConsider`.
5. The existing Phase 11 `specialist_comparison_metadata` for that specific
   workflow/specialist pair is present, `comparable`, and `safeMatch`.
6. The specialist's own compact output summary (already computed by
   `SpecialistAgentHandler`/`output_summarizer.summarize_specialist_output`,
   including any Phase 12/13 observation/tool-loop keys) reports
   `status == "completed"`, `confidence >= 0.85`, `missingContextCount == 0`,
   `hasProposedActions == False`, `toolLoopStatus != "budget_exceeded"`, and
   `rejectedObservationCount == 0`.
7. `answer_text` (see below) is present and passes
   `answer_text_safety.check_answer_text_safety`.
8. The live response itself has zero proposed actions and at least one
   block.
9. A defense-in-depth `scan_for_forbidden_keys` pass over every supplied
   diagnostics dict (same shared `FORBIDDEN_DIAGNOSTIC_KEYS` tuple Phase
   8/9/11/12/13 all reuse).

Never raises: any unexpected input (malformed metadata, a broken `settings`
object) degrades to `status="failed"`, never an exception escaping the
function.

**`answer_text` source and safety
(`SpecialistAgentOutput.result["answer_text"]` /
`answer_text_safety.check_answer_text_safety`).** No schema change was
needed — `_specialist_output_schema()`'s `result` property was already an
open `{"type": "object"}`, so `answer_text` is simply one more key a
specialist may (optionally) populate there. Only the
`specialist_graduation_progress_v1` prompt contract was updated (5 new
instructions) to describe this convention; the other two specialist
contracts are unchanged and are not expected to produce `answer_text` yet.
`check_answer_text_safety` is a deterministic keyword/phrase scan (not an
NLP classifier, consistent with `sanitize_observation_payload`'s own style)
rejecting: empty/whitespace-only text, text longer than
`AGENT_SPECIALIST_TEXT_PROMOTION_MAX_CHARS` (default `4000`), any of ~25
forbidden-payload markers (chain-of-thought/scratchpad/raw-context/raw-block/
proposed-action-payload/raw-transcript/raw-catalog-dump shaped strings,
folded into one `specialist_answer_text_forbidden_payload` reason), and any
of ~20 write-claim phrases ("I updated", "I saved", "I imported", "I changed
your profile", etc., folded into `specialist_answer_text_write_claim`).

**Candidate construction (`text_promotion.build_text_promoted_response`) —
copy-then-replace-text-only, never raises.** Duck-typed defensively (checks
`isinstance(live_response, AgentResponse)` before copying); a malformed
`live_response` or an unexpected copy failure degrades to returning
`live_response` unchanged rather than raising or fabricating a response.
`blocks`/`warnings`/`used_sources`/`proposed_actions`/`message_id`/`run_id`/
`conversation_id`/`assumptions`/`suggested_prompts` are all guaranteed
unchanged by construction (a `model_copy(update={"text": ...})` never
touches any other field) — confirmed by
`test_specialist_text_promoted_response.py`'s exhaustive field-by-field
checks, including that the original `live_response` object is never
mutated.

**Diagnostics (`retrievalMetadata.specialistTextPromotion` /
`text_promotion_diagnostics.build_specialist_text_promotion_metadata`) —
compact, mirrors Phase 9's own shape exactly.** `status`, `promoted`,
`mode`, `workflowName`, `specialistAgentName`, and up to 20 capped
`{"code", "severity"}` reason entries — never a `message`/`details` field
(the `SpecialistTextPromotionReason` model's own `details` field, unlike
`PromotionBlockReason`'s, is never surfaced past this compact builder),
never the promoted answer text, never the raw specialist `result`, never raw
observations/tool-request arguments, never raw compiled context, never the
raw live/candidate `AgentResponse`.

**Orchestrator integration (`orchestrator.py`) — one new metadata variable,
zero structural changes.** `post_context_outcome.promoted_response` was
already a generic "whichever candidate won" seam Phase 9 established;
Phase 14 reuses it unchanged — `post_context_runner.run_post_context_shadow_compare`
now may also set it (only when Phase 9 didn't already), so
`orchestrator.py`'s existing `if post_context_outcome is not None and
post_context_outcome.promoted_response is not None: selected_response =
post_context_outcome.promoted_response` line required *no* edit at all. The
only orchestrator change is threading one new optional metadata field
(`specialist_text_promotion_metadata`) into `_retrieval_metadata_with_diagnostics`,
exactly like every prior phase's own diagnostics field.

**Feature flags (`config.py`) — off by default, fail-closed, mode-gated like
Phase 9.** `AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED` (default `false`),
`AGENT_SPECIALIST_TEXT_PROMOTION_MODE` (default `"off"`; invalid values fall
back to `"off"`), `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` (default
`"graduation_progress_agent"`, always intersected with the hardcoded
ceiling), `AGENT_SPECIALIST_TEXT_PROMOTION_MAX_CHARS` (default `4000`,
`resolved_agent_specialist_text_promotion_max_chars()` always clamps to
`>= 1`). None of these require `OPENAI_API_KEY` on their own — only the
specialist's own `ReasoningBlock` call (already gated by
`AGENT_SPECIALIST_AGENTS_ENABLED`, unchanged since Phase 10) does.

**A note on this phase's own dependency on Phase 11's flags.** Text
promotion's validation/comparison gates read the *existing* Phase 11
`specialist_validation_metadata` — which is only ever computed when
`AGENT_SPECIALIST_VALIDATION_ENABLED`/`AGENT_SPECIALIST_COMPARE_ENABLED` are
also `true`. This is intentional (Phase 14 should never trust an
unvalidated/uncompared specialist output) but means all four flags
(`AGENT_SPECIALIST_AGENTS_ENABLED`, `AGENT_SPECIALIST_VALIDATION_ENABLED`,
`AGENT_SPECIALIST_COMPARE_ENABLED`, `AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED`)
must be `true` together (plus mode `promote_validated`) for promotion to
ever succeed — documented here so a future operator isn't surprised by an
always-`"blocked"` `specialist_validation_missing` reason with only the
Phase 14 flags set.

**Existing behavior is byte-for-byte unchanged when the flag is off.**
`AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED` defaults to `false`; when off,
`run_post_context_shadow_compare` never even builds the specialist-output
sink and `specialist_text_promotion_metadata` stays `None` throughout —
confirmed by the integration suite's flag-off/flag-on SSE/text/blocks/actions
parity checks (block *type* sequences match; the promoted text itself is,
by design, the one thing that legitimately differs when promotion succeeds).

**Static safety scan — same documented deviation as Phase 13.** The
existing whole-`specialists`-package recursive scan already covers the 4 new
files (call/path-shaped `confirm_action(`/`reject_action(`/`/confirm`/
`/reject` tokens, not bare words); a new, dedicated
`test_specialist_text_promotion_safety.py` additionally scans exactly those
4 files and confirms none of them ever call `ReasoningBlock`/the LLM adapter/
`context_builder` directly.

**Tests added:** `tests/unit/test_specialist_text_promotion_gate.py` (29
cases), `tests/unit/test_specialist_answer_text_safety.py` (22 cases),
`tests/unit/test_specialist_text_promoted_response.py` (12 cases),
`tests/unit/test_specialist_text_promotion_diagnostics.py` (8 cases), and
`tests/unit/test_specialist_text_promotion_safety.py` (5 cases — static
scan) — 76 new unit cases total, no real LLM call anywhere. Plus
`tests/integration/test_specialist_text_promotion_integration.py` (14 cases
— flag off/shadow_only/promote_validated parity, missing-specialist-output
and failed-validation fallback, a genuine end-to-end promotion using a
monkeypatched fake specialist registry (mirroring Phase 11's own
`_inject_fake_plan`/registry-injection pattern — no real LLM call), blocks/
proposed-actions preserved through promotion, promotion never happening for
the other two specialists or for write/proposal workflows, the Phase 9/14
precedence rule holding end-to-end, collapsed-SSE-event-type parity, compact
sanitized diagnostics, and confirmation that no write/action-proposal was
ever created).

**Limitations / Phase 15 follow-ups.** Only `graduation_progress_agent`'s
`answer_text` is ever considered — `course_catalog_agent`/
`requirement_explanation_agent` don't populate it yet, and their prompt
contracts weren't changed. The `answer_text` safety scan is a deterministic
keyword/phrase check, not a semantic/factual grounding check — it can catch
an obvious write-claim or leaked marker but cannot verify the explanation is
actually a *faithful* summary of the deterministic data (that trust instead
comes transitively from Phase 11's validation/comparison gates plus the
`>= 0.85` confidence floor). Phase 15 could: (a) extend the `answer_text`
convention to `course_catalog_agent`/`requirement_explanation_agent` and
their own (currently un-eligible) workflows, behind the same hardcoded-
ceiling pattern; (b) consider promoting a small, explicitly-whitelisted
additional field (e.g. `suggested_prompts`) under the same strict-gate
philosophy; and (c) build a small offline evaluation dataset comparing
specialist `answer_text` quality against the live deterministic explanation,
now that a real (if narrow) promotion path exists to make that comparison
meaningful.

## Phase 15 readiness

The system now has: a shared reasoning runtime (Phase 1), all existing LLM
features migrated onto it (Phase 2), a diagnostic Task Understanding Agent
(Phase 3), a Capability Registry + Context Compiler (Phase 4), a diagnostic
Planner Agent (Phase 5), a shadow-only Supervisor Runtime (Phase 6), real
safety-gated read-only workflow execution inside that shadow runtime
(Phase 7), a post-context live-vs-shadow comparison + deterministic
validation layer wired into the live orchestrator turn (Phase 8), a narrow,
off-by-default controlled promotion experiment restricted to
`graduation_progress_workflow` (Phase 9), a real, `ReasoningBlock`-backed
specialist-agent layer for three read-only subtasks (Phase 10), a
deterministic validation + workflow-vs-specialist comparison layer for that
specialist output (Phase 11), a deterministic, bounded, read-only tool
observation layer those specialists can consult before reasoning (Phase 12),
a bounded, disabled-by-default specialist tool-request loop on top of that
same observation registry (Phase 13), and a narrow, disabled-by-default
text-only promotion path from `graduation_progress_agent` onto the live
`graduation_progress_workflow` response (Phase 14). Phase 15 can: (a) expand
Phase 14's `answer_text` convention (and hardcoded eligibility ceiling) to
`course_catalog_agent`/`requirement_explanation_agent`; (b) expand Phase 9's
own workflow-promotion eligible set to `course_question_workflow`/
`requirement_explanation_workflow`; (c) consider a second, still-bounded
tool-loop round type beyond observations (Phase 13 follow-up); (d) build a
specialist-answer-quality evaluation dataset now that a real (if narrow)
promotion path exists; and (e) reconsider `general_academic_workflow`'s
exclusion from real shadow/compare execution — all without any of Phase
1–14 needing to change.

## Dynamic AgentSpec + Block Library + Builder — Phase 15

Phase 15 introduces configuration-driven dynamic sub-agents. The planner/or
orchestrator may eventually emit an `AgentSpec`, but Phase 15 does **not**
generate or execute Python source — `AgentBuilder` assembles a runnable agent
from the fixed `BlockLibrary` only.

### What exists

| Component | Role |
|-----------|------|
| `AgentSpec` | Describes role, objective, reasoning pattern, allowed blocks/observations, context contract, validation policy, budget; `shadow_only=true` enforced |
| `TaskBrief` | Self-contained local task context (objective, user goal, boundaries, dependency outputs) |
| `BlockLibrary` | Nine read-only blocks (`context_filter_block`, `single_pass_reasoning_block`, `tool_observation_loop_block`, validation/synthesis/summarization blocks, …) |
| `AgentBuilder` | Validates spec + resolves block sequence; never calls LLM or runs the agent |
| `DynamicAgentInstance` | Executes `single_pass`, `tool_observation_loop`, and `compare_and_synthesize` patterns in shadow mode via `ReasoningBlock` |
| `DynamicAgentHandler` | Supervisor handler for capability `dynamic_agent` / `PlannerSubtask.dynamic_agent_spec` |
| `dynamic_agent_v1` | New prompt contract + `dynamic_agent_output_v1` JSON schema |

### Safety / scope

- All blocks are `read_only=true`, `side_effect_level="none"`.
- Spec validation rejects `shadow_only=false`, writes, proposed actions, unknown
  blocks/observations, budget over hard caps, forbidden context keys, and
  chain-of-thought/scratchpad field names.
- Runtime strips `proposed_actions`, forbidden reasoning fields, and forces
  shadow/dry-run even when misconfigured.
- `DynamicAgentRunOutput.proposed_actions` is always `[]`.
- Dynamic agents **do not** replace named specialists, workflows, or live routing.
- Diagnostics (`retrievalMetadata.dynamicAgents`) are compact — spec id/name,
  pattern, block count, status, confidence, warning/missing-context counts only.

### Settings

- `AGENT_DYNAMIC_AGENTS_ENABLED=false` (default) — handler returns `"skipped"`.
- `AGENT_DYNAMIC_AGENTS_DRY_RUN=true` (default) — misconfigured `false` still
  forces shadow-only with a warning.

### Supervisor wiring

- `build_default_handler_registry` registers `DynamicAgentHandler` for
  `dynamic_agent`.
- `PlannerSubtask.dynamic_agent_spec: dict | None` optional field added.
- `capabilities/default_registry.py` registers a read-only `dynamic_agent`
  capability descriptor for shadow supervisor runs.
- `post_context_runner` attaches `dynamicAgents` metadata when enabled.

### Limitations / Phase 16 follow-ups

- Planner does not yet emit `AgentSpec` by default (infrastructure + handler only).
- No dynamic-agent output promotion.
- `reflect_and_revise`, `structured_extraction`, and `clarification_assessment`
  patterns have block sequences but conservative runtime support only.
- No arbitrary tool registry beyond spec-allowed Phase 12 observations.

## Monitor + Plan Assumption Tracking + Replan/Repair Signals — Phase 16

Phase 16 adds a deterministic Monitor layer that compares expected plan
assumptions/subtask expectations against actual shadow supervisor execution
results and emits compact replan/repair **signals** — diagnostic only.

### What exists

| Component | Role |
|-----------|------|
| `PlanAssumption` | Falsifiable plan assumption with provenance, confidence, invalidation signals |
| `SubtaskExpectation` | Expected subtask outcome (status, no writes, no proposals, confidence, custom criteria) |
| `DivergenceSignal` | Expected-vs-actual divergence classification |
| `ReplanDecision` | Recommended control action (`continue`, `local_retry`, `ask_clarification`, `request_plan_repair`, …) |
| `monitor_plan_execution` | Main deterministic monitor entry point — never raises |
| `build_monitor_metadata` | Compact `retrievalMetadata.monitorDiagnostics` builder |

### Assumption / expectation extraction

- `assumptions_from_planner_output`, `assumptions_from_task_understanding`,
  `assumptions_from_conversation_assumptions` — all deterministic, no LLM.
- Conversation assumptions use `provenance="assumed"`; planner structural facts
  use `provenance="deterministic"`.
- `expectations_from_planner_output` / `expectations_from_supervisor_plan`
  generate default no-write/no-proposal expectations plus success criteria and
  validation requirement expectations per subtask.

### Divergence + replan policy

- Classifies divergence as `none`, `local_execution_failure`, `assumption_violation`,
  `goal_drift`, `exhausted_path`, `unsafe_output`, `missing_context`,
  `validation_failure`, `promotion_blocked`, or `budget_exceeded`.
- Applies deterministic priority: unsafe → goal drift → assumption violation →
  exhausted path → missing context (clarification vs repair) → local failure → continue.
- **Does not trigger real replanning** — signals are attached to diagnostics only.

### Settings

- `AGENT_MONITOR_ENABLED=false` (default)
- `AGENT_MONITOR_DRY_RUN=true` (default; misconfigured `false` still diagnostic-only)

### Orchestrator wiring

- `post_context_runner.run_post_context_shadow_compare` runs the monitor after
  supervisor/specialist/dynamic-agent diagnostics are available.
- `orchestrator._retrieval_metadata_with_diagnostics` attaches `monitorDiagnostics`.

### Limitations / Phase 17 follow-ups

- Monitor does not call the Planner to replan — repair/regeneration actions are signals only.
- Goal drift detection is conservative/deterministic (no LLM interpretation).
- Optional planner enrichment fields (`plan_assumptions`, `replan_triggers`, …) deferred.

## Clarification as a First-Class Capability — Phase 17

Phase 17 adds a deterministic clarification capability that represents
uncertainty, decides whether a question should be asked, batches compact
prompts, and tags fallback answers with provenance — **diagnostic-only by
default**.

### What exists

| Component | Role |
|-----------|------|
| `ClarificationNeed` | Explicit clarification need with ambiguity type, consequence, topic, evidence |
| `ClarificationDecision` | Policy outcome (`ask_user`, `assume_default`, `resolve_epistemically`, `skip`) |
| `ClarificationQuestion` | Compact user-facing question (no raw diagnostics or internal IDs) |
| `ClarificationAnswer` | Answer with provenance (`confirmed` / `assumed`) |
| `run_clarification_capability` | Main deterministic entry point — never raises |
| `build_clarification_metadata` | Compact `retrievalMetadata.clarificationDiagnostics` builder |

### Ambiguity + policy

- Distinguishes **preference** vs **epistemic** ambiguity (plus `mixed` / `unknown`).
- Consequence-aware policy: high-consequence preference may `ask_user`; epistemic
  items prefer `resolve_epistemically` when retrievable metadata is present.
- Batches questions (cap via `AGENT_CLARIFICATION_MAX_QUESTIONS`, default 3).
- Fallback assumptions tagged `provenance="assumed"` with lower confidence than confirmed answers.

### Capability registry

- `clarification_capability` registered in `capabilities/default_registry.py`
  as a read-only `tool` capability (`side_effect_level="none"`, no writes/proposals).

### Settings

- `AGENT_CLARIFICATION_ENABLED=false` (default)
- `AGENT_CLARIFICATION_USER_FACING_ENABLED=false` (default; diagnostics/fallbacks only)
- `AGENT_CLARIFICATION_MAX_QUESTIONS=3`

### Orchestrator wiring

- `post_context_runner.run_post_context_shadow_compare` runs clarification after
  monitor diagnostics when enabled.
- `orchestrator._retrieval_metadata_with_diagnostics` attaches `clarificationDiagnostics`.
- Does **not** change final text, blocks, SSE sequence, or live workflow selection.

### Safety

- No LLM calls, no writes, no action proposals.
- Questions omit raw context, raw monitor output, and chain-of-thought fields.

### Limitations / Phase 19 follow-ups

- Full plan repair / warm planner invocation after clarification resume is Phase 19.
- Cross-turn state does not yet inject `build_effective_context_text` into task understanding directly — resume uses original message plus confirmed assumptions on conversation memory.
- Assumed fallback on expiry is persisted to clarification state only; broader planner assumption sync remains diagnostic.

## Cross-Turn Clarification State — Phase 18

Phase 18 adds persisted pending clarification state, deterministic answer
resolution on the next user turn, and optional user-facing clarification
questions behind flags.

### What exists

| Component | Role |
|-----------|------|
| `PendingClarificationState` | Agent-owned pending clarification record |
| `ResolvedClarificationState` | Answered/cancelled/expired/assumed resolution result |
| `ClarificationStateRepository` | Mongo persistence in `agent_clarification_states` only |
| `resolve_clarification_answer` | Deterministic option/text/cancel matching — no LLM |
| `process_turn_start_clarification` | Turn-start pending check, resolve, expire, reminder |
| `offer_user_facing_clarification` | Creates pending state + normal assistant question response |

### Flow

1. Turn start: active pending state → increment turn count → expire or resolve user message.
2. Resolved: resume `original_user_message`, append confirmed assumptions to conversation memory.
3. Unresolved: return concise reminder via normal assistant response (same SSE shapes).
4. After post-context clarification diagnostics: if user-facing enabled and `question_ready`, create pending state and return clarification question instead of workflow text.

### Settings

- `AGENT_CLARIFICATION_ENABLED=false` (default)
- `AGENT_CLARIFICATION_USER_FACING_ENABLED=false` (default)
- `AGENT_CLARIFICATION_MAX_QUESTIONS=3`
- `AGENT_CLARIFICATION_MAX_PENDING_TURNS=3`
- `AGENT_CLARIFICATION_STATE_ENABLED=true` (default; controls persistence)

### Diagnostics

- `retrievalMetadata.clarificationState` — compact status, provenance, resume mode, warnings.
- No raw context, monitor output, workflow response, blocks, or proposed actions stored.

### Safety

- One active pending clarification per conversation.
- No student academic data writes, no action proposals, no LLM calls.
- Expired pending state does not block future turns.

## Warm Planner Invocation + Plan Repair Foundation — Phase 19

Phase 19 adds warm planner repair diagnostics (off by default):

- **`PlanSnapshot`**, **`PlanExecutionDelta`**, **`PlanRepairRequest`**, **`PlanRepairOutput`** — typed repair models in `app/agent/planner/repair_schemas.py`.
- **`build_plan_snapshot_from_planner_output`** / **`build_fallback_plan_snapshot`** — compact prior-plan snapshots (no raw context/prompts).
- **`delta_from_clarification_resolution`** / **`deltas_from_monitor_diagnostics`** — deterministic execution deltas.
- **`choose_repair_mode`** — repair vs regeneration vs continue vs clarify-first vs abort-safely policy.
- **`deterministic_plan_repair`** — non-LLM fallback repair path (`safe_to_use=false` in Phase 19).
- Optional **`planner_repair_v1`** ReasoningBlock contract when `AGENT_PLAN_REPAIR_USE_LLM=true` (still diagnostic-only).
- **`build_effective_clarification_context`** — compact confirmed-clarification metadata when `AGENT_CLARIFICATION_EFFECTIVE_CONTEXT_ENABLED=true`.
- **`retrievalMetadata.planRepairDiagnostics`** — compact repair summary attached in dry-run when `AGENT_PLAN_REPAIR_ENABLED=true`.

### Feature flags (default preserves Phase 18 behavior)

- `AGENT_PLAN_REPAIR_ENABLED=false`
- `AGENT_PLAN_REPAIR_DRY_RUN=true`
- `AGENT_PLAN_REPAIR_USE_LLM=false`
- `AGENT_CLARIFICATION_EFFECTIVE_CONTEXT_ENABLED=false`

### Safety

- Repaired plans do **not** affect final answers, workflow selection, or SSE shapes in Phase 19.
- No student academic data writes, no action proposals, no direct LLM calls outside `repair_agent.py` → `ReasoningBlock`.
- Misconfigured `AGENT_PLAN_REPAIR_DRY_RUN=false` is forced back to dry-run with a warning.

## Dynamic Planner AgentSpec Emission — Phase 20

Phase 20 connects Planner output to shadow dynamic-agent execution (off by default):

- **`AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=false`** — Planner strips/ignores `dynamic_agent_spec` fields.
- When enabled, Planner may emit `dynamic_agent_spec` on read-only analyze/validate subtasks via `planner_agent_v1`.
- **`validate_planner_emitted_agent_spec`** / **`normalize_planner_dynamic_specs`** enforce Phase 15 validation, allowed patterns, risk levels, max specs per plan, and `shadow_only=true`.
- Invalid specs are stripped; valid specs attach to `PlannerSubtask.dynamic_agent_spec` with `dynamic_agent_spec_status=validated`.
- Supervisor **`DynamicAgentHandler`** executes validated specs in shadow when `AGENT_DYNAMIC_AGENTS_ENABLED=true`.
- **`retrievalMetadata.plannerDynamicAgents`** — compact generated/validated/rejected/executed counts (no raw specs/output).
- **`retrievalMetadata.dynamicAgents`** — existing supervisor execution summaries unchanged.

### Feature flags

- `AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=false`
- `AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN=true`
- `AGENT_PLANNER_DYNAMIC_SPECS_MAX_PER_PLAN=3`
- `AGENT_PLANNER_DYNAMIC_SPECS_ALLOWED_PATTERNS=single_pass,tool_observation_loop,compare_and_synthesize`
- `AGENT_PLANNER_DYNAMIC_SPECS_ALLOWED_RISK_LEVELS=low,medium`

### Safety

- Dynamic agent construction is configuration only — no generated code.
- All specs forced `shadow_only=true`; no writes, no action proposals.
- Dynamic-agent output does not affect final answers, workflow selection, or SSE shapes.
- Warm-repair dynamic specs deferred to Phase 22 (Phase 21 includes compact repair counts in synthesis input only).

## Synthesis / Final Answer Composer — Phase 21

Phase 21 adds a first-class read-only synthesis capability (off by default):

- Package: `services/agent/app/agent/synthesis/`
- Models: `EvidenceItem`, `SynthesisInput`, `SynthesisOutput`, `SynthesisConflict`
- **`build_synthesis_input`** collects compact post-context summaries (workflow, supervisor validation/promotion, specialist validation/text promotion, dynamic agents, monitor, clarification, plan repair, planner dynamic agents) — never raw context/blocks/payloads.
- Deterministic **evidence extraction**, **trust policy**, **conflict detection**, and **fallback composer**
- Optional **`synthesis_composer_v1`** via `ReasoningBlock` when `AGENT_SYNTHESIS_USE_LLM=true`; invalid LLM output falls back to deterministic synthesis
- Registered as **`synthesis_composer_capability`** in `CapabilityRegistry` (read-only, no side effects)
- Wired in **`post_context_runner.py`** after monitor/clarification/plan repair diagnostics
- Attaches **`retrievalMetadata.synthesisDiagnostics`** — compact counts/status only (no candidate text, no raw evidence)

### Feature flags

- `AGENT_SYNTHESIS_ENABLED=false`
- `AGENT_SYNTHESIS_DRY_RUN=true`
- `AGENT_SYNTHESIS_USE_LLM=false`
- `AGENT_SYNTHESIS_MAX_EVIDENCE_ITEMS=12`
- `AGENT_SYNTHESIS_MAX_CONFLICTS=6`
- `AGENT_SYNTHESIS_MAX_CANDIDATE_CHARS=5000`

### Safety

- Synthesis is **diagnostic-only by default** — does not change `selected_response`, final text, blocks, sources, warnings, proposed actions, or SSE shapes.
- **`safe_to_promote=false` always** in Phase 21.
- No student academic data writes, no action proposals, no direct LLM calls outside `synthesis_agent.py` → `ReasoningBlock`.
- Misconfigured `AGENT_SYNTHESIS_DRY_RUN=false` is forced back to dry-run with a warning.
- Phase 22 follow-up: controlled synthesis text promotion / final answer candidate evaluation.

## Controlled Synthesis Text Promotion — Phase 22

Phase 22 adds a controlled path for synthesis candidate text to replace **`response.text` only** (off by default):

- **`AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=false`** — no promotion evaluation.
- **`AGENT_SYNTHESIS_TEXT_PROMOTION_MODE=off|shadow_only|promote_validated`** — shadow evaluates gates without changing text; promote replaces text only when all gates pass.
- **`evaluate_synthesis_text_promotion`** applies policy-based eligibility (read-only workflow allowlist, no proposed actions, synthesis readiness, candidate safety, monitor/plan-repair/clarification gates).
- **`build_synthesis_text_promoted_response`** copies live `AgentResponse` and replaces only `text` — blocks/warnings/sources/proposed_actions preserved.
- Attaches **`retrievalMetadata.synthesisPromotion`** — compact status/reasons/preservation flags (no candidate text, no live text).
- Defers to Phase 9 workflow promotion and Phase 14 specialist text promotion when either already modified `selected_response`.

### Feature flags

- `AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=false`
- `AGENT_SYNTHESIS_TEXT_PROMOTION_MODE=off`
- `AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS=graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow`
- `AGENT_SYNTHESIS_TEXT_PROMOTION_MIN_CONFIDENCE=0.85`
- `AGENT_SYNTHESIS_TEXT_PROMOTION_MAX_CHARS=5000`
- `AGENT_SYNTHESIS_TEXT_PROMOTION_REQUIRE_BLOCKS=true`

### Safety

- Text-only promotion — deterministic workflow owns blocks, warnings, sources, and proposed actions.
- Candidate text exists in memory only; never stored in diagnostics.
- `safe_to_promote` is computed deterministically in validation — never trusted from LLM output.
- No writes, no action proposals, no direct LLM calls outside existing `ReasoningBlock` synthesis path.
- Phase 23 follow-up: offline replay + evaluation harness for autonomous agent behavior.

## Offline Replay + Evaluation Harness — Phase 23

Phase 23 adds an **offline replay + evaluation harness** for autonomous agent behavior (no production behavior changes):

- Package: `services/agent/app/agent/evaluation/` — replay schemas, sanitizer, case loader, oracles, fake reasoning, gates evaluator, replay runner, metrics, reporting, safety scan.
- **Sanitized fixtures**: `services/agent/tests/fixtures/eval_cases/` (15 synthetic cases covering intent/workflow, dynamic specs, monitor, clarification, plan repair, synthesis promotion, safety).
- **Deterministic oracles** derive graduation credits, prerequisites, requirement buckets, and semester-plan constraints from compact `synthetic_world` payloads.
- **`gates_only` mode (default)**: evaluates structured gates from compact `retrieval_metadata` / `live_response_summary` — no orchestrator, no DB, no LLM.
- **`shadow_replay` mode (partial)**: conservative replay of fake `ReasoningBlock` outputs and synthesis text-promotion policy only.
- **CLI**: `services/agent/scripts/run_agent_replay_eval.py` — JSON + Markdown reports, `--fail-on-failed-cases`, `--allow-real-llm` (explicit, non-deterministic; not for tests).
- Reports are sanitized — no raw context, prompts, blocks, or chain-of-thought.

### Safety

- Eval harness does not change `/turn`, public `/agent` API, SSE shapes, or promotion allowlists.
- No real LLM calls by default; no student academic data writes; no action proposals.
- Phase 24 follow-up: eval-guided promotion policy hardening / broader read-only promotion.

## Eval-Guided Promotion Readiness — Phase 24

Phase 24 converts offline eval results into **promotion-readiness scorecards** (report-only; no production behavior changes):

- **Suite manifests**: `services/agent/tests/fixtures/eval_suites/` — 10 named suites (`core_regression`, `write_safety`, `synthesis_promotion`, etc.) grouping 25 sanitized cases.
- **Promotion candidates**: default registry of 9 paths (workflow/specialist/synthesis promotion, dynamic specs, clarification, plan repair).
- **Readiness thresholds**: pass rate, case counts, zero-tolerance safety gates, promotion precision, unsafe block rate.
- **Readiness policy**: `evaluate_promotion_readiness()` → `not_ready | ready_for_shadow | ready_for_limited_promotion | ready_for_broader_promotion`.
- **Scorecard + recommendations**: JSON/Markdown reports with blocking reasons and compact policy-hardening suggestions (`keep_shadow_only`, `add_more_eval_cases`, etc.).
- **CLI**: `services/agent/scripts/run_agent_promotion_readiness.py` — runs eval then scores readiness; `--fail-on-not-ready`, `--fail-on-any-blocking`.

### Safety

- Readiness layer is offline only — does not widen promotion allowlists or change runtime defaults.
- No real LLM calls; no student academic data writes; no action proposals.
- Phase 25 follow-up: controlled broader read-only promotion based on readiness scorecard.

---

## Runtime Readiness Gate + Controlled Broader Read-Only Promotion — Phase 25

### Goal

Add a **runtime readiness gate** that requires a human-reviewed activation manifest before any promotion candidate may proceed. Offline readiness scorecards alone never auto-enable runtime authority.

### Package

`services/agent/app/agent/readiness/`:

- `schemas.py` — `RuntimeReadinessManifest`, candidate approval, gate input/decision, level ordering
- `manifest_loader.py` — JSON-only manifest load + validation (no network/LLM)
- `runtime_gate.py` — `evaluate_runtime_readiness_gate()`, candidate ID helpers
- `diagnostics.py` — compact `runtimeReadiness` metadata
- `safety.py` — static forbidden-pattern scan

### Config (defaults unchanged — gate off)

| Variable | Default |
|----------|---------|
| `AGENT_RUNTIME_READINESS_GATE_ENABLED` | `false` |
| `AGENT_RUNTIME_READINESS_MANIFEST_PATH` | empty |
| `AGENT_RUNTIME_READINESS_REQUIRE_HUMAN_REVIEW` | `true` |
| `AGENT_RUNTIME_READINESS_MIN_LEVEL` | `ready_for_limited_promotion` |
| `AGENT_RUNTIME_READINESS_MAX_AGE_DAYS` | `30` |
| `AGENT_RUNTIME_READINESS_FAIL_CLOSED` | `true` |

### Activation manifest

Example: `services/agent/config/promotion_readiness_manifest.example.json`

Human-reviewed allowlist — not a scorecard replacement. Runtime parses only compact activation manifests during turns.

### Gate behavior

- **Gate disabled** → existing promotion policies unchanged (`gate_disabled`).
- **Gate enabled + missing manifest** → blocks when `fail_closed=true`.
- Checks: candidate approved, human review (`reviewedAt`/`reviewedBy`), level ordering, expiry, manifest staleness, scope match.

### Candidate IDs

- `synthesis_text_promotion.{workflow}` — synthesis text promotion
- `specialist_text_promotion.{agent}` — specialist text promotion
- `workflow_promotion.{workflow}` — supervisor workflow promotion

### Integration points

- `synthesis/promotion_policy.py` — additional gate before Phase 22 checks; reason `runtime_readiness_gate_blocked`
- `specialists/text_promotion.py` — same gate for specialist text promotion
- `supervisor/promotion.py` — same gate for workflow promotion
- `orchestrator.py` — top-level `retrievalMetadata.runtimeReadiness` summary

### Controlled broader read-only promotion

Even when `AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS` includes multiple read-only workflows, promotion still requires runtime flags, Phase 22 gates, manifest approval, read-only workflow, no proposed actions, block preservation, monitor safety, clarification safety, and plan-repair safety.

Write workflows (`transcript_import_workflow`, `semester_planning_workflow`, `profile_update_workflow`) remain hard-blocked.

### CLI (draft manifest builder)

`services/agent/scripts/build_promotion_activation_manifest.py` — converts readiness report into a **draft** manifest; does not install into runtime config or modify `.env`.

### Diagnostics shape

Compact `runtimeReadiness` on promotion diagnostics and optional turn-level summary — no full manifest, eval report, candidate text, or chain-of-thought.

### Safety

- Fail closed when configured
- No auto-enabling from scorecard
- No writes / action proposals
- No direct LLM calls in readiness package
- Text-only promotion changes `response.text` only; blocks/warnings/sources/actions preserved

---

## Real-World Case Import + Full LLM Shadow Replay Lab — Phase 26

### Goal

Import anonymized real-world-like cases and run a **full LLM shadow replay lab** that exercises the internal reasoning/planning/synthesis stack while blocking all writes, action proposals, and production authority.

### Package extensions

`services/agent/app/agent/evaluation/`:

- `real_world_schemas.py` — stricter import schema (`RealWorldCaseInput`)
- `real_world_anonymizer.py` — conservative private-identifier scanner
- `real_world_importer.py` — convert/import/write EvalCase fixtures
- `side_effect_firewall.py` — lab-only write/action-proposal blocks
- `llm_trace_summary.py` — compact ReasoningBlock contract call summaries
- `full_shadow_runner.py` — `run_full_llm_shadow_eval_case()` lab pipeline
- `full_shadow_reporting.py` — extended sanitized reports

### Replay mode

New mode: `full_llm_shadow_replay` (requires `--allow-real-llm`).

Pipeline (lab only):

```text
TaskUnderstanding → Planner → Supervisor dry-run → Synthesis promotion gates (shadow_only)
```

Uses real `ReasoningBlock` only when explicitly allowed and no case mocks are provided; tests use `mock_reasoning_outputs` / patched runners.

### Config (defaults unchanged)

| Variable | Default |
|----------|---------|
| `AGENT_EVAL_FULL_LLM_SHADOW_ENABLED` | `false` |
| `AGENT_EVAL_FULL_LLM_REQUIRE_EXPLICIT_ALLOW` | `true` |
| `AGENT_EVAL_FULL_LLM_MAX_CASES` | `20` |
| `AGENT_EVAL_FULL_LLM_MAX_REASONING_CALLS_PER_CASE` | `20` |
| `AGENT_EVAL_FULL_LLM_MAX_TOTAL_REASONING_CALLS` | `200` |
| `AGENT_EVAL_SIDE_EFFECT_FIREWALL_ENABLED` | `true` |
| `AGENT_EVAL_REPORT_CONTRACT_CALLS` | `true` |

### CLIs

- `scripts/import_real_world_eval_cases.py` — import anonymized JSON/JSONL → EvalCase files
- `scripts/run_agent_replay_eval.py` — extended with `--mode full_llm_shadow_replay`, budgets, `--lab-config`

### Fixtures

`tests/fixtures/eval_cases_real_world_like/` — 10 synthetic-but-messy anonymized cases.

### Safety

- No real LLM unless `--allow-real-llm`
- Side-effect firewall blocks repository writes and action proposals
- Promotion remains `shadow_only` in lab settings
- Reports include contract call counts/latency/cost metadata only — no prompts, raw outputs, candidate text, or private data
- Production `/turn` behavior unchanged
