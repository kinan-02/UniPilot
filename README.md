# UniPilot AI — Phase 8 Academic Risk Analyzer Backend

UniPilot AI is an AI-powered academic decision support platform.  
This repository currently implements backend foundation plus **authentication**, **student profile CRUD**, **completed courses CRUD**, **graduation progress**, **deterministic semester planning**, **deterministic academic risk analysis**, and **read-only Technion-style course catalog / degree requirements**:

- Dockerized backend services
- Health endpoint in the API
- Register/login endpoints
- bcrypt password hashing
- JWT access tokens
- Protected auth route middleware
- Input validation and auth rate limiting
- Protected student profile CRUD (`/student-profile`)
- Protected completed courses CRUD (`/completed-courses`)
- Deterministic graduation progress (`GET /graduation-progress`)
- Deterministic semester planner (`POST /semester-plans/generate`) and planning history
- Deterministic academic risk analyzer (`POST /academic-risks/analyze`) and analysis history
- Curated Technion CS/SE catalog seed data (2025)
- Read-only catalog endpoints (`/courses`, `/degrees`)
- Catalog seed command for MongoDB
- Unit, integration, and security tests

Simulation and AI recommendation features are intentionally not implemented yet.

## Services

- `api` (Node.js/Express) — **reference backend** (exposed on `API_PORT`)
- `api-python` (FastAPI) — **Python migration target** (exposed on `API_PYTHON_PORT` for development)
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

- Node (reference): `http://localhost:<API_PORT>/health`
- Python (migration): `http://localhost:<API_PYTHON_PORT>/health`

Example with defaults from `.env.example`:

- [http://localhost:3000/health](http://localhost:3000/health) (Node)
- [http://localhost:8000/health](http://localhost:8000/health) (Python)

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

Seed data lives in `data/validated/technion/2025/` (1 degree, 16 courses, 4 requirements).

**Important:** This is **curated placeholder data** for development and demos (`metadata.isCuratedPlaceholder: true`). It is not scraped from official Technion sources.

## Stop and Clean

```bash
docker compose down -v
```

## Run Tests

API tests (health + auth + student profile + completed courses + graduation progress + semester plans + academic risks + catalog unit/integration/security):

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

### Python API (`api-python`)

Python backend tests (Phase 1 — health endpoint):

```bash
cd services/api-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Note: the Python service uses a separate MongoDB database name (`MONGO_PYTHON_DB`, default `unipilot_python`) so it does not interfere with the Node reference backend during parallel development.

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

## Completed Courses API (Protected)

User-owned transcript records. All routes require `Authorization: Bearer <accessToken>`.

- `POST /completed-courses` — add a manual completed course (validates `courseId` against seeded catalog)
- `GET /completed-courses` — list own records (`?page=1&limit=50`)
- `GET /completed-courses/:id` — get one owned record
- `PUT /completed-courses/:id` — update **manual** records only
- `DELETE /completed-courses/:id` — delete **manual** records only

Example create body:

```json
{
  "courseId": "665f2b0f2a3f7b2a1a9a7c01",
  "semesterCode": "2024-1",
  "grade": "B+",
  "gradePoints": 82,
  "creditsEarned": 3.5,
  "attempt": 1
}
```

Duplicate `(courseId, attempt)` for the same user returns `409`. `creditsEarned` accepts half-credit values in 0.5 increments (for example `3.5`).

`official` and `imported` records are **not** creatable via the public API (only `manual` on `POST`). Future transcript ingestion will insert those via internal trusted import logic. They cannot be edited or deleted via API (`403`).

## Graduation Progress API (Protected)

Deterministic degree progress for the authenticated user. Requires a student profile with a selected `degreeId`.

- `GET /graduation-progress` — compute credits, mandatory course progress, elective progress, requirement breakdown, and status summary

**Prerequisites:** register → create `/student-profile` with `degreeId` → optionally add `/completed-courses` → call `/graduation-progress`.

**Errors:** `404` if profile missing; `400` if `degreeId` not selected.

Progress uses MongoDB catalog facts and degree requirements only (no LLM).

## Semester Plans API (Protected)

Deterministic next-semester recommendations for the authenticated user. Requires a student profile with a selected `degreeId`.

- `POST /semester-plans/generate` — generate and persist a rule-based plan
- `GET /semester-plans` — list own planning history (`?page=1&limit=50`)
- `GET /semester-plans/:id` — get one owned plan

Example generate body:

```json
{
  "semesterCode": "2025-2",
  "maxCredits": 12,
  "minCredits": 9
}
```

**Planner behavior (deterministic, no AI):**
- Excludes completed passing courses; failed grades do not count as completed
- Prioritizes remaining mandatory courses before electives
- Respects prerequisites from the catalog
- Schedules prerequisite chains within the same semester in dependency order
- Uses profile `preferences.maxCreditsPerSemester` when `maxCredits` is omitted (default `18`)
- Returns structured `explanation` with `blockedByPrerequisites`, `missingPrerequisites`, and partial/empty plan reasons when limits apply

**Prerequisites:** register → create `/student-profile` with `degreeId` → optionally add `/completed-courses` → call `/semester-plans/generate`.

**Errors:** `404` if profile missing; `400` if `degreeId` not selected; `404` if another user's plan id is requested.

## Academic Risks API (Protected)

Deterministic academic risk analysis for a persisted semester plan or ad-hoc proposed courses. Requires a student profile with a selected `degreeId`.

- `POST /academic-risks/analyze` — analyze and persist rule-based risks
- `GET /academic-risks` — list own analysis history (`?page=1&limit=50`)
- `GET /academic-risks/:id` — get one owned analysis

Example analyze persisted plan:

```json
{
  "planId": "665f2b0f2a3f7b2a1a9a7fff"
}
```

Example ad-hoc analyze:

```json
{
  "semesterCode": "2025-2",
  "courseIds": ["665f2b0f2a3f7b2a1a9a7c01", "665f2b0f2a3f7b2a1a9a7c07"],
  "maxCredits": 12
}
```

**Analyzer behavior (deterministic, no AI):**
- Uses profile, completed courses, catalog, degree requirements, graduation progress, and plan data only
- Detects overload, too few credits, unmet prerequisites, completed courses in plan, failed retakes, mandatory-progress gaps, partial/empty plans, deferred planner warnings, and related rule-based risks
- Returns `summary.totalRisks`, `summary.highestSeverity`, and structured per-risk `evidence` / `suggestedFixes` with `source: "rule"`

**Prerequisites:** register → create `/student-profile` with `degreeId` → generate or propose courses → call `/academic-risks/analyze`.

**Errors:** `404` if profile/plan/analysis missing; `400` if `degreeId` not selected; cross-user access returns `404`.

## Notes

- Only the API service exposes a host port (`3000` by default).
- MongoDB data is persisted in the `mongo_data` named volume.
- Catalog records include `sourceRefs`, `catalogYear`, `catalogVersion`, `status`, and `metadata`.
- Worker and AI services remain internal skeletons for later async AI phases.
- Passwords are stored as bcrypt hashes; plaintext passwords are never stored.
