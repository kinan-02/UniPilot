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
2. Auth — **implemented (Phase 2)**  
3. Student Profile — **implemented (Phase 3)** (`degreeId` optional; no catalog FK validation yet)  
4. Data-engineering container — **implemented (Phase 4)**  
5. Collect/process real DDS data — **source intake started (Phase 5)**  
6. DDS catalog PDF extraction + manual-curation foundation — **implemented (Phase 6)**  
6.5. DDS catalog markdown parser → draft curated JSON — **implemented (Phase 6.5)**  
7.5. DDS catalog assisted curation (course JSON metadata) — **implemented (Phase 7.5)**  
7.6. DDS catalog curated JSON signoff review — **implemented (Phase 7.6)**  
8. Validate against domain/schema — **in progress (reviewed JSON)**    
8. Import validated DDS data into MongoDB  
9. Catalog → Completed Courses → Graduation Progress → Planner → Risk → AI  

### Python Phase 1 status (implemented)

| Item | Status |
|---|---|
| `services/api-python/` FastAPI skeleton | Done |
| `GET /health` with MongoDB + Redis connectivity checks | Done |
| `api-python` Docker Compose service (host-exposed) | Done |
| Separate MongoDB database (`unipilot_python`) | Done |
| pytest health tests | Done |
| Node reference backend | Unchanged |

Phase 1 scope intentionally excludes student profile, data engineering, and AI/RAG.

### Python Phase 2 status (implemented)

| Item | Status |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Done |
| bcrypt password hashing + JWT access tokens | Done |
| Pydantic strict validation (email normalize, password policy incl. 72-byte bcrypt limit) | Done |
| Redis-backed auth rate limiting (in-memory fallback in `test` env) | Done |
| pytest unit / integration / security auth tests | Done |
| Node reference backend | Unchanged |

Phase 2 scope intentionally excludes student profile, data engineering, and AI/RAG.

### Python Phase 3 status (implemented)

| Item | Status |
|---|---|
| `POST/GET/PUT/DELETE /student-profile` | Done |
| JWT-protected singleton profile per user | Done |
| Server-side `userId` assignment; rejects `userId` / `_id` in body | Done |
| Pydantic strict validation (institution, program, semester, preferences) | Done |
| `degreeId` optional; **no catalog validation** until real DDS import | Done |
| pytest unit / integration / security student profile tests | Done |
| Node reference backend | Unchanged |

Phase 3 scope intentionally excludes catalog, data engineering, and AI/RAG.

### Python Phase 4 status (implemented)

| Item | Status |
|---|---|
| `services/data-engineering/` standalone internal container | Done |
| Staging collections only (`staging_courses`, `staging_degree_requirements`, `staging_ingestion_runs`) | Done |
| CLI: `health`, `validate-sample`, `import-sample` | Done |
| Pydantic models: `NormalizedCourse`, `NormalizedDegreeRequirement`, `IngestionRun` | Done |
| Validators + Technion DDS normalizer/importer stubs | Done |
| Synthetic sample import to staging (not production catalog) | Done |
| pytest foundation tests (config, validation, staging importer) | Done |
| Node reference backend | Unchanged |

Phase 4 scope intentionally excludes real Technion DDS scraping/import, catalog API migration, and promotion from staging to production collections.

### Python Phase 5 status (implemented — source intake & mapping only)

| Item | Status |
|---|---|
| Local raw sources under `services/data-engineering/data/raw/technion/` | Done (local; gitignored) |
| Source inspection: spring/summer course JSON + DDS catalog PDF | Done |
| Mapping doc `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md` | Done |
| Synthetic shape sample `data/samples/technion_course_list_synthetic.json` | Done |
| `.gitignore` rules for large raw JSON/PDF | Done |
| MongoDB / staging import of real data | **Not started** |
| PDF parsing pipeline | **Not started** |
| Node reference backend | Unchanged |

Phase 5 scope intentionally excludes production import, staging import of real data, PDF parsing implementation, catalog API migration, and live website scraping.

### Python Phase 6 status (implemented — PDF extraction & manual-curation foundation)

| Item | Status |
|---|---|
| DDS catalog PDF extraction module (`technion_dds_catalog_pdf.py`) | Done |
| CLI: `extract-dds-catalog`, `inspect-dds-catalog` | Done |
| Local generated artifacts under `data/generated/technion/dds_catalog/` | Done (gitignored) |
| Hebrew/RTL best-effort post-processing | Done |
| Candidate section / program / course-number detection | Done |
| Proposed catalog models (`NormalizedDegreeProgram`, etc.) | Done (stubs only) |
| Manual curation template JSON | Done |
| MongoDB / staging / production writes | **Not started** |
| Node reference backend | Unchanged |

Phase 6 scope intentionally excludes staging import of degree requirements, production promotion, catalog API migration, and fully automated table parsing without manual review.

### Python Phase 6.5 status (implemented — markdown parser → draft curated JSON)

| Item | Status |
|---|---|
| Markdown source `technion_dds_catalog_from_docx_clean.md` | Done (local) |
| Course-number normalization (`09407000` → `00940700`, spaced OCR junk) | Done |
| Hebrew RTL cleanup on table cells | Done |
| Program split + credit buckets + semester matrices + elective pools + DS tracks | Done |
| CLI: `parse-dds-catalog-md` | Done |
| Output: `data/generated/technion/dds_catalog/dds_catalog_curated_draft.json` | Done (gitignored) |
| `CuratedCatalogDocument` Pydantic model | Done |
| MongoDB / staging / production writes | **Not started** |
| Node reference backend | Unchanged |

Phase 6.5 scope intentionally excludes staging import, semester JSON merge (prerequisites/offerings), and production promotion. Draft JSON requires manual review before any import.

### Python Phase 7.5 status (implemented — assisted curation, course JSON metadata)

| Item | Status |
|---|---|
| Course offering JSON index (`courses_2025_200/201/202.json`) | Done |
| CLI: `curate-dds-catalog` | Done |
| Reviewed output `data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json` | Done |
| Review report `dds_catalog_curated_review_report.md` | Done |
| Title/credits/faculty enrichment from exact course number matches | Done |
| IE/IS choose-N chain rule groups (not flattened mandatory lists) | Done |
| DS semester-1 additions from markdown when supported | Done |
| MongoDB / staging / production writes | **Not started** |
| Node / Python API changes | **None** |

Phase 7.5 scope intentionally excludes staging import, production promotion, and treating semester JSON as degree requirements. Reviewed JSON requires human signoff before Phase 8.

### Python Phase 7.6 status (implemented — agent-assisted source signoff review)

| Item | Status |
|---|---|
| CLI: `signoff-dds-catalog` | Done |
| Signoff module `app/curation/dds_catalog_signoff.py` | Done |
| Updated `dds_catalog_curated_reviewed.json` with `signoffReview` metadata | Done |
| Signoff report `dds_catalog_signoff_review_report.md` | Done |
| Phase 8 readiness `dds_catalog_phase8_readiness_check.json` | Done |
| Credit bucket verification against markdown | Done |
| Title hint resolution (JSON + non-reversed markdown only) | Done |
| IE/IS chain rules remain non-mandatory choose-N groups | Done |
| MongoDB / staging / production writes | **Not started** |
| Node / Python API changes | **None** |

Phase 7.6 is **agent-assisted source verification**, not true human approval. The reviewed catalog may be suitable for **Phase 8 staging import with review flags preserved**; production promotion still requires human signoff. No MongoDB writes occur in this phase.

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

### 4.2 Target (Python — Phase 3 complete)

- Runtime: Python 3.12+ (pinned in Dockerfile)
- API framework: FastAPI
- Database: MongoDB 7 (separate DB name `unipilot_python` during parallel dev)
- Queue/cache: Redis 7
- Validation: Pydantic v2
- Auth: JWT + bcrypt (matches Node reference behavior)
- Testing: pytest + httpx + mongomock-motor
- **Phase 1 implemented:** skeleton, `GET /health`, Docker `api-python` service
- **Phase 2 implemented:** auth routes, rate limiting, auth test suites
- **Phase 3 implemented:** student profile CRUD, ownership enforcement, profile test suites
- **Not yet implemented:** catalog, data engineering, AI/RAG
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

1. Python Phase 4: data-engineering container (parallel to Node; no Node changes)
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

- Multi-service Docker Compose stack (`api`, `api-python`, `mongo`, `redis`, `worker`, `ai`).
- Healthchecks and startup ordering for core dependencies.
- MongoDB named volume persistence (`mongo_data`).
- Host exposure for `api` (Node reference) and `api-python` (Python migration) during parallel development; all other services internal-only.
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
