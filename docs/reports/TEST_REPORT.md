# UniPilot AI — Test Report

**Project:** UniPilot AI  
**Date:** 2026-06-21  
**Commit / tag:** `16cb178` (+ uncommitted AI rate limit, CI, runbook)  
**Run by:** Automated verification session (Cursor agent)  
**Environment:** Docker Compose on macOS — Python 3.12/3.13, Node/Vitest, Playwright Chromium

## 1. How to Reproduce

```bash
# Full stack
docker compose up -d --build

# Backend (API)
cd services/api && source .venv/bin/activate && pytest

# Backend coverage gate (≥80%)
cd services/api && pytest --cov=app --cov-fail-under=80

# Data engineering
cd services/data-engineering && source .venv/bin/activate && pytest --cov=app --cov-fail-under=80

# Live Docker E2E + benchmarks (stack must be running)
cd services/api && python scripts/verify_and_benchmark.py
cd services/api && python scripts/edge_case_verify.py

# Production readiness audit
python scripts/production_audit.py

# Frontend unit
cd services/web && npm run test -- --run && npm run build

# Playwright E2E (stack on :3000)
cd services/web && npx playwright test

# Vault parity (data-engineering container)
docker compose run --rm data-engineering python -m app.main verify-vault-production-parity --faculty dds
```

## 2. Summary

| Suite | Tests | Passed | Failed | Skipped | Notes |
|-------|-------|--------|--------|---------|-------|
| Data engineering (pytest) | 120 | 120 | 0 | 0 | Vault pipeline, promotion dedupe |
| API **total** | **356** | **356** | 0 | 0 | + AI rate limit security test |
| Web Vitest | 97 | 97 | 0 | 0 | Planner libs, catalog UI |
| Playwright E2E | 14 | 14 | 0 | 0 | Live vault catalog flows |
| Live verify script | 86 | 86 | 0 | 0 | Auth, catalog, plans, graduation, risks |
| Edge-case verify | 17 | 17 | 0 | 0 | Boundary + validation checks |
| Vault production parity | 51 | 51 | 0 | 0 | 16 hard + 35 advisory groups |
| **Total automated (pytest + vitest + e2e)** | **587** | **587** | 0 | 0 | Excludes live verify scripts |

## 3. Coverage

| Service | Lines | Target | Pass? |
|---------|-------|--------|-------|
| `services/api` | **87.88%** | ≥ 80% | Yes |
| `services/data-engineering` | **≥ 86%** | ≥ 80% | Yes |

## 4. Security Test Results

| Check | Expected | Result |
|-------|----------|--------|
| Missing JWT on `/catalog/*` | 401 | Pass |
| Invalid JWT on protected routes | 401 | Pass |
| Valid token, not owner | 403/404 | Pass |
| Invalid request body | 400 | Pass |
| Auth rate limit exceeded | 429 | Pass (live + security suite) |
| **AI rate limit** (`POST /academic-risks/analyze`) | **429** | **Pass** (`test_analyze_enforces_ai_rate_limit_with_429`) |
| Password stored as bcrypt hash | yes | Pass |
| Password never returned | yes | Pass |
| JWT placeholder rejected in production | fail-fast | Pass (`require_jwt_secret`) |
| Internal services not on host | yes | Pass (mongo, redis, worker, ai internal) |
| Only API + web exposed | yes | Pass (`:8000`, `:3000`) |

## 5. Stress Test Results

From `verify_and_benchmark.py` (live Docker, 2026-06-21):

| Endpoint | Requests | p95 latency | Error rate |
|----------|----------|-------------|------------|
| `/health` | 100 | 8.8 ms | 0% |
| `/catalog/courses?limit=50` | 50 | 16.6 ms | 0% |
| `/catalog/courses?limit=200` | 30 | 23.6 ms | 0% |
| Hebrew search | 30 | 28.9 ms | 0% |
| `/graduation-progress` | 50 | 10.2 ms | 0% |
| Semester plan generate | 20 | 33.7 ms | 0% |
| Catalog list concurrent ×20 | 20 | 140 ms | 0% |
| Auth login burst | 50 | — | 429 rate limiting confirmed |

## 6. Production Catalog Verification

| Metric | Expected | Actual | Pass? |
|--------|----------|--------|-------|
| `degree_programs` | 3 | 3 | Yes |
| Hard requirements | 16 | 16 | Yes |
| Advisory rules | 35 | 35 | Yes |
| Courses | 2,068 | 2,068 | Yes |
| Offerings | 2,638 | 2,638 | Yes |
| Vault parity matched groups | 51 | 51 | Yes |
| Excluded course `00960226` | 404 | 404 | Yes |

## 7. E2E User Flows (Playwright)

| Flow | Status |
|------|--------|
| Register → onboard → catalog → plans → sign out | Pass |
| Catalog search + course detail | Pass |
| Planner: maybe courses, lesson selection, save | Pass |
| Saved plan persistence after reload | Pass |
| Live vault course `00940345` in planner | Pass |
| Weekly grid shows DNE discrete math | Pass |
| Profile shows 3 DDS programs | Pass |
| i18n EN/HE switch | Pass |
| Guest redirect to login | Pass |

## 8. CI

GitHub Actions workflow `.github/workflows/ci.yml`:

- API pytest with `--cov-fail-under=80`
- Data-engineering pytest with `--cov-fail-under=80`
- Web Vitest + production build

## 9. Verdict

**PASS** — All required test tiers (unit, integration, security, stress, E2E/system) pass. Coverage exceeds 80%. Auth and AI rate limits enforced. Production catalog matches vault sign-off. Docker stack starts with synced `.env` (`AUTH_RATE_LIMIT_MAX=30`, `AI_RATE_LIMIT_MAX=10`).
