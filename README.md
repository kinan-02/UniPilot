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
| `api` | FastAPI REST API | `API_PORT` (default **8000**) |
| `data-engineering` | Internal staging / promotion CLI | none |
| `worker` | Internal async job stub | none |
| `ai` | Internal inference stub | none |
| `mongo` | Persistence (`mongo_data` volume) | none |
| `redis` | Rate limits / future queue | none |

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

Set `MONGO_DB=unipilot_python` in `.env` (matches `.env.example`) so the API reads the promoted Technion DDS catalog.

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

### Docker E2E verification + benchmarks

With the stack running (uses `API_PORT` from `.env`, default 8000):

```bash
cd services/api && python scripts/verify_and_benchmark.py
cd services/api && python scripts/edge_case_verify.py   # boundary + validation checks
```

Writes `services/api/scripts/verify_report.json`. Covers auth, catalog, completed courses, graduation progress, semester plans (generate + manual + versioning), and academic risks against live MongoDB.

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

End-to-end smoke tests (requires Docker stack on `WEB_PORT`, default 3000):

```bash
cd services/web
npx playwright install chromium
npm run test:e2e
```

The web UI defaults to **Hebrew** (RTL) with an in-app language switcher (Hebrew / English). Open [http://localhost:3000](http://localhost:3000) after `docker compose up --build`.

## API overview (all JWT-protected except `/health`)

| Area | Key routes |
|------|------------|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Profile | `POST/GET/PUT/DELETE /student-profile` |
| Catalog | `GET /catalog/courses`, `GET /catalog/degree-programs/{code}/...` |
| Transcript | `POST/GET/PUT/DELETE /completed-courses` |
| Progress | `GET /graduation-progress` |
| Plans | `POST /semester-plans/generate`, `POST/PUT/DELETE /semester-plans`, `POST /semester-plans/:id/versions` |
| Risks | `POST /academic-risks/analyze`, `GET /academic-risks`, `GET /academic-risks/:id` |

Full contract: `docs/API_SPEC.md`. API version **1.0.0**.

### Quick start flow

Register via the web UI at `/register`, complete onboarding with a degree program, then explore catalog, transcript, progress, plans, and risks from the sidebar.

### Manual semester planner

Build a semester schedule at **`/plans/new`** or edit an existing manual plan at **`/plans/:id/edit`**.

The planner is a CheeseFork-inspired schedule workspace (product inspiration only — no CheeseFork code in this repo):

1. Select semester (year + Technion semester code: 200 winter, 201 spring, 202 summer).
2. Search catalog courses with offerings for that semester; preview before adding.
3. Add courses to your plan; choose exact lecture/tutorial/lab groups per course.
4. The weekly grid shows **selected lesson events from active courses only**; inactive courses stay in the list but are excluded from credits, conflicts, exams, and export.
5. Review exams, conflicts, and change warnings; save explicitly; share read-only via token or export `.ics`.

Plan data is user-owned (`semester_plans` collection). Catalog/course/offering data is read-only. Shared plans: **`/shared/:token`** (read-only, no private profile data).

See `docs/API_SPEC.md` for `selectedLessonEvents`, `PATCH .../lesson-selection`, and `plannerInsights`.

## Data engineering

Internal Python CLI for Technion DDS ingestion, staging validation, and guarded production promotion. Shares MongoDB (`MONGO_DB`, default `unipilot_python`).

```bash
docker compose run --rm data-engineering python -m app.main health
docker compose run --rm data-engineering python -m app.main promote-dds-to-production --dry-run
```

See `services/data-engineering/README.md` and `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`.

## Security & ops notes

- `web` and `api` publish host ports; all other services stay internal.
- Passwords: bcrypt; JWT from env (`JWT_SECRET` required at startup — dev default in `.env.example`; production needs a unique 32+ char secret).
- Auth rate limit: `AUTH_RATE_LIMIT_MAX` defaults to **30** in development (Docker); set **5** for production.
- Auth rate limiting via Redis.
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
