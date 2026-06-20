# UniPilot AI — Feature Backlog

Last updated: 2026-06-20

Ordered, backend-first backlog. **Current implementation status:** see `docs/PROJECT_CONTEXT.md` §9–10. FastAPI (`services/api`) is the sole API.

Pick ONE open item at a time: plan (prompt 02) → TDD (prompt 03) → test (prompt 04) → security review (prompt 05) → commit.

Legend — Priority: P0 (must), P1 (should), P2 (nice). Status: `todo` / `in-progress` / `done`.

## Infrastructure

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| INF-1 | Docker Compose with api/worker/ai/mongo/redis/data-engineering | P0 | 0 | done |
| INF-2 | Only API exposed; others internal-only | P0 | 0 | done |
| INF-3 | Healthchecks + startup retry/reconnect | P0 | 0 | done |
| INF-4 | `.env.example` + env-based config + startup secret validation | P0 | 0 | done |
| INF-5 | MongoDB named volume persistence | P0 | 0 | done |
| INF-6 | `/health` endpoint on api | P1 | 0 | done |

## Authentication & Security

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| AUTH-1 | User model + unique email index | P0 | 1 | done |
| AUTH-2 | Register with bcrypt hashing | P0 | 1 | done |
| AUTH-3 | Login + JWT issuance | P0 | 1 | done |
| AUTH-4 | JWT verification middleware | P0 | 1 | done |
| AUTH-5 | Request body validation (auth routes) | P0 | 1 | done |
| AUTH-6 | Rate limiting on auth endpoints (Redis) | P0 | 1 | done |
| AUTH-7 | Ownership/authorization checks | P0 | 2 | done |

## Student Domain

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| STU-1 | Student profile model + protected CRUD | P0 | 2 | done |
| STU-2 | Completed courses (transcript records) | P0 | 5 | done |
| STU-3 | Validation + consistent response envelope | P0 | 2 | done |

## Catalog & Academic Logic

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| CAT-1 | Production DDS catalog read APIs (`/catalog/*`) | P0 | 13 | done |
| CAT-2 | Data-engineering staging + promotion pipeline | P0 | 4–12 | done |
| CAT-3 | Graduation progress (deterministic) | P0 | 15 | done |
| CAT-4 | Semester planner (generate + manual + versioning) | P0 | 16 | done |
| CAT-5 | Academic risk analyzer (deterministic) | P0 | 17 | done |

## Async AI Pipeline

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| AI-1 | Redis job queue + worker consumer | P0 | 3 | todo |
| AI-2 | Internal AI service integration | P0 | 3 | todo |
| AI-3 | Job model + states in MongoDB | P0 | 3 | todo |
| AI-4 | Enqueue endpoint (202 + job id) | P0 | 3 | todo |
| AI-5 | Job status/result endpoint (protected) | P0 | 3 | todo |
| AI-6 | Rate limiting on AI endpoints | P0 | 3 | todo |
| AI-7 | AI response validation + timeouts/retries | P0 | 3 | todo |

## AI Decision Features

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| DEC-1 | Course/path recommendation request | P1 | 4 | todo |
| DEC-2 | "What-if" academic scenario analysis | P1 | 4 | todo |
| DEC-3 | Decision history per student | P2 | 4 | todo |

## Quality & Delivery

| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| QA-1 | Stress tests (auth + planners) | P0 | 5 | done |
| QA-2 | Security test suite (401/403/400/429) | P0 | 5 | done |
| QA-3 | Coverage ≥ 80% across suites | P0 | 5 | in-progress |
| QA-4 | Docker E2E verify script | P1 | — | done |
| DOC-1 | README run + test instructions | P0 | 6 | done |
| DOC-2 | Final risk assessment | P0 | 6 | todo |
| DOC-3 | Test report | P0 | 6 | todo |
| DOC-4 | Final project report | P0 | 6 | todo |

## Acceptance Criteria Template (per feature)

- API contract defined (route, body schema, response, status codes, auth).
- Data model + indexes defined.
- Validation + (where needed) auth + rate limiting applied.
- Unit + integration + (relevant) E2E/stress/security tests added.
- README/docs updated; committed with a conventional message.

## Future TODOs

Deferred tasks that depend on later UX or multi-catalog work:

- **STU-FUTURE-1:** Validate `StudentProfile.degreeId` against the profile's `institutionId` and `catalogYear` once catalog selection UX and multi-catalog support are implemented.
