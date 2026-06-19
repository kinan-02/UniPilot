# Python Backend Migration Plan

Last updated: 2026-06-19  
Status: Approved planning document (no application code in this phase)  
Related docs: `docs/PROJECT_CONTEXT.md`, `docs/API_SPEC.md`, `docs/DATABASE_SCHEMA.md`, `docs/DOMAIN_MODEL.md`, `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`, `docs/DATA_INGESTION_ARCHITECTURE.md`

## 1) Decision Summary

UniPilot will migrate the **main backend** from **Node.js / Express** to **Python / FastAPI**.

| Item | Policy |
|---|---|
| Existing Node backend | **Kept unchanged** as the reference implementation during migration |
| Python backend | **New target implementation**, built in parallel |
| Behavioral contract | `docs/API_SPEC.md` + current Node behavior |
| Node removal | **Not allowed** until Python reaches feature parity and the team explicitly approves |
| This document | Planning only — **no application code** is part of this task |

## 2) Why We Are Doing This

### 2.1 Team and course alignment

- The course material and assignments use **Python**.
- The team is **more comfortable with Python** for backend, data, and ML work.
- Staying in Python reduces context switching between coursework, data pipelines, and product backend work.

### 2.2 Technical fit

Python is better suited for:

- **Data engineering** — ETL, validation pipelines, batch imports
- **PDF / HTML processing** — Technion catalog and policy document extraction
- **AI and RAG** — embeddings, retrieval, orchestration, evaluation
- **Academic data ingestion** — normalization, review workflows, provenance tracking

The Node backend proved the domain model, API contract, security baseline, and Docker patterns. Python should inherit that design, not reinvent it.

### 2.3 Sequencing rationale

| Migrate early | Wait for real DDS data |
|---|---|
| Auth | Course Catalog |
| Student Profile | Degree Requirements |
| FastAPI skeleton + Docker | Completed Courses |
| Data-engineering container setup | Graduation Progress |
| | Semester Planner |
| | Academic Risk Analyzer |
| | AI services |

**Auth** and **Student Profile** do not depend heavily on the academic catalog. They can be ported first while the team builds the real-data pipeline.

**Course Catalog**, **Degree Requirements**, **Graduation Progress**, **Semester Planner**, and **Academic Risk Analyzer** should wait until **real Technion Faculty of Data and Decision Sciences (DDS)** data is collected, validated, and imported. Implementing these features against placeholder seed data in Python would create rework.

**`StudentProfile.degreeId`** should remain **optional** in Python until the real catalog is imported. Do not require degree FK validation before DDS data exists.

After real DDS data is validated, update `docs/DATABASE_SCHEMA.md` and `docs/DOMAIN_MODEL.md` if needed **before** implementing catalog-dependent Python features.

## 3) Migration Safety Rules

1. **Keep Node as reference** — when behavior is ambiguous, read Node tests and handlers first.
2. **Build Python in parallel** — do not delete, rename, or mark Node services as legacy prematurely.
3. **Port one feature at a time** — each Python phase ends with tests + doc updates + team commits.
4. **Use API_SPEC as contract** — request/response envelopes, status codes, validation rules, and ownership policy must match.
5. **Every migrated feature requires tests** — unit, integration, and security tests at minimum; E2E where applicable.
6. **Run both test suites during transition** — when a feature is ported, compare Node and Python behavior for that feature until parity is declared.
7. **Preserve Docker first-run reliability** — `docker compose up --build` must work from a clean clone with documented `.env.example`.
8. **Update README and PROJECT_CONTEXT after every Python phase** — graders and teammates must always know how to run the active stack.
9. **Do not remove Node** until Python passes all required tests, matches API_SPEC, and the team approves cutover.

## 4) Target Python Architecture

### 4.1 Services (Docker Compose)

| Service | Role | Host-exposed | Notes |
|---|---|---|---|
| `api-py` (or `api` after cutover) | FastAPI client-facing API | Yes (only public backend port) | JWT, validation, orchestration |
| `mongo` | Persistence | No | Shared or parallel volume policy per phase |
| `redis` | Queue + rate limiting | No | Shared infrastructure |
| `worker-py` | Background jobs | No | Async AI, ingestion jobs later |
| `data-engineering` | Offline/batch academic data processing | No | PDF/HTML extract, normalize, validate |
| `ai-py` | Internal inference / RAG gateway | No | Internal-only |

During parallel development, Node services (`api`, `worker`, `ai`) may coexist in Compose with distinct service names and ports. Only **one** API service should publish the host port at a time unless documented otherwise for side-by-side testing.

### 4.2 Python stack

| Concern | Choice |
|---|---|
| API framework | FastAPI |
| Validation | Pydantic v2 schemas (strict, reject unknown fields on writes) |
| Database | MongoDB (Motor or PyMongo — decide in Phase 1 ADR) |
| Auth | JWT (access tokens), bcrypt password hashing |
| Rate limiting | Redis-backed (auth + AI endpoints) |
| Testing | pytest + httpx (AsyncClient) |
| Coverage | ≥ 80% overall |
| Response envelope | `{ success, data, error }` per `docs/API_SPEC.md` |

### 4.3 Proposed repository layout (future implementation)

```text
services/
  api/                    # Node reference (unchanged)
  api-py/                 # FastAPI target
    app/
      main.py
      routers/
      models/
      schemas/
      services/
      security/
      db/
    tests/
      unit/
      integration/
      security/
    Dockerfile
    pyproject.toml
  worker-py/
  data-engineering/
    pipelines/
    extractors/
    validators/
    cli/
  ai-py/
docker-compose.yml        # extended, not replacing Node services until cutover
docker-compose.python.yml # optional overlay for Python-only dev (future)
```

Exact naming is decided in Python Phase 1; this layout is the planning target.

## 5) Migration Phases (Ordered)

### Python Phase 1 — FastAPI Skeleton + Docker

**Goal:** Python API boots first try alongside existing infrastructure.

**Deliverables:**

- `services/api-py` with FastAPI app, `/health` endpoint, standard response envelope
- Dockerfile (multi-stage, non-root user, pinned base image)
- Docker Compose integration with `mongo`, `redis` healthchecks and `depends_on`
- `.env.example` entries for Python service ports and secrets
- pytest smoke test for `/health`
- README section: how to run Python API (parallel to Node)

**Exit criteria:**

- `docker compose up --build` starts Python API + dependencies from clean clone
- `/health` returns configured dependency status
- Only Python API (or documented test port) exposed to host
- PROJECT_CONTEXT updated with dual-backend note

**Node reference:** `services/api/src/app.js`, `docker-compose.yml`

---

### Python Phase 2 — Auth

**Goal:** Register, login, JWT, bcrypt, rate limiting — behavior matches Node.

**Deliverables:**

- User model + indexes (unique email)
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- Pydantic request/response schemas (strict)
- JWT middleware for protected routes
- bcrypt password hashing (cost ≥ 10)
- Redis-backed auth rate limiting → `429`
- Unit tests (password, JWT utilities, schema validation)
- Integration tests (register/login against MongoDB)
- Security tests (401, rate limit, no plaintext passwords in responses)

**Exit criteria:**

- Python auth tests pass
- Behavior matches `docs/API_SPEC.md` auth section and Node auth tests
- README auth section covers Python commands
- Run Node + Python auth test suites during PR review

**Node reference:** `services/api/src/routes/authRoutes.js`, `services/api/test/integration/auth.integration.test.js`

---

### Python Phase 3 — Student Profile

**Goal:** Protected student profile CRUD with ownership; `degreeId` optional.

**Deliverables:**

- Student profile model + unique `userId` index
- `POST/GET/PUT/DELETE /student-profile`
- JWT required on all routes; `userId` from token only (clients cannot set `userId`)
- Pydantic validation (semester code format, preferences shape)
- **`degreeId` optional** — validate against catalog only when provided and catalog exists
- Unit + integration + security tests (cross-user isolation, 404/401/400)
- README student profile section for Python

**Exit criteria:**

- Profile CRUD works without `degreeId`
- When `degreeId` is provided before real catalog import, behavior is documented (reject or defer validation per REAL_DATA_ALIGNMENT_PLAN)
- Matches API_SPEC student profile contract
- Node reference tests used as parity checklist

**Node reference:** `services/api/src/routes/studentProfileRoutes.js`, `services/api/src/models/studentProfileModel.js`

**Explicit deferral:** Do not block Python Phase 3 on catalog seed or DDS import.

---

### Python Phase 4 — Data-Engineering Container

**Goal:** Build the Python container that will process real Technion DDS academic data.

**Deliverables:**

- `services/data-engineering` Docker image
- CLI entrypoints for: collect manifest, extract, normalize, validate (subset)
- Folder layout aligned with `docs/DATA_INGESTION_ARCHITECTURE.md`
- Internal-only network exposure
- Healthcheck or `--version` / smoke command
- pytest for pure validation/normalization functions
- README: how to run data-engineering container locally

**Exit criteria:**

- Container builds and runs in Compose
- Can process a **small DDS subset** end-to-end: raw → extracted → normalized → validated JSON on disk
- No MongoDB import required yet in this phase
- See `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md` for DDS scope

**Node reference:** `scripts/data/seedCatalog.js` (import behavior only — do not port to Node)

---

### Python Phase 5 — Collect and Process Real DDS Data

**Goal:** Acquire and process real Technion Faculty of Data and Decision Sciences source materials.

**Deliverables:**

- Source manifest for DDS (`data/raw/technion/dds/<catalogYear>/manifest.json`)
- Collected PDFs/HTML/URLs (committed or documented fetch procedure per licensing)
- Extraction outputs under `data/extracted/technion/dds/<catalogYear>/`
- Normalized JSON under `data/normalized/technion/dds/<catalogYear>/`
- Provenance metadata (`sourceRefs`, `catalogYear`, `catalogVersion`)
- Data-engineering runbook in README or `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`

**Exit criteria:**

- At least one real DDS degree/track subset processed (courses + requirements minimum)
- Manual review checklist completed for extracted fields
- No LLM-invented catalog facts

---

### Python Phase 6 — Validate Real Data Against Domain Model

**Goal:** Confirm real DDS data fits UniPilot domain and database schema.

**Deliverables:**

- Validation report: `docs/reports/DDS_DATA_VALIDATION_REPORT.md` (or equivalent)
- Field-level mapping: source → `Course`, `Degree`, `DegreeRequirement`
- Gap analysis vs `docs/DOMAIN_MODEL.md` and `docs/DATABASE_SCHEMA.md`
- List of schema changes required (if any)
- Decision record if domain model must evolve

**Exit criteria:**

- Team sign-off on validated subset
- Open schema questions resolved or documented as ADRs
- **No catalog API implementation** until this phase completes

See `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`.

---

### Python Phase 7 — Populate Database from Validated DDS Data

**Goal:** Import validated real DDS data into MongoDB.

**Deliverables:**

- Import CLI (`data-engineering` or `api-py` admin script) for validated JSON → MongoDB
- Idempotent seed/import (safe re-run)
- Indexes created per `docs/DATABASE_SCHEMA.md`
- Import integration test against test MongoDB
- `.env.example` documents import command

**Exit criteria:**

- MongoDB contains real DDS catalog subset (not placeholder seed)
- `degrees`, `courses`, `degree_requirements` queryable
- Import is repeatable in Docker
- README documents first-run: Compose up → import DDS catalog

**After this phase:** `StudentProfile.degreeId` FK validation against real degrees may be enabled in Python.

---

### Python Phase 8+ — Academic Features on Real Data (Python)

Implement remaining backend features **in order**, each as its own sub-phase with full tests:

| Sub-phase | Feature | Node reference |
|---|---|---|
| 8a | Course Catalog (read APIs) | `services/api/src/routes/catalogRoutes.js` |
| 8b | Degree Requirements (read APIs) | catalog + requirements routes |
| 8c | Completed Courses | `completedCourseRoutes.js` |
| 8d | Graduation Progress | `graduationProgressCalculator.js` |
| 8e | Semester Planner | `semesterPlanner.js` |
| 8f | Academic Risk Analyzer | `academicRiskAnalyzer.js` |
| 8g | AI services (async pipeline) | worker + ai services |

**Per sub-phase requirements:**

- Port deterministic logic first; no LLM in planner/risk/progress
- TDD: pytest unit → integration → security
- Compare against Node test scenarios where they exist
- Update `docs/API_SPEC.md` only if real data forces contract clarification
- Update README after each sub-phase

## 6) Testing Strategy During Migration

| Test type | Python requirement |
|---|---|
| Unit | Pure functions (auth, progress, planner, risk, validators) |
| Integration | API + MongoDB (+ Redis for rate limit / queue) |
| Security | 401/403/404/400/429, ownership, no secret leakage |
| E2E | Register → profile → catalog → plan → analyze (when features exist) |
| Stress | Auth + AI endpoints (when implemented) |
| Parity | Cross-check selected scenarios against Node tests |

**CI recommendation (future):** run `npm test` (Node) and `pytest` (Python) on every PR touching either stack.

## 7) Documentation Updates Per Phase

After **every** Python phase, update at minimum:

- `README.md` — run, test, import commands
- `docs/PROJECT_CONTEXT.md` — current Python phase status
- `docs/API_SPEC.md` — only when contract changes are approved
- `docs/DATABASE_SCHEMA.md` — after Phase 6/7 if schema evolves

## 8) Definition of Done (Full Python Migration)

The Python backend migration is complete when **all** of the following are true:

- [ ] Python backend passes all required tests (unit, integration, security, E2E, stress where applicable)
- [ ] Coverage ≥ 80%
- [ ] `docker compose up --build` works first try from clean clone
- [ ] API behavior matches `docs/API_SPEC.md`
- [ ] README explains Python backend setup, test commands, and DDS import
- [ ] Data-engineering container processes a real DDS subset before catalog APIs ship
- [ ] Feature parity with Node reference for all in-scope assignment features
- [ ] Team explicitly approves Node deprecation / removal (separate decision; not automatic)

## 9) What Not To Do

- Do not delete or modify Node backend code as part of Python migration work items
- Do not implement catalog-dependent features in Python before Phase 7
- Do not require `degreeId` on student profile until real catalog is imported
- Do not invent academic rules or catalog facts in Python or in LLM prompts
- Do not mark Node as legacy in README until §8 is complete and approved

## 10) Immediate Next Steps

1. Team review and approve this plan
2. Add ADR: `docs/decisions/0002-python-backend-migration.md` (optional, recommended)
3. Begin **Python Phase 1** implementation (separate task)
4. Execute **REAL_DATA_ALIGNMENT_PLAN** in parallel with Python Phases 1–3
