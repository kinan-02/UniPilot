# UniPilot AI

UniPilot AI is an AI-powered academic decision support platform. The **FastAPI** backend (`services/api`) and **React** web app (`services/web`) provide:

- JWT authentication, student profile, completed courses
- Production Technion DDS catalog (`/catalog/*`)
- Graduation progress, semester planning (auto + manual + weekly schedule + versioning)
- Deterministic academic risk analysis
- Docker-first deployment with MongoDB, Redis, worker, and AI stubs

Simulation and async AI recommendation features are not implemented yet.

## Services

| Service | Role | Host port |
|---------|------|-----------|
| `web` | React SPA — **primary UI** (proxies `/api` to backend) | `WEB_PORT` (default **3000**) |
| `api` | FastAPI REST API — the only backend clients ever talk to | `API_PORT` (default **8000**) |
| `transcript-parser` | Internal Technion transcript PDF extraction | none |
| `data-engineering` | Internal staging / promotion CLI | none |
| `worker` | Internal async job stub | none |
| `ai` | Internal academic advisor — the V2 agent loop behind `/advisor/ask` (grounded reasoning over the catalog/wiki with certainty tagging) | none |
| `mongo` | Persistence (`mongo_data` volume) | none |
| `redis` | Rate limits / future queue | none |

The `ai` service has its own direct read-only MongoDB access for catalog/student data and reaches back into `api` for computation that stays there (`/internal/*`). It never performs the actual write for a proposed action (save a plan, commit a transcript import) — those stay in `api`'s existing confirm/reject flow. See [`docs/agent/AGENT_ARCHITECTURE_V2.md`](docs/agent/AGENT_ARCHITECTURE_V2.md) for the agent loop's design.

Open the app at [http://localhost:3000](http://localhost:3000) after `docker compose up --build`. The web container proxies API calls to the internal `api` service.

## Prerequisites

- Docker + Docker Compose
- Python 3.12+ (optional — for local pytest without rebuilding images)
- Node.js 22+ (optional — for local frontend dev)

## Setup & run

```bash
cp .env.example .env
docker compose up --build
```

Set `MONGO_DB=unipilot_python` in `.env` (matches `.env.example`) so the API reads the promoted Technion catalog (DDS + 16 additional faculties when fully promoted).

- **Web UI:** [http://localhost:3000](http://localhost:3000) (`WEB_PORT`)
- **API health:** [http://localhost:8000/health](http://localhost:8000/health) (`API_PORT`, or via web at `/api/health`)

**First-time catalog data:** promote DDS production data via `data-engineering` (Phase 12). See [Data engineering](#data-engineering) below. The API expects published documents in `courses`, `degree_programs`, `degree_requirements`, and `catalog_rules`.

Keep `AUTO_SEED_CATALOG=false` (default in `.env.example`) so the API does **not** insert dev fixture catalog before promotion. After a volume wipe, run the vault → staging → production pipeline once (see Data engineering README).

```bash
docker compose down -v   # clean reset (destroys Mongo volume)
docker compose up --build -d
# then promote catalog (export → import staging → import courses → promote)
```

### Local frontend development

With the Docker stack running (API on host port from `.env`):

```bash
cd services/web
npm install
npm run dev
```

Vite dev server runs at [http://localhost:5173](http://localhost:5173) and proxies `/api` to `http://localhost:${API_PORT}` (override with `VITE_DEV_API_TARGET`).

## Run tests

### Backend (pytest)

`pytest.ini` in each Python service enforces **100% line coverage** (`--cov-fail-under=100`).

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Focused suites:

```bash
pytest tests/unit
pytest tests/integration
pytest tests/security
pytest tests/stress
```

Transcript parser service (internal; 100% coverage gate):

```bash
cd services/transcript-parser
pip install -r requirements-dev.txt
pytest
```

Outlook Mail MCP service (internal read-only MCP; delegated Microsoft Graph):

```bash
cd services/outlook-mcp
pip install -r requirements-dev.txt
pytest
```

See [services/outlook-mcp/README.md](services/outlook-mcp/README.md) for OAuth setup and MCP tool usage.

AI service (internal; the V2 agent loop, retrieval, tool primitives):

```bash
cd services/ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest            # live LLM tests are deselected by default (-m "not live")
```

### Full-stack verification (local)

Runs API pytest, transcript-parser pytest, web build, Vitest (file-by-file), and optional Docker health / Playwright checks with a single progress bar:

```bash
python3 scripts/extensive_verification.py --no-cov --skip-e2e --skip-docker
python3 scripts/extensive_verification.py --no-cov --skip-docker   # includes Playwright @progress
```

Writes `scripts/verification_report.json` (gitignored). Use `--smoke-only` for progress-focused API tests only.

### Docker E2E verification + benchmarks

With the stack running (uses `API_PORT` from `.env`, default 8000):

```bash
cd services/api && python scripts/verify_and_benchmark.py
cd services/api && python scripts/edge_case_verify.py   # boundary + validation checks (~28 checks)
```

Writes `services/api/scripts/verify_report.json` and `services/api/scripts/edge_case_verify_report.json`. The benchmark script covers auth, catalog, completed courses, graduation progress, semester plans (generate + manual + versioning), and academic risks against live MongoDB. The edge-case script adds pagination bounds, refresh-token rotation/reuse, student-profile validation, and related boundary checks.

### Production readiness audit

```bash
python scripts/production_audit.py
```

See also `docs/operations/PRODUCTION_DEPLOYMENT.md` and `docs/reports/PRODUCTION_AUDIT.md`.

### Frontend (Vitest + Playwright)

Unit/component tests:

```bash
cd services/web
npm install
npm run test
npm run build
```

End-to-end tests (requires Docker stack on `WEB_PORT`, default 3000):

```bash
cd services/web
npx playwright install chromium
npm run test:e2e
```

See `services/web/e2e/README.md` for architecture (Page Object Model, fixtures, accessibility gates, and CI artifacts).

```bash
npm run test:e2e:smoke          # Register/login/onboarding smoke
npm run test:e2e:critical       # Cross-feature @critical journey
npm run test:e2e:a11y           # WCAG 2.x accessibility scans
npm run test:e2e:report         # Open HTML report after a run
```

Run a single Playwright project (authenticated projects auto-register one student per parallel worker):

```bash
PLAYWRIGHT_WORKERS=4 npm run test:e2e   # optional: default 4 in CI, ~50% CPU locally
npm run test:e2e -- --project=smoke
npm run test:e2e -- --project=onboarding
npm run test:e2e -- --project=progress
npm run test:e2e -- --project=transcript-progress
npm run test:e2e -- --project=planner-catalog
npm run test:e2e -- --project=planner-auto-assist
npm run test:e2e -- --project=critical-paths
npm run test:e2e -- --project=accessibility
```

CI runs the full Playwright suite against a Docker stack with `AUTO_SEED_CATALOG=true` (see `.github/workflows/ci.yml`).

The web UI defaults to **Hebrew** (RTL) with an in-app language switcher (Hebrew / English). Open [http://localhost:3000](http://localhost:3000) after `docker compose up --build`.

## API overview (all JWT-protected except `/health`)

| Area | Key routes |
|------|------------|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Profile | `POST/GET/PUT/DELETE /student-profile` |
| Catalog | `GET /catalog/courses`, `GET /catalog/degree-programs/{code}/...` |
| Transcript | `POST/GET/PUT/DELETE /completed-courses` |
| Transcript import | `POST /transcript-import/parse` (PDF preview), `POST /transcript-import/commit` (persist selected rows) |
| Progress | `GET /graduation-progress`, `GET /graduation-progress/curriculum-graph` |
| Plans | `POST /semester-plans/generate`, `POST /semester-plans/suggest-courses`, `POST /semester-plans/suggest-schedule`, `POST/PUT/DELETE /semester-plans`, `POST /semester-plans/:id/versions` |
| Risks | `POST /academic-risks/analyze`, `GET /academic-risks`, `GET /academic-risks/:id` |
| Advisor | `POST /advisor/ask`, `POST /advisor/ask/stream` (SSE) — forwarded to the `ai` service's agent loop |

Full contract: `docs/API_SPEC.md`. API version **1.0.0**. Agent design: `docs/agent/AGENT_ARCHITECTURE_V2.md`.

### Quick start flow

Register via the web UI at `/register`, complete onboarding with a degree program, then explore catalog, transcript, progress, plans, and risks from the sidebar.

### Transcript import and progress

Technion publishes **two** official PDF transcript types. UniPilot currently imports the **summary** variant: **one row per course** with the grade from the **last** time you took it. Earlier fails or retakes are **not** on that PDF. If you need full attempt history in UniPilot, add retakes manually on the transcript page (or wait for full-transcript import support).

Summary PDF totals (accumulated credits and GPA) match the **Transcript** and **Progress** headline numbers. Requirement buckets on Progress may still assign fewer credits when pool or overlap rules apply (`degreeAppliedCredits`).

Re-upload after parser fixes so pass/exemption metadata is stored. Duplicate rows (same course, semester, and grade) are skipped on commit.

### Manual semester planner

Build a semester schedule at **`/plans/new`** or edit an existing manual plan at **`/plans/:id/edit`**.

The planner is a CheeseFork-inspired schedule workspace (product inspiration only — no CheeseFork code in this repo):

1. Select semester (year + Technion semester code: 200 winter, 201 spring, 202 summer).
2. Optional **auto-pick courses** — suggests matrix/progress-aware courses for the semester (respects max credits, offerings, exam/schedule conflicts). Preview only; edit before save. Status messages are localized (Hebrew/English).
3. Search catalog courses with offerings for that semester; preview before adding.
4. Add courses to your plan; choose exact lecture/tutorial/lab groups per course.
5. The weekly grid shows **selected lesson events from active courses only**; inactive courses stay in the list but are excluded from credits, conflicts, exams, and export.
6. Review exams, conflicts, and change warnings; save explicitly; share read-only via token or export `.ics`.

**API (preview, no persist):** `POST /semester-plans/suggest-courses`, `POST /semester-plans/suggest-schedule`.

Plan data is user-owned (`semester_plans` collection). Catalog/course/offering data is read-only. Shared plans: **`/shared/:token`** (read-only, no private profile data).

See `docs/API_SPEC.md` for `selectedLessonEvents`, `PATCH .../lesson-selection`, `plannerInsights`, and suggestion `explanation` fields (`partialPlan`, `emptyPlan`).

## Data engineering

Internal Python CLI for Technion wiki catalog export, semester JSON import, staging validation, and guarded production promotion. Shares MongoDB (`MONGO_DB`, default `unipilot_python`).

```bash
docker compose run --rm data-engineering python -m app.main health
docker compose run --rm data-engineering python -m app.main promote-dds-to-production --dry-run
```

**Promote one faculty** (export → staging → quality → production → API smoke):

```bash
bash scripts/promote_and_verify_faculty.sh <faculty-id>
# Example: bash scripts/promote_and_verify_faculty.sh civil-environmental-engineering
```

Before the first faculty promotion on a clean Mongo volume, import all Technion semester courses once:

```bash
docker compose run --rm data-engineering python -m app.main import-technion-courses-staging
```

**Verify curriculum E2E** for all promoted faculties (requires API + promoted Mongo; `AUTO_SEED_CATALOG=false`):

```bash
python3 scripts/verify_promoted_faculty_curriculum.py --base-url http://localhost:8000
python3 scripts/verify_promoted_faculty_curriculum.py --faculty-id faculty-civil-environmental-engineering
```

See `services/data-engineering/README.md` and `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`.

## Outlook Mail integration (optional)

Read-only Outlook / Microsoft 365 mail access for the autonomous agent via a controlled MCP server:

1. Set `MICROSOFT_CLIENT_ID` and `MICROSOFT_TOKEN_ENCRYPTION_KEY` in `.env` (see `.env.example`).
2. Register redirect URI `${WEB_APP_URL}/api/integrations/outlook/callback` in Azure App Registration.
3. Connect account: `GET /api/integrations/outlook/connect` (JWT required).
4. Agent calls MCP tools from `services/outlook-mcp` (stdio) with `userId` + `INTERNAL_SERVICE_TOKEN`.

Details: [services/outlook-mcp/README.md](services/outlook-mcp/README.md).

## Security & ops notes

- `web` and `api` publish host ports; all other services stay internal.
- Passwords: bcrypt; JWT from env (`JWT_SECRET` required at startup — dev default in `.env.example`; production needs a unique 32+ char secret).
- Auth rate limit: `AUTH_RATE_LIMIT_MAX` defaults to **30** in development (Docker); set **5** for production.
- Progress rate limit: `PROGRESS_RATE_LIMIT_MAX` (default **60**/min) on `GET /graduation-progress` and `/graduation-progress/curriculum-graph`.
- Transcript import rate limit: `TRANSCRIPT_IMPORT_RATE_LIMIT_MAX` (default **10**/min) on `/transcript-import/*`.
- Auth, progress, and transcript-import rate limiting via Redis.
- Replace dev secrets in `.env` before non-local deployment.
- Worker and AI remain internal stubs for a future async AI phase.

## Documentation

Full index: **[docs/README.md](docs/README.md)**

| Topic | Document |
|-------|----------|
| Project status & phases | [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) |
| API contract | [docs/API_SPEC.md](docs/API_SPEC.md) |
| MongoDB schema | [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) |
| Architecture | [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) |
| Data ingestion | [docs/DATA_INGESTION_ARCHITECTURE.md](docs/DATA_INGESTION_ARCHITECTURE.md) |
| Data-engineering CLI | [services/data-engineering/README.md](services/data-engineering/README.md) |
