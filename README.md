# UniPilot AI — Phase 4 Catalog Backend

UniPilot AI is an AI-powered academic decision support platform.  
This repository currently implements backend foundation plus **authentication**, **student profile CRUD**, and **read-only Technion-style course catalog / degree requirements**:

- Dockerized backend services
- Health endpoint in the API
- Register/login endpoints
- bcrypt password hashing
- JWT access tokens
- Protected auth route middleware
- Input validation and auth rate limiting
- Protected student profile CRUD (`/student-profile`)
- Curated Technion CS/SE catalog seed data (2025)
- Read-only catalog endpoints (`/courses`, `/degrees`)
- Catalog seed command for MongoDB
- Unit, integration, and security tests

Completed courses, graduation progress, semester planning, and AI features are intentionally not implemented yet.

## Services

- `api` (Node.js/Express) — **only exposed service**
- `worker` (Node.js/Express health stub) — internal only
- `ai` (Node.js/Express health/infer stub) — internal only
- `mongo` (MongoDB) — internal only, persisted via volume
- `redis` (Redis) — internal only, queue/rate-limit foundation

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for local tests and host-side seed command)

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

## Seed Technion Catalog (Phase 4)

After Docker is running, load the curated Technion CS catalog into MongoDB:

```bash
docker compose exec api node src/scripts/seedCatalogCli.js --institution technion --catalogYear 2025
```

From the host (requires local `MONGO_URI`):

```bash
cd services/api
npm install
MONGO_URI="mongodb://unipilot:unipilot_dev_password@localhost:27017/unipilot?authSource=admin" npm run seed:catalog
```

Seed data lives in `data/validated/technion/2025/` (1 degree, 12 courses, 4 requirements).

**Important:** This is **curated placeholder data** for development and demos (`metadata.isCuratedPlaceholder: true`). It is not scraped from official Technion sources.

## Stop and Clean

```bash
docker compose down -v
```

## Run Tests

API tests (health + auth + student profile + catalog unit/integration/security):

```bash
cd services/api
npm install
npm test
```

Run focused suites:

```bash
cd services/api
npm run test:unit
npm run test:integration
npm run test:security
```

## Auth API

### Register

- `POST /auth/register`

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

### Login

- `POST /auth/login`

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

### Get Current User (Protected)

- `GET /auth/me`
- Header: `Authorization: Bearer <accessToken>`

## Student Profile API (Protected)

All routes require `Authorization: Bearer <accessToken>`.

- `POST /student-profile` — create profile (`degreeId` must reference a seeded degree when provided)
- `GET /student-profile` — read own profile
- `PUT /student-profile` — update own profile
- `DELETE /student-profile` — delete own profile

Example seeded degree id: `665f2b0f2a3f7b2a1a9a7d01` (Technion `CS-BSC`, catalog year 2025).

## Catalog API (Protected, Read-Only)

Shared academic data — readable by any authenticated user. Not student-owned.

### List Courses

- `GET /courses?institutionId=technion&catalogYear=2025&page=1&limit=50`
- Header: `Authorization: Bearer <accessToken>`

### Get Course

- `GET /courses/:courseId`
- Header: `Authorization: Bearer <accessToken>`

### List Degrees

- `GET /degrees?institutionId=technion&catalogYear=2025`
- Header: `Authorization: Bearer <accessToken>`

### Get Degree

- `GET /degrees/:degreeId`
- Header: `Authorization: Bearer <accessToken>`

### Get Degree Requirements

- `GET /degrees/:degreeId/requirements`
- Header: `Authorization: Bearer <accessToken>`

## Notes

- Only the API service exposes a host port (`3000` by default).
- MongoDB data is persisted in the `mongo_data` named volume.
- Catalog records include `sourceRefs`, `catalogYear`, `catalogVersion`, `status`, and `metadata`.
- Worker and AI services remain internal skeletons for later async AI phases.
- Passwords are stored as bcrypt hashes; plaintext passwords are never stored.
