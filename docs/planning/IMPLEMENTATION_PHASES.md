# UniPilot AI — Implementation Phases

Build the project **feature by feature**, backend-first. Do not implement everything at once. Each phase ends with tests, README updates, and commits from team members.

## Phase 0 — Project Skeleton & Docker First-Run
**Goal:** the empty system boots with one command.
- `docker-compose.yml` with `api`, `worker`, `ai`, `mongo`, `redis`.
- Only `api` exposes a host port; others internal.
- Healthchecks + startup retry so the app never crash-loops on ordering.
- `.env.example` with all required vars; config loaded from env.
- MongoDB named volume for persistence.
- Health endpoint on `api`.
- **Exit criteria:** `docker compose up --build` works from clean clone; only API reachable.

## Phase 1 — Auth Foundation
**Goal:** secure accounts.
- User model in MongoDB (unique email index).
- Register/login with bcrypt password hashing.
- JWT issuance + verification middleware.
- Request body validation on auth routes.
- Rate limiting on auth endpoints (Redis-backed).
- **Exit criteria:** unit + integration + security tests pass; README auth section added.

## Phase 2 — Protected Student Domain
**Goal:** student-owned academic data.
- Student/profile + academic data models.
- Protected CRUD endpoints with ownership checks.
- Full validation; consistent response envelope.
- **Exit criteria:** integration + security tests for auth/ownership; coverage ≥ 80%.

## Phase 3 — Async AI Pipeline
**Goal:** long AI requests handled in background.
- Redis job queue; `worker` consumer.
- Internal `ai` service integration (provider/model wrapper).
- Job model with states (pending/processing/completed/failed) in MongoDB.
- API: enqueue endpoint (`202` + job id) + status/result endpoint.
- Rate limiting on AI endpoints; AI output validated.
- **Exit criteria:** E2E test of enqueue→process→result; stress test on AI endpoint + queue.

## Phase 4 — AI Decision Features
**Goal:** the actual academic decision support value.
- Recommendation / what-if / planning features on top of the async pipeline (see backlog).
- **Exit criteria:** per-feature unit/integration/E2E tests; README usage examples.

## Phase 5 — Hardening & Stress/Security Testing
**Goal:** prove robustness.
- Stress tests on auth + AI endpoints.
- Security test suite (401/403/400/429, no plaintext passwords).
- Error-handling and logging review (no leaks).
- **Exit criteria:** all five test types green; coverage ≥ 80%.

## Phase 6 — Documentation, Risk & Demo Prep
**Goal:** submission-ready.
- README finalized and verified.
- `RISK_ASSESSMENT.md` finalized from template.
- `TEST_REPORT.md` filled from template.
- Final project report assembled.
- Verify all team members have GitHub commits.
- **Exit criteria:** prompt `09-final-demo-prep.md` checklist fully green.

## Cadence (every phase)
1. Plan (prompt 02) → 2. Implement TDD (prompt 03) → 3. Tests (prompt 04) → 4. Security review (prompt 05) → 5. Docker check (prompt 06) → 6. README (prompt 07) → 7. Commit (conventional, each member contributing).
