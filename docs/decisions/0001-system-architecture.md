# ADR-0001: System Architecture

- **Status:** Accepted
- **Date:** 2026-06-19
- **Deciders:** UniPilot AI team
- **Related:** `docs/architecture/ARCHITECTURE.md`, `.cursor/rules/unipilot-*.mdc`

## Context
UniPilot AI is an AI-powered academic decision support platform graded primarily on backend quality. The assignment imposes hard constraints: the app must run first-try with Docker, use at least two backend containers, expose only the API/web container, keep MongoDB/Redis/worker/AI internal, persist data in MongoDB, authenticate with JWT, hash passwords with bcrypt, protect student endpoints, rate-limit auth and AI endpoints, process long AI requests asynchronously, and ship unit/integration/E2E/stress/security tests plus README, final report, and risk assessment.

We need a single, agreed architecture before implementation so every feature fits the constraints.

## Decision
We will build a multi-container backend orchestrated by Docker Compose:

- **`api`** — the only client-facing container. Handles HTTP, JWT auth, request validation, rate limiting, and enqueues long AI jobs. Stateless.
- **`worker`** — internal background processor. Consumes the Redis queue, calls the internal AI service, and writes job results to MongoDB.
- **`ai`** — internal AI/inference service wrapping the model/provider. Never exposed to clients.
- **`mongo`** — MongoDB, the single source of truth for persistent data (users, jobs, results, academic data). Data persisted on a named volume.
- **`redis`** — job queue for async AI processing and shared store for rate limiting. Not a source of truth.

Long AI requests are handled asynchronously: the API validates + authenticates the request, enqueues a job, and returns `202 Accepted` with a job id. The worker processes it; the client polls a protected status/result endpoint. Auth uses JWT; passwords are bcrypt-hashed; student endpoints enforce ownership; auth and AI endpoints are rate-limited via Redis. All secrets come from environment variables with a committed `.env.example`. Only the `api` container publishes a host port.

## Alternatives Considered
- **Single monolithic container** — simplest, but violates the "at least two backend containers" rule and couples slow AI work to the request path. Rejected.
- **Synchronous AI calls in the API** — simpler control flow, but blocks the API on long model calls and risks timeouts/poor resilience. Rejected in favor of async queue + worker.
- **SQL database instead of MongoDB** — viable generally, but the assignment mandates MongoDB persistence. Rejected.
- **Exposing the AI service directly** — simpler integration, but violates the internal-only exposure rule and widens the attack surface. Rejected.

## Consequences
- **Positive:** Meets all mandatory constraints; clean separation of concerns; resilient to slow/failed AI calls; scalable (stateless API, shared Redis); least exposure.
- **Negative / trade-offs:** More moving parts; requires healthchecks/retry for first-run reliability; async flow adds a polling/status mechanism and job-state management.
- **Follow-ups:** Implement Phase 0 skeleton (compose + healthchecks + `.env.example`); define job-state schema; add stress tests for the queue; document run/test steps in README.

## Compliance Check
- [x] Backend-first
- [x] Docker first-run reliability preserved
- [x] Only API exposed; internal services stay internal
- [x] MongoDB remains source of truth
- [x] Async AI via Redis + worker
- [x] Security (JWT, bcrypt, validation, rate limiting) addressed
- [x] Test + documentation impact captured
