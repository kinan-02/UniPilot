# UniPilot Agent / MAS Overhaul Plan

Last updated: 2026-07-03

Source of truth: [`Agent_spec.md`](../../Agent_spec.md) at repo root.

## Decision

Replace the session-based MAS negotiation runtime (`services/mas`) with a **supervisor orchestrator** inside `services/api`, exposed as the single user-facing **UniPilot Agent**.

| Aspect | Old (`services/mas`) | New (`services/api/app/agent`) |
|--------|----------------------|--------------------------------|
| UX model | Goal → multi-agent negotiation session | Conversation → intent → workflow → structured reply |
| API | `POST /agent/sessions` | `POST /agent/conversations`, `POST .../messages` (SSE) |
| Truth source | Mixed graph + API bootstrap | Mongo → offerings JSON → catalog → Obsidian RAG |
| LLM role | Planner proposes courses | Explains deterministic service outputs |
| Persistence | `agent_sessions` | `agent_conversations`, `agent_messages`, `agent_runs`, `agent_steps`, … |

The old MAS container remains temporarily for backward compatibility; new work lands in the API agent module.

## Implementation phases (from spec §38)

| Phase | Scope | Status |
|-------|--------|--------|
| **1** | Conversations, messages, runs, SSE, orchestrator skeleton, response schema | **Done** |
| **2** | Entity resolver, retrieval planner, context builder/validator, Mongo + offerings + wiki retrievers, `AgentContextPack` | **Done** |
| **3** | Graduation progress workflow (audit, matching, rich blocks) | **Done** |
| **4** | Course question workflow | **Done** |
| **5** | Transcript import workflow | **Done** |
| **6** | Semester planning workflow | **Done** |
| **7** | Agentic RAG tuning, reranking, optimization | **Done** |

## Phase 7 deliverables (advanced agentic RAG)

- Locked retrieval profiles in `app/retrieval/profile_config.json` (9 profiles)
- `profiles.py` — intent → profile mapping, rerank boosts, token budgets
- Profile-aware hybrid wiki retriever (BM25 + semantic weights, link expansion)
- Context Builder logs `retrieval_profile` + `retrieval_metadata` on `AgentContextPack`
- **Query decomposition** — `app/agent/query_decomposer.py` (rules-first sub-queries)
- **Multi-step wiki retrieval** — merged snippets via `app/agent/wiki_context_merger.py`
- **Validation-driven refinement** — `app/agent/retrieval_gaps.py`, `app/agent/retrieval_refiner.py`
- **Advanced explanation context** — `app/agent/explanation_enricher.py` → `wikiExplanationSummary`
- **Optional LLM validation** — `app/agent/llm_answer_validator.py` (`AGENT_LLM_VALIDATION_ENABLED`)
- Evaluation: `benchmark_cases.jsonl`, `retrieval_metrics.py`, `run_retrieval_eval.py`
- Regression tests in `tests/retrieval/` and `tests/unit/test_agentic_retrieval.py`
- Docs: `docs/agent/RAG_FINE_TUNING_SPEC.md`, `docs/agent/RAG_EVALUATION_RESULTS.md`

## Phase 6 deliverables

- `SemesterPlanningWorkflow` — deterministic multi-option planning via existing suggestion services
- `semester_planning_service` — Balanced / Lighter / Faster progress variants with schedule optimization
- Structured blocks: `SemesterPlanOptionsBlock`, `SchedulePreviewBlock`, `ConfirmationBlock`
- `save_semester_plan` action proposals — draft plan saved only after user confirms
- Entity extraction: `maxCredits`, `avoidDays`, `planningObjective`, `next semester`

## Phase 5 deliverables

- `TranscriptImportWorkflow` — parse, catalog match, duplicate detection, review table
- `transcript_review_service`, `transcript_import_response_builder`
- `agent_action_proposals` persistence + confirm/reject routes
- Multipart PDF upload on `POST /agent/conversations/{id}/messages`
- JSON `attachments` with pre-parsed `parsePreview` (e.g. after `/transcript-import/parse`)
- `TranscriptReviewBlock`, `ConfirmationBlock`, `action.proposed` SSE event
- No silent import — `commit_transcript_import` runs only after user confirms

## Phase 4 deliverables

- `CourseQuestionWorkflow` — eligibility, offering, contribution, and prerequisite analysis
- `course_question_service`, `requirement_contribution_service`
- Structured blocks: `CourseRecommendationBlock`, `PrerequisiteStatusBlock`, `OfferingStatusBlock`
- Catalog retriever: `requirement_contribution` query + prerequisite validation
- Intent router: course questions without explicit course numbers
- Integration tests: contribution question + missing course number clarification

## Phase 1 deliverables

- Mongo collections: `agent_conversations`, `agent_messages`, `agent_runs`, `agent_steps`
- JWT-protected routes under `/agent/conversations`
- SSE event types per spec §26 (`agent.step.*`, `message.*`, `structured_output`, `run.*`)
- Rules-first `IntentRouter` (no LLM required for MVP)
- `TaskPlanner` maps intent → workflow name
- `AgentOrchestrator` runs pipeline with hard limits
- `graduation_progress_workflow` wired to existing `graduation_progress_service` (first real workflow)
- Placeholder workflow for unsupported intents

## Reuse from existing codebase

| New component | Reuses |
|---------------|--------|
| Graduation workflow | `graduation_progress_service.get_graduation_progress_for_user` |
| Course question (Phase 4) | `catalog_repository`, `prerequisite_resolver`, offerings JSON |
| Transcript import (Phase 5) | `transcript_import_service`, `transcript-parser` |
| Semester planning (Phase 6) | `semester_plan_suggestion_service`, `planning/*` |
| Wiki RAG (Phase 2) | Obsidian vault mount (`ACADEMIC_WIKI_PATH`), future indexer |
| Auth / rate limits | Existing JWT + `enforce_ai_rate_limit` |

## Deprecation path for `services/mas`

1. Phase 1–3: New agent API live; old `/agent/sessions` unchanged.
2. Phase 4+: Web UI migrates to conversation UI; sessions page becomes legacy.
3. Final: Remove `mas` from `docker-compose.yml`, archive `services/mas`, delete session routes.

## Design rules (non-negotiable)

1. Structured truth first, RAG second, LLM last.
2. One visible UniPilot Agent; internal workflows are not user-facing agents.
3. All workflows consume the same `AgentContextPack` (Phase 2+).
4. No write without user confirmation (`agent_action_proposals`).
5. Max retrieval attempts per run: 2–3; no infinite loops.
