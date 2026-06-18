# UniPilot AI — Architecture

UniPilot AI is an AI-powered academic decision support platform. It helps students make academic decisions (e.g. course/path planning, recommendations, what-if analysis) backed by an AI service, with long-running AI work handled asynchronously.

This document describes the intended target architecture. Keep it in sync with the real system as features land.

## Design Principles
- **Backend-first.** The project is graded primarily on backend quality.
- **First-run Docker reliability.** One command brings the whole system up.
- **Least exposure.** Only the API container is reachable by clients.
- **Async by default for AI.** Long AI requests never block the API.
- **Persistence in MongoDB.** All durable state lives in MongoDB.

## Containers

| Container | Role | Client-facing | Notes |
|-----------|------|---------------|-------|
| `api` | HTTP API / web gateway | **Yes (only this one)** | Auth, validation, rate limiting, enqueues AI jobs |
| `worker` | Background job processor | No | Consumes Redis queue, calls AI service, writes results to MongoDB |
| `ai` | Internal AI/inference service | No | Wraps the model/provider; only reachable internally |
| `mongo` | MongoDB database | No | Persistent data; named volume |
| `redis` | Queue + rate-limit store | No | Job queue + shared rate limiting |

Minimum requirement: **at least two backend containers**. Target layout uses `api` + `worker` + `ai`.

## Request Flows

### Synchronous (auth, CRUD)
```
Client → api → MongoDB
                ↑
         JWT verify + schema validation + rate limit
```

### Asynchronous (AI request)
```
Client → api  (validate, auth, rate limit)
          │  enqueue job
          ▼
        redis (queue)
          │
          ▼
        worker → ai service → provider/model
          │
          ▼
        MongoDB (job: pending → processing → completed/failed)

Client polls:  api → MongoDB → job status / result
```

The API responds immediately (e.g. `202 Accepted` + job id). The client polls a status endpoint until the job completes.

## Cross-Cutting Concerns

### Authentication & Authorization
- JWT issued at login/register; verified by middleware on protected routes.
- Student-specific endpoints require auth + ownership checks (token user id must match resource owner).

### Passwords
- bcrypt hashing (cost ≥ 10). Never stored or returned in plaintext.

### Validation
- Schema validation at every boundary (request bodies, params, query). AI responses validated as untrusted input.

### Rate Limiting
- Redis-backed limits on auth and AI endpoints. `429` on exceed.

### Secrets & Config
- All secrets via environment variables; `.env.example` committed. Required secrets validated at startup.

### Networking
- Internal Docker network for service-to-service calls by name.
- Only `api` publishes a host port.

## Data Stores
- **MongoDB**: users, jobs, AI results, student academic data. Indexes on user id, email (unique), job status.
- **Redis**: job queue + rate-limiting counters. Not a source of truth for durable data.

## Component Diagram

```
                 ┌─────────────┐
   Client  ───▶  │     api     │  (only exposed container)
                 └──────┬──────┘
            enqueue     │ read/write
                 ┌──────▼──────┐        ┌──────────────┐
                 │    redis    │◀──────▶│    worker    │
                 └─────────────┘  jobs  └──────┬───────┘
                                               │ call
                 ┌─────────────┐        ┌──────▼───────┐
                 │   mongo     │◀──────▶│  ai service  │
                 └─────────────┘ persist└──────────────┘
```

## Related Documents
- Phases: `docs/planning/IMPLEMENTATION_PHASES.md`
- Backlog: `docs/planning/FEATURE_BACKLOG.md`
- Risk: `docs/reports/RISK_ASSESSMENT_TEMPLATE.md`
- Tests: `docs/reports/TEST_REPORT_TEMPLATE.md`
- Rules: `.cursor/rules/unipilot-*.mdc`
