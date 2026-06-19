# UniPilot AI — Project Context (Source of Truth)

Last updated: 2026-06-19

This document is the primary context document for UniPilot AI implementation work.
Use it before starting major coding, architecture updates, or roadmap decisions.

If this file and another doc conflict:
1. Follow assignment requirements.
2. Follow accepted ADRs in `docs/decisions/`.
3. Update this file so it stays current.

## 1) Project Vision

UniPilot AI is an AI-powered academic decision support platform that helps students make better academic planning decisions (course/path planning, what-if analysis, and recommendations) through a reliable backend-first architecture.

Success means:
- Reliable first-run startup with Docker.
- Secure student data handling.
- Async AI workflows that do not block the API.
- Strong backend quality, testing, and clear documentation.

## 2) Course Assignment Requirements

Mandatory constraints:
- App must run on first try with Docker.
- Backend quality is the grading priority.
- Use at least two backend containers.
- Only API/web container may be exposed to clients.
- MongoDB, Redis, worker, and AI service stay internal.
- Persistent data must be stored in MongoDB.
- Passwords must be hashed with bcrypt (no plaintext).
- JWT authentication required for protected endpoints.
- Validate all request bodies.
- Rate limit auth and AI endpoints.
- Long AI requests must be async/background processed.
- Provide unit, integration, E2E/system, stress, and security tests.
- README must contain accurate run and test instructions.
- Team must show regular GitHub commits by all members.
- Final submission must include risk assessment and project report.

## 3) Current Architecture (As Implemented)

Current stage: **auth + student profile backend implemented** (in roadmap terms: Phase 0–1 complete + Phase 2 student profile CRUD implemented).

Architecture pattern:
- `api` receives client requests and exposes `/health`, auth routes, and protected `/student-profile` CRUD.
- `worker` and `ai` are internal services for async pipeline foundation.
- `redis` is queue/rate-limit infrastructure foundation.
- `mongo` is persistent data store (named volume).
- Internal Docker network for inter-service communication by service name.

Current behavior intentionally excludes completed courses, course catalog, and AI recommendation logic, but includes authentication and student profile CRUD with ownership enforcement.

## 4) Tech Stack

- Runtime: Node.js 20 (Alpine images)
- API framework: Express
- Database: MongoDB 7
- Queue/cache/rate-limit foundation: Redis 7
- Container orchestration: Docker Compose
- Testing (current): Jest + Supertest (API health test)
- Language: JavaScript (CommonJS)

## 5) Docker Services

| Service | Role | Host-exposed | Internal Port | Healthcheck | Notes |
|---|---|---|---|---|---|
| `api` | Client-facing backend API | Yes (host `API_PORT` -> container `3000`) | 3000 | Yes | Only service exposed to host |
| `mongo` | Persistent database | No | 27017 | Yes | Uses `mongo_data` named volume |
| `redis` | Queue/rate-limit foundation | No | 6379 | Yes | Internal-only |
| `worker` | Background worker skeleton | No | 3002 | Yes | Internal-only |
| `ai` | AI service skeleton | No | 3001 | Yes | Internal-only |

Networking and exposure rules:
- Only `api` may publish host ports.
- All services must stay on `unipilot-internal` network.
- Do not expose `mongo`, `redis`, `worker`, or `ai`.

## 6) Backend Folder Structure

```text
services/
  api/
    src/
      app.js
      server.js
      db/
      middleware/
      models/
      routes/
      security/
      validation/
    test/
      health.test.js
      unit/
      integration/
      security/
    Dockerfile
    package.json
  worker/
    src/
      index.js
    Dockerfile
    package.json
  ai/
    src/
      index.js
    Dockerfile
    package.json
docker-compose.yml
.env.example
README.md
docs/
  architecture/
  planning/
  reports/
  decisions/
```

## 7) Testing Strategy

Target strategy (required by assignment):
1. Unit tests
2. Integration tests
3. E2E/system tests
4. Stress tests
5. Security tests

Coverage target: **>= 80%**.

Current implemented tests:
- API health test.
- Auth unit tests (password hashing, JWT utilities, auth payload validation).
- Auth integration tests (register/login behavior against MongoDB in-memory instance).
- Auth security tests (protected route JWT checks + auth rate limiting behavior).
- Student profile unit tests (payload validation).
- Student profile integration tests (create/read/update/delete for authenticated user).
- Student profile security tests (auth required, ownership isolation).

Near-term testing priorities:
- Add integration tests for container/dependency wiring.
- Add Docker smoke test script/CI gate for first-run reliability.

## 8) Security Requirements

Current enforced foundation:
- Internal-only service exposure (except API).
- Environment-based secrets/config.
- Non-root runtime users in service containers.
- `.env` ignored by git.

Required and currently implemented:
- JWT auth middleware and protected auth route.
- bcrypt password hashing in auth flow (no plaintext storage).
- Schema-based validation on auth inputs.
- Auth endpoint rate limiting.
- Student profile model with unique `userId` index.
- Protected student profile CRUD (`POST/GET/PUT/DELETE /student-profile`).
- Ownership checks: users can only access/modify their own profile.

Still pending for next phases:
- AI endpoint rate limiting.

## 9) Development Roadmap

Canonical roadmap: `docs/planning/IMPLEMENTATION_PHASES.md` and `docs/planning/FEATURE_BACKLOG.md`.

Practical sequence:
1. Foundation (done): Docker skeleton + health + internal networking.
2. Auth foundation (done): user model, register/login, JWT, bcrypt, validation, auth rate limiting.
3. Student domain (in progress): student profile CRUD done; completed courses/catalog pending.
4. Async AI pipeline: enqueue, worker processing, status/result flow.
5. AI decision features.
6. Hardening, stress/security testing, documentation, risk/final report.

## 10) What Has Already Been Implemented

- Multi-service Docker Compose stack (`api`, `mongo`, `redis`, `worker`, `ai`).
- Healthchecks and startup ordering for core dependencies.
- MongoDB named volume persistence (`mongo_data`).
- Only API service host exposure (internal-only for other services).
- API `/health` endpoint and auth endpoints (`/auth/register`, `/auth/login`, `/auth/me`).
- Student profile endpoints (`POST/GET/PUT/DELETE /student-profile`) with JWT protection and ownership checks.
- bcrypt password hashing, JWT token issuance, and protected-route middleware.
- Auth validation and auth rate limiting middleware.
- Student profile validation schemas and MongoDB model/indexes.
- Auth and student profile test suites (unit + integration + security) in addition to health test.
- Service Dockerfiles with deterministic install (`npm ci`) and non-root users.
- Core project workflow/rules/prompts/playbooks/ADRs documentation scaffold.

## 11) What Should NOT Change Without Discussion

Discuss with the team before changing any of these:
- Only-API-exposed network policy.
- MongoDB as the persistent source of truth.
- Redis-backed async/queue architecture direction.
- Backend-first scope and phase order.
- Security baseline requirements (JWT, bcrypt, validation, rate limits).
- Testing requirement categories and >=80% coverage target.
- Docker first-run reliability as a non-negotiable requirement.
- Accepted architecture decisions in `docs/decisions/0001-system-architecture.md`.

## 12) Working Agreement for Contributors

Before major implementation work:
1. Read this file (`docs/PROJECT_CONTEXT.md`).
2. Read `docs/planning/IMPLEMENTATION_PHASES.md` for current phase.
3. Read relevant rule files in `.cursor/rules/unipilot-*.mdc`.
4. Implement one feature at a time and update docs/tests with each feature.
