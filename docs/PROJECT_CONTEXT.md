# UniPilot AI — Project Context (Source of Truth)

Last updated: 2026-06-19
Use it before starting major coding, architecture updates, or roadmap decisions.

If this file and another doc conflict:
1. Follow assignment requirements.
2. Follow accepted ADRs in `docs/decisions/`.
3. Update this file so it stays current.

For Technion catalog ingestion design, see `docs/DATA_INGESTION_ARCHITECTURE.md`.

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

Current stage: **auth + student profile + catalog + completed courses + graduation progress + deterministic semester planner + deterministic academic risk analyzer backend implemented** (Phase 8 academic risk analyzer complete).

Architecture pattern:
- `api` receives client requests and exposes `/health`, auth routes, protected `/student-profile` CRUD, protected `/completed-courses` CRUD, protected `/graduation-progress`, protected `/semester-plans` generate/history routes, protected `/academic-risks` analyze/history routes, and read-only catalog routes (`/courses`, `/degrees`).
- `worker` and `ai` are internal services for async pipeline foundation.
- `redis` is queue/rate-limit infrastructure foundation.
- `mongo` is persistent data store (named volume).
- Internal Docker network for inter-service communication by service name.

Current behavior intentionally excludes AI recommendation, simulation, and RAG logic, but includes authentication, student profile CRUD, completed courses CRUD, deterministic graduation progress, deterministic semester planning, deterministic academic risk analysis, and read-only Technion catalog APIs backed by a curated seed dataset.

## 3.2) Python Backend Migration (Approved Plan)

The team has decided to migrate the **main backend** from **Node.js / Express** to **Python / FastAPI**.

| Policy | Detail |
|---|---|
| Node backend | **Reference implementation** — keep unchanged during migration |
| Python backend | **New target** — built in parallel, feature by feature |
| Behavioral contract | `docs/API_SPEC.md` + current Node behavior and tests |
| Node removal | Only after Python feature parity + explicit team approval |

**Canonical plan:** `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`  
**Real DDS data plan:** `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`

### Why migrate

- Course material and assignments use Python; the team is more comfortable with Python.
- Python is better suited for data engineering, PDF processing, AI, RAG, and academic data ingestion.
- Auth and Student Profile can be ported first (minimal catalog dependency).
- Catalog, requirements, progress, planner, and risk analyzer should wait for **real Technion DDS data** (not placeholder seed).

### Python migration order (summary)

1. FastAPI skeleton + Docker — **implemented (Phase 1)**  
2. Auth  
3. Student Profile (`degreeId` optional until real catalog import)  
4. Data-engineering container  
5. Collect/process real DDS data  
6. Validate against domain/schema  
7. Import validated DDS data into MongoDB  
8. Catalog → Completed Courses → Graduation Progress → Planner → Risk → AI  

### Python Phase 1 status (implemented)

| Item | Status |
|---|---|
| `services/api-python/` FastAPI skeleton | Done |
| `GET /health` with MongoDB + Redis connectivity checks | Done |
| `api-python` Docker Compose service (host-exposed) | Done |
| Separate MongoDB database (`unipilot_python`) | Done |
| pytest health tests | Done |
| Node reference backend | Unchanged |

Phase 1 scope intentionally excludes auth, student profile, data engineering, and AI/RAG.

### Target Python stack

FastAPI, MongoDB, Redis, Python worker, data-engineering container, Pydantic, JWT, bcrypt, pytest, Docker Compose — see migration plan for full architecture.

**Do not** delete or modify the Node backend as part of Python migration tasks. **Do not** mark Node as legacy until the migration definition of done is met.

## 3.1) Technion Academic Data Strategy

UniPilot targets **Technion** as the initial institution (`institutionId: "technion"`). Academic reference data is split into two layers:

| Layer | Source of truth | Purpose |
|---|---|---|
| Structured catalog facts | **MongoDB** (`degrees`, `courses`, `degree_requirements`, `course_offerings`) | API responses, planning, eligibility, graduation progress |
| Document-grounded text | **RAG index** (derived from validated sources) | Policy explanations and narrative answers with citations |

**Rules:**

- MongoDB is the system of record for structured academic data.
- RAG supports explanations and policies; it does not replace catalog facts.
- The LLM must not invent courses, prerequisites, credits, or degree requirements.
- All structured catalog records must include `sourceRefs`, `catalogYear`, and `catalogVersion`.
- Ingestion pipeline design: `docs/DATA_INGESTION_ARCHITECTURE.md`.

**Phase boundary:**

- **Phase 4 (catalog seed):** implemented — curated Technion CS dataset in `data/validated/technion/2025/` + `seedCatalog.js` / `seedCatalogCli.js`.
- **Phase 5 (completed courses):** implemented — user-owned transcript records in `completed_courses` with manual CRUD, catalog `courseId` validation, duplicate attempt handling, `creditsEarned` in 0.5 increments (0–36), and edit/delete restricted to `source=manual`.
- **Phase 6 (graduation progress):** implemented — deterministic `GET /graduation-progress` using student profile, completed courses, degree requirements, and catalog facts (no LLM).
- **Phase 7 (semester planner):** implemented — deterministic `POST /semester-plans/generate` plus planning history (`GET /semester-plans`, `GET /semester-plans/:id`) using profile, completed courses, catalog, degree requirements, and graduation progress (no LLM).
- **Phase 8 (academic risk analyzer):** implemented — deterministic `POST /academic-risks/analyze` plus analysis history (`GET /academic-risks`, `GET /academic-risks/:id`) using profile, completed courses, catalog, degree requirements, graduation progress, and semester plans (no LLM).
- **Later phase:** full offline pipeline (PDF/HTML extraction, normalization, validation, review, RAG generation, automated refresh).

Raw Technion inputs (PDFs, HTML pages, faculty URLs, catalogs, requirement documents, policies) flow through the pipeline defined in the ingestion architecture doc; only validated artifacts are imported into MongoDB.

## 4) Tech Stack

### 4.1 Current (Node reference — implemented)

- Runtime: Node.js 20 (Alpine images)
- API framework: Express
- Database: MongoDB 7
- Queue/cache/rate-limit foundation: Redis 7
- Container orchestration: Docker Compose
- Testing (current): Jest + Supertest
- Language: JavaScript (CommonJS)

### 4.2 Target (Python — Phase 1 in progress)

- Runtime: Python 3.12+ (pinned in Dockerfile)
- API framework: FastAPI
- Database: MongoDB 7 (separate DB name `unipilot_python` during parallel dev)
- Queue/cache: Redis 7
- Validation: Pydantic v2 (settings in Phase 1)
- Testing: pytest + httpx
- **Phase 1 implemented:** `services/api-python/` skeleton, `GET /health`, Docker `api-python` service
- **Not yet implemented:** auth, student profile, data engineering, AI/RAG
- See `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`

## 5) Docker Services

| Service | Role | Host-exposed | Internal Port | Healthcheck | Notes |
|---|---|---|---|---|---|
| `api` | Node reference backend API | Yes (host `API_PORT` -> container `3000`) | 3000 | Yes | Reference implementation |
| `api-python` | FastAPI migration target | Yes (host `API_PYTHON_PORT` -> container `8000`) | 8000 | Yes | Parallel dev; uses `unipilot_python` DB |
| `mongo` | Persistent database | No | 27017 | Yes | Uses `mongo_data` named volume |
| `redis` | Queue/rate-limit foundation | No | 6379 | Yes | Internal-only |
| `worker` | Background worker skeleton | No | 3002 | Yes | Internal-only |
| `ai` | AI service skeleton | No | 3001 | Yes | Internal-only |

Networking and exposure rules:
- `api` and `api-python` may publish host ports during parallel migration.
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
  DATA_INGESTION_ARCHITECTURE.md
data/                          # offline catalog artifacts (see ingestion architecture)
  validated/                   # Phase 4: small curated Technion seed committed here
scripts/data/                  # offline ingestion scripts (Phase 4: seedCatalog.js only)
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
- Catalog unit tests (seed mappers, query validation, public DTO mappers).
- Catalog integration tests (courses/degrees/requirements read APIs).
- Catalog security tests (401 without JWT on all catalog routes).
- Student profile degree reference integration tests.
- Completed courses unit tests (payload validation).
- Completed courses integration tests (create/list/get/update/delete manual records).
- Completed courses security tests (JWT required, cross-user isolation, non-manual edit/delete blocked).
- Graduation progress unit tests (requirement evaluation, fractional credits, failing grades ignored).
- Graduation progress integration tests (profile/degree/completed-course flow, edge cases).
- Graduation progress security tests (JWT required).
- Semester planner unit tests (mandatory priority, prerequisites, failed grades, partial plans).
- Semester plans integration tests (generate/list/get, profile/degree edge cases).
- Semester plans security tests (JWT required, cross-user isolation, userId rejection).
- Academic risk analyzer unit tests (overload, prerequisites, completed/failed courses, mandatory progress).
- Academic risks integration tests (plan/ad-hoc analyze, history, edge cases).
- Academic risks security tests (JWT required, cross-user isolation, userId rejection).

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
- Student profile `degreeId` FK validation against seeded `degrees` collection.
- Curated Technion catalog seed (`data/validated/technion/2025/`) marked as **placeholder data** (`isCuratedPlaceholder`, not official Technion extracts).
- Catalog models (`courses`, `degrees`, `degree_requirements`) with indexes and provenance fields.
- Read-only catalog APIs: `GET /courses`, `GET /courses/:id`, `GET /degrees`, `GET /degrees/:id`, `GET /degrees/:id/requirements` (JWT required).
- Catalog seed CLI (`services/api/src/scripts/seedCatalogCli.js`, `scripts/data/seedCatalog.js`).
- Completed courses model (`completed_courses`) with unique `(userId, courseId, attempt)` index.
- Protected completed courses CRUD (`POST/GET/PUT/DELETE /completed-courses`) with ownership checks.
- Completed course `courseId` FK validation against published `courses` catalog.
- Manual-only edit/delete policy: `PUT` / `DELETE` blocked for `official` and `imported` sources.
- Graduation progress endpoint (`GET /graduation-progress`) with deterministic requirement evaluation.
- Semester plans model (`semester_plans`) with user ownership indexes.
- Deterministic semester planner (`POST /semester-plans/generate`) and planning history (`GET /semester-plans`, `GET /semester-plans/:id`).
- Deterministic academic risk analyzer (`POST /academic-risks/analyze`) and analysis history (`GET /academic-risks`, `GET /academic-risks/:id`).

Still pending for next phases:
- AI endpoint rate limiting.
- Validate `StudentProfile.degreeId` against profile `institutionId` and `catalogYear` once catalog selection UX and multi-catalog support exist (see `docs/planning/FEATURE_BACKLOG.md` → Future TODOs).

## 9) Development Roadmap

Canonical roadmaps:

- **Node (reference, implemented):** `docs/planning/IMPLEMENTATION_PHASES.md`, `docs/planning/FEATURE_BACKLOG.md`
- **Python migration:** `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`
- **Real DDS data:** `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`

### Node reference — completed through Phase 8

Phases 1–8 on the Node stack are implemented (auth through academic risk analyzer) using curated placeholder catalog data.

### Python migration — next work

1. Python Phase 1–3: skeleton, auth, student profile (parallel to Node; no Node changes)
2. Python Phase 4–7: data-engineering container, real DDS collection/validation/import
3. Python Phase 8+: catalog and academic features on **real DDS data**
4. AI / RAG / simulation (both stacks): after catalog facts are grounded in real data

### Still pending (both stacks / later)

- AI endpoint rate limiting (Python: implement with AI phase)
- Full Technion ingestion automation beyond DDS subset
- Simulation features and plan versioning/editing APIs
- Hardening, stress/security testing, documentation, risk/final report
- Node deprecation decision (only after Python parity + team approval)

## 10) What Has Already Been Implemented

- Multi-service Docker Compose stack (`api`, `mongo`, `redis`, `worker`, `ai`).
- Healthchecks and startup ordering for core dependencies.
- MongoDB named volume persistence (`mongo_data`).
- Only API service host exposure (internal-only for other services).
- API `/health` endpoint and auth endpoints (`/auth/register`, `/auth/login`, `/auth/me`).
- Student profile endpoints (`POST/GET/PUT/DELETE /student-profile`) with JWT protection and ownership checks.
- Completed courses endpoints (`POST/GET/PUT/DELETE /completed-courses`) with JWT protection, ownership checks, catalog FK validation, and manual-only mutations.
- Graduation progress endpoint (`GET /graduation-progress`) with JWT protection and deterministic requirement evaluation.
- Semester plans endpoints (`POST /semester-plans/generate`, `GET /semester-plans`, `GET /semester-plans/:id`) with JWT protection, ownership checks, and deterministic rule-based explanations.
- Academic risks model (`academic_risks`) with user ownership indexes and embedded rule-based findings.
- Academic risks endpoints (`POST /academic-risks/analyze`, `GET /academic-risks`, `GET /academic-risks/:id`) with JWT protection, ownership checks, and deterministic analysis (no LLM).
- Catalog read endpoints with JWT protection (shared academic data, not user-owned).
- bcrypt password hashing, JWT token issuance, and protected-route middleware.
- Auth validation and auth rate limiting middleware.
- Student profile validation schemas and MongoDB model/indexes.
- Completed courses validation schemas, MongoDB model/indexes, and test suites.
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
2. For **Python migration** work, read `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`.
3. For **real DDS catalog data**, read `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`.
4. Read `docs/planning/IMPLEMENTATION_PHASES.md` for Node reference phase history.
5. For catalog/ingestion design, read `docs/DATA_INGESTION_ARCHITECTURE.md`.
6. Read relevant rule files in `.cursor/rules/unipilot-*.mdc`.
7. Implement one feature at a time and update docs/tests with each feature.
