# UniPilot AI — Phase 1 Dockerized Backend Skeleton

UniPilot AI is an AI-powered academic decision support platform.  
This repository currently implements **Phase 1 skeleton infrastructure only**:

- Dockerized backend services
- Health endpoint in the API
- Basic API health test

Authentication, authorization, and business features are intentionally not implemented yet.

## Services

- `api` (Node.js/Express) — **only exposed service**
- `worker` (Node.js/Express health stub) — internal only
- `ai` (Node.js/Express health/infer stub) — internal only
- `mongo` (MongoDB) — internal only, persisted via volume
- `redis` (Redis) — internal only, queue/rate-limit foundation

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ (only needed for local test execution)

## Setup

```bash
cp .env.example .env
```

Security note: `.env.example` contains local development defaults. Replace secret values (especially `JWT_SECRET` and `MONGO_ROOT_PASSWORD`) before any non-local deployment.

## Run (First-Try Docker)

```bash
docker compose up --build
```

API health URL:

- `http://localhost:<API_PORT>/health`

Example with defaults from `.env.example`:

- [http://localhost:3000/health](http://localhost:3000/health)

## Stop and Clean

```bash
docker compose down -v
```

## Run Tests

Basic API health test:

```bash
cd services/api
npm install
npm test
```

## Notes

- Only the API service exposes a host port (`3000` by default).
- MongoDB data is persisted in the `mongo_data` named volume.
- Worker and AI service are skeleton stubs prepared for async queue flow in later phases.
