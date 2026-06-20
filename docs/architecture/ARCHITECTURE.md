# UniPilot AI — Architecture

Last updated: 2026-06-20

UniPilot AI is an AI-powered academic decision support platform. It helps students make academic decisions (course/path planning, recommendations, what-if analysis) backed by deterministic planners today and an async AI service in later phases.

## Design Principles

- **Backend-first.** Graded primarily on backend quality.
- **First-run Docker reliability.** One command brings the system up.
- **Least exposure.** Only the API container is reachable by clients.
- **Async by default for AI.** Long AI requests must not block the API (future phase).
- **Persistence in MongoDB.** All durable state lives in MongoDB.

## Containers

| Container | Role | Client-facing | Notes |
|-----------|------|---------------|-------|
| `api` | FastAPI HTTP API | **Yes (only this one)** | Auth, validation, rate limiting, catalog, planners |
| `data-engineering` | Catalog ingestion CLI | No | Staging import, quality gates, guarded production promotion |
| `worker` | Background job processor | No | Stub; future Redis queue consumer |
| `ai` | Internal AI/inference service | No | Stub; future model/provider wrapper |
| `mongo` | MongoDB database | No | Persistent data; named volume `mongo_data` |
| `redis` | Queue + rate-limit store | No | Auth rate limits; future job queue |

Minimum requirement: **at least two backend containers**. Current layout: `api` + `worker` + `ai` + `data-engineering`.

## Request Flows

### Synchronous (implemented)

```
Client → api (FastAPI) → MongoDB
              ↑
       JWT + Pydantic validation + rate limit
```

Covers auth, student profile, catalog reads, completed courses, graduation progress, semester plans, and academic risk analysis.

### Asynchronous (planned — AI phase)

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

## Cross-Cutting Concerns

### Authentication & Authorization
- JWT issued at login/register; verified on protected routes.
- Student-owned resources enforce ownership (`token.sub` == resource `userId`).

### Passwords
- bcrypt hashing (cost ≥ 10). Never stored or returned in plaintext.

### Validation
- Pydantic schema validation at every boundary. AI responses treated as untrusted when implemented.

### Rate Limiting
- Redis-backed limits on auth endpoints. AI endpoint limits planned with AI phase.

### Secrets & Config
- All secrets via environment variables; `.env.example` committed. Required secrets validated at startup.

### Networking
- Internal Docker network (`unipilot-internal`) for service-to-service calls by name.
- Only `api` publishes a host port (`API_PORT` → container `8000`).

## Data Stores

- **MongoDB** (`MONGO_DB`, default `unipilot_python`): users, profiles, completed courses, semester plans, academic risks, and promoted Technion DDS catalog collections (`courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`).
- **Redis**: rate-limiting counters (and future job queue). Not a source of truth.

## Component Diagram

```
                 ┌─────────────┐
   Client  ───▶  │  api (API)  │  (only exposed container)
                 └──────┬──────┘
            enqueue     │ read/write
                 ┌──────▼──────┐        ┌──────────────┐
                 │    redis    │◀──────▶│    worker    │
                 └─────────────┘  jobs  └──────┬───────┘
                                               │ call
                 ┌─────────────┐        ┌──────▼───────┐
                 │   mongo     │◀──────▶│  ai service  │
                 └─────────────┘        └──────────────┘
                        ▲
                        │ promote (CLI)
                 ┌──────┴──────────────┐
                 │  data-engineering   │  (internal)
                 └─────────────────────┘
```

## Related Documents

- Index: `docs/README.md`
- Status: `docs/PROJECT_CONTEXT.md`
- API: `docs/API_SPEC.md`
- Phases: `docs/planning/IMPLEMENTATION_PHASES.md`
- Backlog: `docs/planning/FEATURE_BACKLOG.md`
- Ingestion: `docs/DATA_INGESTION_ARCHITECTURE.md`
- Promotion CLI: `services/data-engineering/README.md`
