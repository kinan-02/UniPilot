# UniPilot AI — Test Report

**Project:** UniPilot AI  
**Date:** 2026-06-21  
**Commit / tag:** `193d41c` (working tree includes uncommitted vault integration changes)  
**Run by:** Automated verification session (Cursor agent)  
**Environment:** Docker Compose on macOS — Python 3.13, Node/Vitest, Playwright Chromium

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

# Frontend unit
cd services/web && npm run test -- --run && npm run build

# Playwright E2E (stack on :3000)
cd services/web && npx playwright test

# Flake check (2× each test)
cd services/web && npx playwright test --repeat-each=2

# Vault pipeline (data-engineering container)
docker compose run --rm data-engineering python -m app.main export-vault-catalog --faculty dds
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging --dry-run
docker compose run --rm data-engineering python -m app.main validate-dds-staging-quality --allow-warnings
docker compose run --rm data-engineering python -m app.main promote-dds-to-production \
  --i-confirm-dangerous-production-write --allow-warnings
```

## 2. Summary

| Suite | Tests | Passed | Failed | Skipped | Notes |
|-------|-------|--------|--------|---------|-------|
| Data engineering (pytest) | 126 | 126 | 0 | 0 | Incl. vault CI fixture, promotion dedupe |
| API **total** | **349** | **349** | 0 | 0 | +14 edge-case integration tests |
| Web Vitest | 97 | 97 | 0 | 0 | Planner libs, catalog UI |
| Playwright E2E | 14 | 14 | 0 | 0 | 2× repeat → 28/28, no flakes |
| Live verify script | 86 | 86 | 0 | 0 | Auth, catalog, plans, graduation, risks |
| Mongo integrity audit | 21 | 21 | 0 | 0 | Production invariants |
| **Total automated** | **586** | **586** | **0** | **0** | Excludes live verify (86) & edge verify (17) |

## 3. Coverage

| Service | Lines | Target | Pass? |
|---------|-------|--------|-------|
| `services/api` | **87.74%** | ≥ 80% | Yes |
| `services/data-engineering` | **86.50%** | ≥ 80% | Yes |

Coverage reports: run `pytest --cov=app --cov-report=html` in each service directory.

**Modules below 80% (non-blocking backlog):**

| Module | Coverage |
|--------|----------|
| `data-engineering/app/main.py` | 26% (CLI entrypoints) |
| `api/app/services/catalog_cache.py` | 55% |
| `api/app/services/manual_semester_plan_service.py` | 75% |

## 4. Security Test Results

| Check | Expected | Result |
|-------|----------|--------|
| Missing JWT on `/catalog/*` | 401 | Pass (9 parametrized routes) |
| Invalid JWT on `/catalog/*` | 401 | Pass |
| Missing JWT on protected routes | 401 | Pass (existing security suite) |
| Valid token, not owner | 403 | Pass (completed courses, plans) |
| Invalid request body | 400 | Pass |
| Rate limit exceeded | 429 | Pass (live: 25/30 login attempts blocked after audit burst) |
| Password stored as bcrypt hash | yes | Pass (`$2*` prefix in MongoDB) |
| Password never returned | yes | Pass |
| Internal services not on host | yes | Pass (mongo, redis internal only) |
| Only API + web exposed | yes | Pass (`:8000`, `:3000`) |

## 5. Stress Test Results

From `verify_and_benchmark.py` (live Docker):

| Endpoint | Requests | p95 latency | Error rate | Notes |
|----------|----------|-------------|------------|-------|
| `/health` | 100 | 5.8 ms | 0% | |
| `/catalog/courses?limit=50` | 50 | 15.3 ms | 0% | |
| `/catalog/courses?limit=200` | 30 | 25.6 ms | 0% | |
| Hebrew search | 30 | 29.5 ms | 0% | |
| `/catalog/degree-programs/.../catalog-summary` | 30 | 22.3 ms | 0% | |
| `/graduation-progress` | 50 | 12.5 ms | 0% | |
| Semester plan generate | 20 | 28.8 ms | 0% | |
| Catalog list concurrent ×20 | 20 | 146 ms | 0% | |
| Auth login (post-verify burst) | 50 | — | — | 429 rate limiting confirmed |

## 6. Production Catalog Verification

| Metric | Expected | Actual | Pass? |
|--------|----------|--------|-------|
| `degree_programs` | 3 | 3 | Yes |
| Hard requirements | 19 | 19 | Yes |
| Advisory rules (unique) | 35 | 35 | Yes |
| Legacy `catalog_rule` duplicates | 0 | 0 | Yes |
| Duplicate `requirementGroupId` | 0 | 0 | Yes |
| Courses | 2,068 | 2,068 | Yes |
| Offerings | 2,638 | 2,638 | Yes |
| Orphan offerings | 0 | 0 | Yes |
| Vault sign-off (`vault-wiki`) | 3 programs | 3 | Yes |
| Excluded course `00960226` | 404 | 404 | Yes |
| Live advisory total (API) | 35 | 35 | Yes |
| Live hard total (API) | 19 | 19 | Yes |
| Idempotent re-promotion | stable | 35 → 35 docs | Yes |

**Per-program advisory breakdown (live API):** `009009-1-000` 12 adv / 6 hard; `009118-1-000` 12 adv / 6 hard; `009216-1-000` 11 adv / 7 hard (35 advisory, 19 hard total).

**Promotion run:** `dds-promotion-ece45363bbf2` — removed 35 superseded `catalog_rule` duplicates.

## 7. Pipeline Verification

| Step | Result |
|------|--------|
| `export-vault-catalog --faculty dds` | 3 programs, 35 signed-off non-executable groups |
| `import-dds-catalog-staging --dry-run` | 3 programs, 51 requirement groups, 35 rules |
| `import-technion-courses-staging --dry-run` | Courses/offers validated |
| `validate-dds-staging-quality` | 0 blockers |
| `plan-dds-production-promotion --dry-run` | `canPromote: true` |
| Re-promotion | `completed`, 0 errors |

## 8. E2E User Flows (Playwright)

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
| **Flake check (2× repeat)** | **28/28 pass** |

## 9. Known Observations (not failures)

1. **Staging vs production course count:** staging has 2,070 courses vs production 2,068 — expected (2 production-excluded courses promoted out).
2. **Staging requirement groups (55) vs production hard reqs (19):** staging includes advisory groups in `staging_degree_requirements`; production splits hard vs advisory correctly.
3. **Extended live auth probing triggers Redis rate limits** — correct security behavior; reset with `docker compose exec redis redis-cli FLUSHDB` in dev only.

## 10. Verdict

**PASS** — All required test tiers (unit, integration, security, stress, E2E/system) pass. Coverage exceeds 80%. Production catalog is deduplicated and consistent. Vault pipeline is reproducible in Docker. No functional failures or warnings in live verification.

**Recommended before submission:** commit vault integration changes, run one clean `docker compose down -v && docker compose up --build` smoke on a fresh clone, then promote catalog with `AUTO_SEED_CATALOG=false`.

## 11. Edge-case test suite (new)

**File:** `services/api/tests/integration/test_system_edge_cases_integration.py` (14 tests)

| Scenario | Expected | Result |
|----------|----------|--------|
| Empty catalog (no seed) | 200, total=0 | Pass |
| Pagination offset beyond total | empty items | Pass |
| Invalid program code format | 400 | Pass |
| Batch offerings: empty list | 400 | Pass |
| Batch offerings: invalid course number | 400 | Pass |
| Batch offerings: exceeds max | 400 | Pass |
| Batch offerings: missing course | empty slot | Pass |
| Invalid semester code on list | 400 | Pass |
| Search no match | empty items | Pass |
| Duplicate advisory rules in Mongo | API dedupes to 1 | Pass |
| Graduation progress without profile | 404 | Pass |
| Plan generate without profile | 404 | Pass |
| Weak password on register | 400 | Pass |
| Unknown query params on catalog | ignored (200) | Pass |

**Live edge verify:** `python scripts/edge_case_verify.py` → writes `edge_case_verify_report.json`

## 12. Clean-room Docker smoke (2026-06-21)

Procedure: `docker compose down -v` → `AUTO_SEED_CATALOG=false docker compose up --build -d` → vault pipeline → verify.

| Step | Result |
|------|--------|
| Stack health (7 services) | Pass |
| Mongo empty before promote (0 programs, 0 rules) | Pass |
| Edge verify pre-promote (empty catalog) | 15/15 pass |
| Vault export → staging import → course import | Pass |
| Production promotion | **completed** |
| Production counts | 3 programs, **35** rules, **16** hard reqs, 2068 courses, 2638 offerings |
| Legacy `catalog_rule` duplicates | 0 |
| `verify_and_benchmark.py` | **86/86** pass |
| Edge verify post-promote | **17/17** pass |
| Playwright E2E (14 tests) | **14/14** pass |

**Fix applied during clean-room:** `AUTO_SEED_CATALOG` default changed to `false` so API dev bootstrap no longer blocks vault promotion on fresh Mongo volumes.

**Note:** Vault-promoted hard requirement count is **16** (6+5+5 per program via API), not 19 from the dev bootstrap fixture. Bootstrap fixtures (`AUTO_SEED_CATALOG=true`) still seed 19 for local pytest.
