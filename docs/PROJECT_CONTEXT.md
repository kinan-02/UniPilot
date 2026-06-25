# UniPilot AI — Project Context (Source of Truth)

Last updated: 2026-06-23
Use it before starting major coding, architecture updates, or roadmap decisions.

If this file and another doc conflict:
1. Follow assignment requirements.
2. Follow accepted ADRs in `docs/decisions/`.
3. Update this file so it stays current.

For Technion catalog ingestion design, see `docs/DATA_INGESTION_ARCHITECTURE.md` and `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`.

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

Current stage: **auth (incl. Google OAuth + remember-me) + student profile + catalog + completed courses + graduation progress + deterministic semester planner + deterministic academic risk analyzer + transcript UI** implemented.

Architecture pattern:
- `api` receives client requests and exposes `/health`, auth routes (register, login, refresh, logout, Google OAuth, remember-me cookies), protected `/student-profile` CRUD, protected `/completed-courses` CRUD, protected `/graduation-progress`, protected `/semester-plans` generate/history routes, protected `/academic-risks` analyze/history routes, and read-only catalog routes (`/catalog/*`).
- `worker` and `ai` are internal services for async pipeline foundation.
- `redis` is queue/rate-limit infrastructure foundation.
- `mongo` is persistent data store (named volume).
- Internal Docker network for inter-service communication by service name.

Current behavior intentionally excludes AI recommendation, simulation, and RAG logic, but includes authentication, student profile CRUD, completed courses CRUD, deterministic graduation progress, deterministic semester planning, deterministic academic risk analysis, and read-only Technion catalog APIs backed by a curated seed dataset.

Last updated: 2026-06-20

## 3.2) Backend Migration — Complete

The **Node.js / Express** reference backend has been **removed**. **`services/api/`** (Python / FastAPI) is the sole production API.

| Policy | Detail |
|---|---|
| Production API | `services/api/` — FastAPI on port 8000 inside Docker |
| MongoDB database | `unipilot_python` (promoted Technion DDS catalog) |
| Behavioral contract | `docs/API_SPEC.md` + pytest + `scripts/verify_and_benchmark.py` |
| Historical plan | `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md` (archived reference) |

**Do not** reintroduce a second API container or expose internal services to the host.

### Python Phase 2 status (implemented)

| Item | Status |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Done |
| `POST /auth/refresh`, `POST /auth/logout` (HttpOnly cookies) | Done |
| Google OAuth (`GET /auth/google`, `GET /auth/google/callback`) | Done (optional via `GOOGLE_OAUTH_*` env) |
| Remember-me refresh token TTL (`rememberMe` on login/register) | Done |
| bcrypt password hashing + JWT access tokens | Done |
| Pydantic strict validation (email normalize, password policy incl. 72-byte bcrypt limit) | Done |
| Redis-backed auth rate limiting (in-memory fallback in `test` env) | Done |
| pytest unit / integration / security auth tests | Done |
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
Phase 3 scope intentionally excludes catalog, data engineering, and AI/RAG.

### Python Phase 4 status (implemented)

| Item | Status |
|---|---|
| `services/data-engineering/` standalone internal container | Done |
| Staging collections only (`staging_courses`, `staging_degree_requirements`, `staging_degree_programs`, `staging_catalog_rules`, `staging_ingestion_runs`) | Done |
| CLI: `health`, `validate-sample`, `import-sample` | Done |
| Pydantic models: `NormalizedCourse`, `NormalizedDegreeRequirement`, `IngestionRun` | Done |
| Validators + Technion DDS normalizer/importer stubs | Done |
| Synthetic sample import to staging (not production catalog) | Done |
| pytest foundation tests (config, validation, staging importer) | Done |
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
Phase 5 scope intentionally excludes production import, staging import of real data, and live website scraping.

### Data source pivot (2026-06-21)

| Source | Path | Role |
|--------|------|------|
| Semester JSON | `data/raw/technion/courses_2025_{200,201,202}.json` | Semester planner — offerings only |
| Catalog wiki vault | `data/catalog_valut/` (auto-resolves nested `catalog_valut/wiki/`) | Programs, requirements, courses, regulations (full Technion wiki; DDS exported first) |

**Retired:** PDF extraction, docx markdown export, and markdown parser pipeline (`parse-dds-catalog-md`, `curate-dds-catalog`, `signoff-dds-catalog`). Raw catalog PDFs remain under `catalog_valut/raw/` for provenance.

**Next:** `export-vault-catalog --faculty dds` (implemented) → staging import + production promotion. Additional faculties register in `vault_export_registry.py`. See `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`.

### Python Phase 6–7.6 status (retired — superseded by catalog vault)

Phases 6–7.6 (PDF extraction, markdown parser, assisted curation, agent signoff) were implemented and then **removed** when the catalog wiki vault became the authoritative catalog source. Historical phase notes below are kept for traceability only.

### Python Phase 6 status (retired)

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
| MongoDB / staging / production writes | **Not started** (signoff only) |
| Node / Python API changes | **None** |

Phase 7.6 is **agent-assisted source verification**, not true human approval. The reviewed catalog may be suitable for **Phase 8 staging import with review flags preserved**; production promotion still requires human signoff. No MongoDB writes occur in this phase.

### Python Phase 8 status (implemented — DDS catalog staging import only)

| Item | Status |
|---|---|
| CLI: `import-dds-catalog-staging` (`--dry-run` supported) | Done |
| Importer `app/importers/dds_catalog_staging_importer.py` | Done |
| Staging collections: `staging_degree_programs`, `staging_degree_requirements`, `staging_catalog_rules`, `staging_ingestion_runs` | Done |
| Idempotent upsert by stable `stagingKey` | Done |
| Preserves `manualReviewRequired`, `signoffReview`, warnings, `productionEligible: false` | Done |
| Production collections (`degrees`, `degree_requirements`, `courses`, `catalog`, …) | **Not written** |
| Production promotion | **Blocked** |
| Node / Python API changes | **None** |
| Main API catalog exposure | **None** |

Phase 8 imports the Phase 7.6 reviewed curated catalog into **staging only**. `canPromoteToProduction` must remain `false`; all staging documents set `productionEligible: false` and `requiresHumanSignoff: true`.

### Python Phase 9 status (implemented — Technion course JSON staging import)

| Item | Status |
|---|---|
| CLI: `import-technion-courses-staging` (`--dry-run`, `--dds-only`) | Done |
| Source reader `app/sources/technion_course_json.py` | Done |
| Importer `app/importers/technion_course_staging_importer.py` | Done |
| Staging collections: `staging_courses`, `staging_course_offerings`, `staging_ingestion_runs` | Done |
| Merge duplicate courses across semester files | Done |
| Separate offering documents per semester snapshot | Done |
| Production collections | **Not written** |
| Degree requirement inference from course JSON | **None** |
| Node / Python API changes | **None** |

Semester JSON files are **offering snapshots** (200=winter, 201=spring, 202=summer), not the full canonical catalog. All staged documents keep `productionEligible: false`.

### Python Phase 10 status (implemented — staging quality review, report-only)

| Item | Status |
|---|---|
| CLI: `validate-dds-staging-quality` | Done |
| Module `app/quality/dds_staging_quality.py` | Done |
| Reports: `data/reports/technion/dds_staging_quality_report.{json,md}` | Done |
| Optional audit: `staging_data_quality_reports` (`--write-staging-audit`) | Done |
| Cross-link catalog course refs ↔ `staging_courses` | Done |
| OCR-suspect / credit mismatch / manual-review summaries | Done |
| Staged or production record mutation | **None** |
| Production promotion | **Blocked** |
| Node / Python API changes | **None** |

Phase 10 answers whether staged DDS + course data is safe enough to **design** a promotion gate later. Findings classify as `info`, `warning`, `staging-blocker`, `production-blocker`, or `api-migration-blocker`.

### Python Phase 10.5 status (implemented — blocker cleanup + revalidation)

| Item | Status |
|---|---|
| CLI: `cleanup-dds-staging-blockers` (`--dry-run`) | Done |
| Module `app/curation/dds_catalog_blocker_cleanup.py` | Done |
| Curated JSON fixes (OCR artifact removal, title enrichment, cognition track rule) | Done |
| Course number normalization fix (`01040030`) | Done |
| Re-import staging catalog + re-run `validate-dds-staging-quality` | Done |
| Report: `data/reports/technion/dds_staging_blocker_cleanup_report.md` | Done |
| Production promotion | **Blocked** |
| Node / Python API changes | **None** |

Phase 10.5 applies **source-backed** curated JSON fixes only (no uncertain OCR auto-corrections). Remaining cross-link gaps for courses not in 2025 semester JSON are documented for human review before Phase 11 promotion-gate design.

### Python Phase 11 status (implemented — promotion gate dry-run only)

| Item | Status |
|---|---|
| CLI: `plan-dds-production-promotion` (`--output-json`, `--output-md`, `--strict`, `--allow-warnings`) | Done |
| CLI stub: `promote-dds-to-production` (refuses; no production writes) | Done |
| Module `app/promotion/dds_promotion_gate.py` | Done |
| Models `app/models/promotion.py` | Done |
| Reports: `data/reports/technion/dds_promotion_plan.json` / `.md` | Done |
| Human signoff policies enforced (advisory-only rules, 14 excluded courses) | Done |
| Production collection writes | **None** |
| Node / Python API changes | **None** |

Phase 11 answers: *If we later run production promotion, exactly what would be promoted, skipped, and which safety checks must pass?* Default behavior is **dry-run/read-only** with respect to production collections (`degree_programs`, `degree_requirements`, `catalog_rules`, `courses`, `course_offerings`). Gate statuses: `pass`, `pass-with-warnings`, or `fail`. `canPromote: true` means Phase 12 may implement real promotion after explicit approval and a dangerous confirmation flag — **not** in Phase 11.

### Python Phase 12 status (implemented — guarded production promotion)

| Item | Status |
|---|---|
| CLI: `promote-dds-to-production` (`--i-confirm-dangerous-production-write`, `--dry-run`) | Done |
| CLI: `rollback-dds-production-promotion` (`--promotion-run-id`, dangerous flag) | Done |
| Module `app/promotion/dds_production_promoter.py` | Done |
| Audit collection: `promotion_runs` | Done |
| Reports: `data/reports/technion/dds_production_promotion_report.json` / `.md` | Done |
| Idempotent upsert by stable `productionKey` | Done |
| Node / Python API changes | **None** |

Phase 12 writes production data **only** when `--i-confirm-dangerous-production-write` is passed, the Phase 11 gate passes, and production collections are empty or idempotently compatible. `--dry-run` re-runs the gate and builds documents without writing. Rollback deletes only documents matching a given `promotionRunId`.

### Python Phase 13 status (implemented — read-only catalog API)

| Item | Status |
|---|---|
| `GET /catalog/courses` (search, pagination, optional offerings) | Done |
| `GET /catalog/courses/{course_number}` | Done |
| `GET /catalog/courses/{course_number}/offerings` | Done |
| `GET /catalog/degree-programs` | Done |
| `GET /catalog/degree-programs/{program_code}` | Done |
| `GET /catalog/degree-programs/{program_code}/requirements` (hard only) | Done |
| `GET /catalog/degree-programs/{program_code}/advisory-rules` | Done |
| `GET /catalog/degree-programs/{program_code}/catalog-summary` | Done |
| Repository `app/repositories/catalog_repository.py` (read-only) | Done |
| JWT required (matches Node catalog auth policy) | Done |
| pytest catalog unit + integration tests | Done |
Phase 13 reads **production** collections promoted in Phase 12 (`courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`). Hard requirements come only from `degree_requirements`; advisory/non-executable metadata comes only from `catalog_rules` with `enforceInGraduationProgress: false`. No write endpoints; no graduation progress or planner logic.

### Python Phase 14 status (implemented — completed courses API)

| Item | Status |
|---|---|
| `POST /completed-courses` (JWT, catalog FK validation) | Done |
| `GET /completed-courses` (paginated, user-scoped) | Done |
| `GET /completed-courses/{id}` | Done |
| `PUT /completed-courses/{id}` (manual only) | Done |
| `DELETE /completed-courses/{id}` (manual only) | Done |
| Repository `app/repositories/completed_course_repository.py` | Done |
| `courseId` validated against production `courses` collection | Done |
| Unique `(userId, courseId, attempt)` index | Done |
| `userId` server-assigned from JWT; client `userId`/`_id` rejected | Done |
| pytest unit + integration + security tests | Done |
| Graduation progress / planner / AI | Not implemented |

Phase 14 stores user-owned transcript rows in `completed_courses`. Catalog collections are read-only for FK validation. Advisory `catalog_rules` and hard `degree_requirements` are not used in completed-course logic. No graduation progress calculation.

### Python Phase 15 status (implemented — graduation progress API)

| Item | Status |
|---|---|
| `GET /graduation-progress` (JWT, self-scoped) | Done |
| `degreeId` on profile validated against `degree_programs._id` | Done |
| Hard `credit_bucket` rules from `degree_requirements` | Done |
| Linked `course_pool` enforcement for DS + faculty electives | Done |
| `semester_matrix` / track rules excluded (planning-only) | Done |
| Calculator `app/services/graduation_progress_calculator.py` | Done |
| Service `app/services/graduation_progress_service.py` | Done |
| pytest unit + integration + security tests | Done |
| API version `0.6.0` | Done |
| Semester planner / academic risk / AI | Not implemented (Python) at Phase 15 |

Phase 15 computes deterministic graduation progress at read time from the authenticated user's profile (`degreeId` → `degree_programs`), `completed_courses`, hard `degree_requirements` (`credit_bucket`), and linked `course_pool` documents in `catalog_rules` (DS elective pool + faculty elective prefix pool). Buckets without linked pools use credit-only heuristic allocation. **Grades:** Technion numeric 0–100; pass strictly above 55. Response includes `requirementProgress`, `missingRequirements`, `assumptions`, and `ineligibleCredits`.

### Python Phase 16 status (implemented — deterministic semester planner)

| Item | Status |
|---|---|
| `POST /semester-plans/generate` (JWT, self-scoped) | Done |
| `GET /semester-plans`, `GET /semester-plans/:id` | Done |
| Mandatory courses from `semester_matrix` catalog rules (primary) | Done |
| Electives from linked `course_pool` rules + graduation remaining | Done |
| Prerequisites from structured `courses.prerequisites` + `prerequisitesText` fallback | Done |
| Planner `app/planning/semester_planner.py` + `prerequisite_resolver.py` | Done |
| Service `app/services/semester_plan_service.py` | Done |
| pytest unit + integration + security + stress tests | Done |
| API version `0.7.0` | Done |
| Manual plan CRUD + weekly schedule | See Phase 16.1 |
Phase 16 generates a deterministic next-semester plan from profile, graduation progress, hard requirements, semester matrix, and course pools. Completed passing courses are excluded; failed grades do not count as completed. Plans persist in `semester_plans` with structured `explanation` (rules applied, blocked prerequisites, partial/empty plan flags).

### Python Phase 16.1 status (implemented — manual plans + weekly schedule)

| Item | Status |
|---|---|
| `POST /semester-plans` (manual create) | Done |
| `PUT /semester-plans/:id` (update courses + weekly schedule) | Done |
| `DELETE /semester-plans/:id` (archive) | Done |
| `POST /semester-plans/suggest-courses` (preview auto-pick for manual planner) | Done |
| `POST /semester-plans/suggest-schedule` (preview lesson selection) | Done |
| Weekly schedule conflict detection (`weeklySchedule.conflicts`, `weekView`) | Done |
| Offering resolution via `GET /catalog/courses/:number/offerings` data | Done |
| API version `0.8.0` | Done |
| Academic risk analyzer (Python) | Skipped for now (Phase 17) |
| Plan versioning endpoint (`POST /semester-plans/:id/versions`) | Done (Phase 16.2) |

Students can manually select catalog courses, attach offering schedule groups per semester, and receive deterministic overlap detection. Archived plans cannot be edited. New plan versions fork via `POST /semester-plans/:id/versions` with `basePlanId` linkage and incremented `version`.

### Python Phase 16.2 status (implemented — semester plan versioning)

| Item | Status |
|---|---|
| `POST /semester-plans/:id/versions` (fork owned plan) | Done |
| `basePlanId` + incremented `version` on forked plan | Done |
| Fork copies semesters/assumptions/explanation; status reset to `draft` | Done |
| Cannot fork archived plans | Done |
| API version `0.8.1` | Done |

### Python Phase 15.1 status (implemented — graduation pool data links)

| Item | Status |
|---|---|
| `linkedCreditBucketId` on promoted DS/faculty pool rules | Done |
| Promotion metadata `graduationPoolLinkPhase: 15.1` | Done |
| Pools remain `advisoryOnly` / `enforceInGraduationProgress: false` in catalog APIs | Done |
| Calculator enforces pools via explicit link (overrides naming convention) | Done |
| Human sign-off notes updated | Done |
| Re-promotion + E2E verification | Run after deploy |

Phase 15.1 adds explicit `linkedCreditBucketId` on promoted `catalog_rules` for `009216-1-000:elective-ds-pool` → `009216-1-000:elective-ds` and `009216-1-000:elective-faculty-pool` → `009216-1-000:elective-faculty`. Graduation progress uses the link; catalog read APIs still treat these as advisory metadata.

### Target Python stack

FastAPI, MongoDB, Redis, Python worker, data-engineering container, Pydantic, JWT, bcrypt, pytest, Docker Compose.

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

- **Phase 4 (catalog seed, legacy):** small curated placeholder in `data/validated/technion/2025/` — superseded by DDS promotion (Phase 12) into `unipilot_python`.
- **Phase 5 (completed courses):** implemented — user-owned transcript records in `completed_courses` with manual CRUD, catalog `courseId` validation, duplicate attempt handling, `creditsEarned` in 0.5 increments (0–36), and edit/delete restricted to `source=manual`.
- **Phase 6 (graduation progress):** implemented — deterministic `GET /graduation-progress` using student profile, completed courses, degree requirements, and catalog facts (no LLM).
- **Phase 7 (semester planner):** implemented — deterministic `POST /semester-plans/generate` plus planning history (`GET /semester-plans`, `GET /semester-plans/:id`) using profile, completed courses, catalog, degree requirements, and graduation progress (no LLM).
- **Phase 8 (academic risk analyzer):** implemented — deterministic `POST /academic-risks/analyze` plus analysis history (`GET /academic-risks`, `GET /academic-risks/:id`) using profile, completed courses, catalog, degree requirements, graduation progress, and semester plans (no LLM).
- **Later phase:** full offline pipeline (PDF/HTML extraction, normalization, validation, review, RAG generation, automated refresh).

Raw Technion inputs (PDFs, HTML pages, faculty URLs, catalogs, requirement documents, policies) flow through the pipeline defined in the ingestion architecture doc; only validated artifacts are imported into MongoDB.

## 4) Tech Stack

### 4.1 Production API (implemented)

- Runtime: Python 3.12+ (pinned in Dockerfile)
- API framework: FastAPI
- Database: MongoDB 7 (`unipilot_python` — promoted Technion DDS catalog)
- Queue/cache/rate-limit: Redis 7
- Validation: Pydantic v2
- Auth: JWT + bcrypt
- Testing: pytest + httpx + mongomock-motor (271 tests, ≥80% coverage target)
- Container orchestration: Docker Compose
- Internal services: `worker`, `ai`, `data-engineering` (not host-exposed)

See `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md` for migration history.

## 5) Docker Services

| Service | Role | Host-exposed | Internal Port | Healthcheck | Notes |
|---|---|---|---|---|---|
| `api` | FastAPI backend API | Yes (host `API_PORT` -> container `8000`) | 8000 | Yes | Sole client-facing API |
| `mongo` | Persistent database | No | 27017 | Yes | Uses `mongo_data` named volume |
| `redis` | Queue/rate-limit foundation | No | 6379 | Yes | Internal-only |
| `worker` | Background worker skeleton | No | 3002 | Yes | Internal-only |
| `ai` | AI service skeleton | No | 3001 | Yes | Internal-only |

Networking and exposure rules:
- Only `api` (FastAPI) may publish a host port during normal operation.
- All services must stay on `unipilot-internal` network.
- Do not expose `mongo`, `redis`, `worker`, or `ai`.

## 6) Backend Folder Structure

```text
services/
  api/
    app/
      main.py
      routes/
      services/
      repositories/
      planning/
    tests/
    scripts/
    Dockerfile
  data-engineering/
  worker/
  ai/
docker-compose.yml
.env.example
README.md
docs/
data/
scripts/
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
- Academic risks security tests (JWT required, cross-user isolation, userId rejection, AI rate limit 429).
- Transcript ↔ graduation progress integration tests (add/update/delete completed courses, multi-year, pool eligibility).
- Web transcript unit/page/integration tests + Playwright `transcript-progress` E2E.

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
- Read-only catalog APIs under `/catalog/*` (JWT required), backed by promoted Technion DDS production collections.
- Data-engineering pipeline promotes catalog into MongoDB (`unipilot_python`); no Node seed CLI.
- Completed courses model (`completed_courses`) with unique `(userId, courseId, attempt)` index.
- Protected completed courses CRUD (`POST/GET/PUT/DELETE /completed-courses`) with ownership checks.
- Completed course `courseId` FK validation against published `courses` catalog.
- Manual-only edit/delete policy: `PUT` / `DELETE` blocked for `official` and `imported` sources.
- Graduation progress endpoint (`GET /graduation-progress`) with deterministic requirement evaluation.
- Semester plans model (`semester_plans`) with user ownership indexes.
- Deterministic semester planner (`POST /semester-plans/generate`) and planning history (`GET /semester-plans`, `GET /semester-plans/:id`).
- Deterministic academic risk analyzer (`POST /academic-risks/analyze`) and analysis history (`GET /academic-risks`, `GET /academic-risks/:id`).

Still pending for next phases:
- AI endpoint rate limiting (implement with AI/RAG phase).
- Validate `StudentProfile.degreeId` against profile `institutionId` and `catalogYear` once catalog selection UX and multi-catalog support exist (see `docs/planning/FEATURE_BACKLOG.md` → Future TODOs).

## 9) Development Roadmap

Canonical roadmaps:

- **Delivery phases:** `docs/planning/IMPLEMENTATION_PHASES.md`, `docs/planning/FEATURE_BACKLOG.md`
- **Real DDS data:** `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`
- **Migration history (archived):** `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`

### Production backend (FastAPI — `services/api`)

**FastAPI is the sole client-facing API** (Docker service `api`, container port 8000). MongoDB database: `MONGO_DB` (default `unipilot_python`).

Implemented: auth (JWT + Google OAuth + remember-me), profile, catalog (`/catalog/*`), completed courses, graduation progress, semester plans (generate + manual + auto-pick preview + weekly schedule + versioning), academic risk analyzer, transcript UI (i18n, paginated list, progress link). API version **1.0.0**. pytest: **1391** tests (unit, integration, security, stress). Web Vitest: **242**. Playwright E2E: **18** (runs in CI).

### Still pending

- Async AI pipeline (worker + ai stubs exist; enqueue/rate-limit on AI endpoints not implemented)
- Full Technion ingestion automation beyond current DDS subset
- Simulation features
- Hardening docs: risk assessment, test report, final project report

## 10) What Has Already Been Implemented

- Multi-service Docker Compose stack (`api`, `data-engineering`, `mongo`, `redis`, `worker`, `ai`).
- Healthchecks and startup ordering for core dependencies.
- MongoDB named volume persistence (`mongo_data`).
- Host exposure for `api` (FastAPI) only; all other services internal-only.
- API `/health` endpoint and auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, Google OAuth when configured).
- Student profile endpoints (`POST/GET/PUT/DELETE /student-profile`) with JWT protection and ownership checks.
- Completed courses endpoints (`POST/GET/PUT/DELETE /completed-courses`) with JWT protection, ownership checks, catalog FK validation, and manual-only mutations.
- Graduation progress endpoint (`GET /graduation-progress`) with JWT protection and deterministic requirement evaluation.
- Semester plans endpoints (`POST /semester-plans/generate`, manual `POST/PUT/DELETE /semester-plans`, `POST /semester-plans/:id/versions`, `GET /semester-plans`, `GET /semester-plans/:id`) with JWT protection, ownership checks, and deterministic or manual planner metadata.
- Academic risks model (`academic_risks`) with user ownership indexes and embedded rule-based findings.
- Academic risks endpoints (`POST /academic-risks/analyze`, `GET /academic-risks`, `GET /academic-risks/:id`) with JWT protection, ownership checks, and deterministic analysis (no LLM).
- Catalog read endpoints with JWT protection (shared academic data, not user-owned).
- bcrypt password hashing, JWT token issuance, HttpOnly refresh cookies, and protected-route middleware.
- Auth validation and auth rate limiting middleware.
- Student profile validation schemas and MongoDB model/indexes.
- Completed courses validation schemas, MongoDB model/indexes, and test suites.
- Auth and student profile test suites (unit + integration + security) in addition to health test.
- Service Dockerfiles with pinned Python base images and non-root users.
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
4. Read `docs/planning/IMPLEMENTATION_PHASES.md` for phase history.
5. For catalog/ingestion design, read `docs/DATA_INGESTION_ARCHITECTURE.md`.
6. Read relevant rule files in `.cursor/rules/unipilot-*.mdc`.
7. Implement one feature at a time and update docs/tests with each feature.
