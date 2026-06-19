# UniPilot AI Architecture Freeze

Last updated: 2026-06-19  
Source of truth inputs: `docs/PROJECT_CONTEXT.md`, `docs/DOMAIN_MODEL.md`, `docs/decisions/0001-system-architecture.md`

This document defines architecture decisions that are considered frozen for the MVP and early implementation phases.

## 1) Freeze Intent

- Preserve backend-first delivery and assignment compliance.
- Prevent accidental scope creep and architectural churn.
- Force explicit discussion before changing critical system decisions.

## 2) Docker Services (Frozen Baseline)

### Required service topology
- `api` (client-facing HTTP API)
- `mongo` (persistence)
- `redis` (queue + rate-limit infrastructure)
- `worker` (background processing)
- `ai` (internal AI service)

### Exposure rules
- Only `api` may publish host ports.
- `mongo`, `redis`, `worker`, `ai` remain internal-only.

### Runtime expectations
- `docker compose up --build` works from clean clone.
- Healthchecks must exist for all services.
- MongoDB uses named volume persistence.

## 3) API Architecture (Frozen)

- API stack: Node.js + Express.
- API owns:
  - auth endpoints
  - input validation
  - ownership/authorization checks
  - rate limiting at HTTP boundary
  - orchestration of async jobs (later phases)
- Standard response envelope:
  - `success`, `data`, `error`
- Protected endpoint policy:
  - JWT required
  - ownership predicate (`userId == token.sub`) for student-owned resources

## 4) Database Architecture (Frozen)

- Primary persistence: MongoDB only.
- Redis is not a durable source of truth.
- Collection modeling follows `docs/DATABASE_SCHEMA.md`.
- Student-owned documents require `userId`.
- Catalog entities are shared/read-only for student APIs.

## 5) Worker + AI Service Architecture (Frozen)

- Long-running AI operations must be asynchronous.
- API does not block on AI inference for long operations.
- Worker consumes queued jobs, calls internal AI service, persists results.
- AI service is internal-only and never directly client-facing.

## 6) Security Rules (Frozen)

- No plaintext password storage.
- bcrypt hashing for credential persistence.
- JWT auth with expiration for protected routes.
- Request validation required on all write endpoints.
- Rate limiting required on auth and AI-trigger endpoints.
- Secrets must come from environment variables; no hardcoded secrets.

## 7) Testing Expectations (Frozen)

Required test categories for course compliance:
- Unit
- Integration
- E2E/system
- Stress
- Security

Minimum quality bar:
- >=80% coverage target (project rule baseline).
- Tests must be deterministic and runnable via documented commands.
- Auth/security tests must include invalid JWT and protected-route checks.

## 8) MVP Boundaries (Freeze Scope)

### In MVP design scope
- Auth
- Student profile
- Completed courses
- Course catalog
- Degree requirements
- Graduation progress
- Semester plans

### Explicitly out of MVP
- Full AI advisor endpoints
- Full simulation endpoints
- Advanced advisor workflows and collaboration features
- Complex requirement DSL execution engine

## 9) What Must Not Change Without Discussion

The following require explicit team discussion and ADR update before changing:
- Service topology (`api` + `mongo` + `redis` + `worker` + `ai`)
- Only-API-exposed network policy
- MongoDB as persistent system of record
- Async worker-mediated AI pattern
- Ownership-based authorization strategy
- Security baseline (bcrypt + JWT + validation + rate limits)
- Required test categories and quality gates

## 10) Change Control Process

Before changing frozen architecture:
1. Document rationale and trade-offs.
2. Update/add ADR in `docs/decisions/`.
3. Update `docs/PROJECT_CONTEXT.md`, `docs/API_SPEC.md`, and `docs/DATABASE_SCHEMA.md`.
4. Confirm no assignment requirement is violated.

No implementation should proceed on changed architecture until this process is complete.
