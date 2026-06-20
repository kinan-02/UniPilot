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
- `data-engineering` (Python CLI) — **internal staging ingestion foundation** (no host port)
- `worker` (Node.js/Express health stub) — internal only
- `ai` (Node.js/Express health/infer stub) — internal only
- `mongo` (MongoDB) — internal only, persisted via volume
- `redis` (Redis) — internal only, queue/rate-limit foundation

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for Node API tests and host-side seed command)
- Python 3.12+ (for local `api-python` pytest only; Docker does not require a host Python install)

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

Python backend tests (Phase 1 health + Phase 2 auth + Phase 3 student profile + Phase 13 catalog + Phase 14 completed courses + Phase 15 graduation progress — unit, integration, security):

```bash
cd services/api-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Run focused suites:

```bash
cd services/api-python
source .venv/bin/activate
pytest tests/unit
pytest tests/integration
pytest tests/security
```

Note: the Python service uses a separate MongoDB database name (`MONGO_PYTHON_DB`, default `unipilot_python`) so it does not interfere with the Node reference backend during parallel development.

### Data Engineering (`data-engineering`)

Internal-only Python service for **staging** academic data ingestion. It shares the same MongoDB instance as `api-python` (`MONGO_PYTHON_DB`) but writes only to staging collections — not production `courses` / `degree_requirements`.

**Phase 4 foundation only:** real Technion Faculty of Data and Decision Sciences (DDS) import is not implemented yet. Use synthetic sample commands for pipeline testing.

**Phase 5 (source intake):** local Technion files live under `services/data-engineering/data/raw/technion/` (gitignored). Field mapping and gaps are documented in `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`. No real data is written to MongoDB in this phase.

**Phase 6 (PDF extraction):** extract and inspect the DDS catalog PDF locally. Generated artifacts go to `services/data-engineering/data/generated/technion/dds_catalog/` (gitignored). Hebrew RTL and tables remain imperfect — manual curation is required before any staging import.

```bash
cd services/data-engineering
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

CLI commands (local or via Docker):

```bash
# Local (requires reachable MongoDB)
python -m app.main health
python -m app.main validate-sample
python -m app.main import-sample

# Docker one-off jobs (recommended)
docker compose run --rm data-engineering python -m app.main health
docker compose run --rm data-engineering python -m app.main validate-sample
docker compose run --rm data-engineering python -m app.main import-sample
```

Staging collections: `staging_courses`, `staging_degree_requirements`, `staging_degree_programs`, `staging_catalog_rules`, `staging_ingestion_runs`.

DDS catalog staging import (Phase 8 — staging only, preserves review flags):

```bash
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json \
  --dry-run
```

Production collections (`degrees`, `degree_requirements`, `courses`, `catalog`) are **not** written. The main API does not expose staging catalog data yet.

Technion course JSON staging import (Phase 9 — offering snapshots, staging only):

```bash
docker compose run --rm data-engineering python -m app.main import-technion-courses-staging \
  --course-json data/raw/technion/courses_2025_200.json \
  --course-json data/raw/technion/courses_2025_201.json \
  --course-json data/raw/technion/courses_2025_202.json \
  --dry-run
```

Semester codes: `200` winter, `201` spring, `202` summer. Staging: `staging_courses`, `staging_course_offerings`. Course JSON is **not** used for degree requirement inference.

Staging quality review (Phase 10 — validates staged data, no writes):

```bash
docker compose run --rm data-engineering python -m app.main validate-dds-staging-quality \
  --output-json data/reports/technion/dds_staging_quality_report.json \
  --output-md data/reports/technion/dds_staging_quality_report.md
```

Reports classify staging vs production vs API-migration blockers. Staged records are not modified automatically.

Phase 10.5 blocker cleanup (curated JSON fixes, then re-import + revalidate):

```bash
docker compose run --rm data-engineering python -m app.main cleanup-dds-staging-blockers
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json
```

Phase 11 promotion gate (dry-run plan only — **no production writes**):

```bash
docker compose run --rm data-engineering python -m app.main plan-dds-production-promotion \
  --output-json data/reports/technion/dds_promotion_plan.json \
  --output-md data/reports/technion/dds_promotion_plan.md \
  --allow-warnings
```

Phase 12 guarded production promotion:

```bash
# Refuses without dangerous flag (exit 2)
docker compose run --rm data-engineering python -m app.main promote-dds-to-production
docker compose run --rm data-engineering python -m app.main promote-dds-to-production --dry-run
docker compose run --rm data-engineering python -m app.main promote-dds-to-production \
  --i-confirm-dangerous-production-write
```

See `services/data-engineering/README.md` for service-specific details.

Raw Technion source layout:

```text
services/data-engineering/data/
  raw/technion/          # real JSON + PDF (local only, gitignored)
  samples/               # small synthetic shape references (committed)
```

Mapping document: `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`

DDS catalog PDF extraction (Phase 6 — local artifacts only):

```bash
cd services/data-engineering
python -m app.main inspect-dds-catalog --pdf-path data/raw/technion/09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf
python -m app.main extract-dds-catalog --pdf-path data/raw/technion/09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf
```

Outputs: `data/generated/technion/dds_catalog/` (`extracted_pages.json`, `extraction_report.json`, `candidate_sections.json`, etc.). No MongoDB writes.

### Python Auth API (`api-python` on `API_PYTHON_PORT`)

The Python backend implements the same auth contract as the Node reference API:

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me` (requires `Authorization: Bearer <accessToken>`)

Example against default Python port:

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"python-user@example.com","password":"StrongPass123!"}'
```

### Python Student Profile API (`api-python` on `API_PYTHON_PORT`)

Self-scoped singleton CRUD — same contract as the Node reference API. All routes require JWT. `userId` is server-assigned; clients must not send `userId` or `_id`. `degreeId` is optional and is **not** validated against the catalog until real DDS data is imported.

- `POST /student-profile` — create profile (`409` if one already exists)
- `GET /student-profile` — read own profile (`404` before creation)
- `PUT /student-profile` — update own profile
- `DELETE /student-profile` — delete own profile

Example flow:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"profile-user@example.com","password":"StrongPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['accessToken'])")

curl -s -X POST http://localhost:8000/student-profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"institutionId":"technion","programType":"BSc","catalogYear":2025,"currentSemesterCode":"2025-1"}'
```

### Python Catalog API (`api-python` on `API_PYTHON_PORT`, Phase 13)

Read-only DDS catalog from **production** MongoDB collections (Phase 12 promotion). JWT required. Hard requirements and advisory rules are **separate endpoints** — advisory `catalog_rules` are never returned as hard graduation requirements.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"catalog-user@example.com","password":"StrongPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['accessToken'])")

curl -s "http://localhost:8000/catalog/courses?limit=5" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8000/catalog/courses/00940345" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8000/catalog/degree-programs" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8000/catalog/degree-programs/009216-1-000/requirements" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8000/catalog/degree-programs/009216-1-000/advisory-rules" -H "Authorization: Bearer $TOKEN"
```

### Python Completed Courses API (`api-python` on `API_PYTHON_PORT`, Phase 14)

User-owned transcript records. JWT required. `courseId` must be a MongoDB ObjectId of a published course in the **production** `courses` collection (use catalog list/detail to discover ids). Does not calculate graduation progress.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"completed-user@example.com","password":"StrongPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['accessToken'])")

COURSE_ID=$(docker compose exec -T mongo mongosh -u unipilot -p unipilot_dev_password --authenticationDatabase admin unipilot_python --quiet --eval \
  'const c=db.courses.findOne({courseNumber:"00104000",status:"published"}); if(c) print(c._id.toString())')

curl -s -X POST http://localhost:8000/completed-courses \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"courseId\":\"$COURSE_ID\",\"semesterCode\":\"2024-1\",\"grade\":\"A\",\"creditsEarned\":2}"

curl -s http://localhost:8000/completed-courses -H "Authorization: Bearer $TOKEN"
```

## Auth API (Node reference on `API_PORT`)

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
  "grade": 82,
  "creditsEarned": 3.5,
  "attempt": 1
}
```

`grade` is a **numeric score 0–100** (Technion scale). Pass is strictly **above 55**; 55 and below do not count toward graduation progress.

Duplicate `(courseId, attempt)` for the same user returns `409`. `creditsEarned` accepts half-credit values in 0.5 increments (for example `3.5`).

`official` and `imported` records are **not** creatable via the public API (only `manual` on `POST`). Future transcript ingestion will insert those via internal trusted import logic. They cannot be edited or deleted via API (`403`).

## Graduation Progress API (Protected — Python Phase 15)

Deterministic degree progress for the authenticated user. Requires a student profile with a valid `degreeId` (MongoDB `_id` of a published `degree_programs` document).

- `GET /graduation-progress` — compute credits, requirement breakdown, pool-enforced electives, and status summary

**Prerequisites:** register → create `/student-profile` with `degreeId` from `GET /catalog/degree-programs` → optionally add `/completed-courses` → call `/graduation-progress`.

**Errors:** `404` if profile missing; `400` if `degreeId` not selected or not found in catalog.

Progress uses production `degree_requirements` (`credit_bucket`), linked `course_pool` rules from `catalog_rules` (Phase 15.1 `linkedCreditBucketId` on promoted pools), and completed courses with numeric grades (pass > 55). `semester_matrix` rules are not enforced.

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
