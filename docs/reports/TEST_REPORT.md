# UniPilot AI — Test Report

**Project:** UniPilot AI  
**Date:** 2026-06-23  
**Commit / tag:** `53822c8` (+ transcript UI + Playwright CI)  
**Run by:** Automated verification session  
**Environment:** Docker Compose — Python 3.12, Node 22 / Vitest, Playwright Chromium

## 1. How to Reproduce

```bash
# Full stack
docker compose up -d --build

# Backend (API) — pytest.ini enforces 100% line coverage
cd services/api && source .venv/bin/activate && pytest

# Data engineering — pytest.ini enforces 100% line coverage
cd services/data-engineering && source .venv/bin/activate && pytest

# Live Docker E2E + benchmarks (stack must be running)
cd services/api && python scripts/verify_and_benchmark.py
cd services/api && python scripts/edge_case_verify.py

# Production readiness audit
python scripts/production_audit.py

# Frontend unit
cd services/web && npm run test -- --run && npm run build

# Playwright E2E (stack on :3000; CI sets AUTO_SEED_CATALOG=true)
cd services/web && npx playwright install chromium && npm run test:e2e

# Vault parity (data-engineering container)
docker compose run --rm data-engineering python -m app.main verify-vault-production-parity --faculty dds
```

## 2. Summary

| Suite | Tests | Passed | Failed | Skipped | Notes |
|-------|-------|--------|--------|---------|-------|
| Data engineering (pytest) | 616 | 616 | 0 | 0 | **100% line coverage** |
| API **total** | **1330** | **1330** | 0 | 0 | **100% line coverage**; includes Google OAuth + transcript↔progress integration |
| Web Vitest | 227 | 227 | 0 | 0 | Transcript lib/page, planner, catalog, progress UI |
| Playwright E2E | 15 | 15 | 0 | 0 | smoke, onboarding, features, progress, planner-catalog, transcript-progress |
| Live verify script | 86 | 86 | 0 | 0 | Auth, catalog, plans, graduation, risks |
| Edge-case verify | 17 | 17 | 0 | 0 | Boundary + validation checks |
| Vault production parity | 51 | 51 | 0 | 0 | 16 hard + 35 advisory groups |
| **Total automated (pytest + vitest + e2e)** | **2188** | **2188** | 0 | 0 | Excludes live verify scripts |

## 3. Coverage

| Service | Lines | Target | Pass? |
|---------|-------|--------|-------|
| `services/api` | **100%** | 100% | Yes |
| `services/data-engineering` | **100%** | 100% | Yes |

CI (`.github/workflows/ci.yml`) and local `pytest.ini` both enforce `--cov-fail-under=100`.

## 3b. Test quality principles

- **Behavior over lines:** tests assert outcomes (status codes, error messages, deduped counts), not just execution.
- **Layered suites:** unit (pure logic), integration (mongomock/HTTP), security (401/403/429), stress (verify script), E2E (Playwright).
- **No silent gaps:** 100% line coverage is required; new code must ship with tests that fail if behavior regresses.
- **Transcript ↔ progress:** API integration tests verify completed-course mutations update graduation progress; web integration + Playwright cover the UI invalidation path.

## 4. Security Test Results

| Check | Expected | Result |
|-------|----------|--------|
| Missing JWT on `/catalog/*` | 401 | Pass |
| Invalid JWT on protected routes | 401 | Pass |
| Valid token, not owner | 403/404 | Pass |
| Invalid request body | 400 | Pass |
| Auth rate limit exceeded | 429 | Pass (live + security suite) |
| **AI rate limit** (`POST /academic-risks/analyze`) | **429** | **Pass** (`test_analyze_enforces_ai_rate_limit_with_429`) |
| Google OAuth state / token validation | 400/401 on bad input | Pass |
| Password stored as bcrypt hash | yes | Pass |
| Password never returned | yes | Pass |
| JWT placeholder rejected in production | fail-fast | Pass (`require_jwt_secret`) |
| Internal services not on host | yes | Pass (mongo, redis, worker, ai internal) |
| Only API + web exposed (dev compose) | yes | Pass (`:8000`, `:3000`; prod override hides API) |

## 5. Stress Test Results

From `verify_and_benchmark.py` (live Docker):

| Endpoint | Requests | p95 latency | Error rate |
|----------|----------|-------------|------------|
| `/health` | 100 | ~9 ms | 0% |
| `/catalog/courses?limit=50` | 50 | ~17 ms | 0% |
| `/graduation-progress` | 50 | ~10 ms | 0% |
| Semester plan generate | 20 | ~34 ms | 0% |
| Auth login burst | 50 | — | 429 rate limiting confirmed |

## 6. Production Catalog Verification

| Metric | Expected | Actual | Pass? |
|--------|----------|--------|-------|
| `degree_programs` | 3 | 3 | Yes |
| Hard requirements | 16 | 16 | Yes |
| Advisory rules | 35+ | 46 (dev seed) / 51 (vault parity) | Yes |
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
| Graduation progress pools + i18n | Pass |
| **Transcript add course → progress summary updates** | **Pass** |
| Guest redirect to login | Pass |

## 8. CI

GitHub Actions workflow `.github/workflows/ci.yml`:

- Security scans (Bandit, pip-audit, npm audit)
- API pytest with `--cov-fail-under=100`
- Data-engineering pytest with `--cov-fail-under=100`
- Web Vitest + production build
- **Playwright E2E** against Docker stack (`AUTO_SEED_CATALOG=true` for CI catalog bootstrap)

## 9. Verdict

**PASS** — All required test tiers (unit, integration, security, stress, E2E/system) pass. Coverage exceeds 80% (100% on Python services). Auth, AI rate limits, and Google OAuth security tests pass. Playwright E2E runs in CI.
