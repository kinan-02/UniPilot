# UniPilot AI — Feature Backlog

Ordered, backend-first backlog. Pick ONE item at a time, plan it (prompt 02), implement with TDD (prompt 03), test (prompt 04), review (prompt 05), then commit.

Legend — Priority: P0 (must), P1 (should), P2 (nice). Status: `todo` / `in-progress` / `done`.

## Infrastructure
| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| INF-1 | Docker Compose with api/worker/ai/mongo/redis | P0 | 0 | todo |
| INF-2 | Only API exposed; others internal-only | P0 | 0 | todo |
| INF-3 | Healthchecks + startup retry/reconnect | P0 | 0 | todo |
| INF-4 | `.env.example` + env-based config + startup secret validation | P0 | 0 | todo |
| INF-5 | MongoDB named volume persistence | P0 | 0 | todo |
| INF-6 | `/health` endpoint on api | P1 | 0 | todo |

## Authentication & Security
| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| AUTH-1 | User model + unique email index | P0 | 1 | todo |
| AUTH-2 | Register with bcrypt hashing | P0 | 1 | todo |
| AUTH-3 | Login + JWT issuance | P0 | 1 | todo |
| AUTH-4 | JWT verification middleware | P0 | 1 | todo |
| AUTH-5 | Request body validation (auth routes) | P0 | 1 | todo |
| AUTH-6 | Rate limiting on auth endpoints (Redis) | P0 | 1 | todo |
| AUTH-7 | Ownership/authorization checks | P0 | 2 | todo |

## Student Domain
| ID | Feature | Priority | Phase | Status |
|----|---------|----------|-------|--------|
| STU-1 | Student profile model + protected CRUD | P0 | 2 | todo |
| STU-2 | Academic data model (courses/grades/goals) | P0 | 2 | todo |
| STU-3 | Validation + consistent response envelope | P0 | 2 | todo |

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
| QA-1 | Stress tests (auth + AI) | P0 | 5 | todo |
| QA-2 | Security test suite (401/403/400/429) | P0 | 5 | todo |
| QA-3 | Coverage ≥ 80% across suites | P0 | 5 | todo |
| DOC-1 | README run + test instructions | P0 | 6 | todo |
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

- **STU-FUTURE-1:** Validate `StudentProfile.degreeId` against the profile's `institutionId` and `catalogYear` once catalog selection UX and multi-catalog support are implemented. (Current Phase 4 behavior only checks that the referenced degree exists and is published.)
