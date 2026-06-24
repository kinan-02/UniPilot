# UniPilot E2E Testing

Industry-grade Playwright suite for full-stack verification against the Docker stack.

## Standards

| Practice | Implementation |
|----------|----------------|
| Page Object Model | `e2e/pages/*` — stable, reusable UI actions |
| Custom fixtures | `e2e/fixtures/test.ts` — inject page objects per test |
| Stable selectors | `data-testid`, roles, and accessible labels (bilingual he/en) |
| No arbitrary sleeps | `waitForApiResponse()` and Playwright auto-waiting |
| Auth reuse | `auth.setup.ts` → `e2e/.auth/user.json` storage state |
| Global health gate | `global-setup.ts` waits for web UI before any spec |
| Failure artifacts | trace (retry), screenshot, video (CI + local) |
| Accessibility gate | `@axe-core/playwright` — WCAG 2.x Level A/AA (`@a11y` project) |
| Critical path tag | `@critical` — single cross-feature student journey |
| CI reporting | HTML + JUnit + JSON reports uploaded as GitHub artifacts |

## Layout

```
e2e/
├── fixtures/test.ts      # Extended test with page object fixtures
├── pages/                # Page Object Model
├── helpers/              # onboarding, planner, api, a11y
├── global-setup.ts       # Stack health check
├── auth.setup.ts         # Shared authenticated session
├── smoke.spec.ts         # Register/login/onboarding (no shared auth)
├── accessibility.spec.ts # WCAG scans on core routes
├── critical-paths.spec.ts# End-to-end student journey (@critical)
└── …feature specs
```

## Running locally

Requires the Docker stack (`docker compose up --build` from repo root) and `AUTO_SEED_CATALOG=true` in `.env` for catalog/planner specs.

```bash
cd services/web
npm ci
npx playwright install chromium
npm run test:e2e
```

### Selective runs

```bash
npm run test:e2e:smoke          # Auth + onboarding smoke only
npm run test:e2e:critical       # @critical journey (isolated fresh user)
npm run test:e2e:a11y           # Accessibility project
npm run test:e2e -- --project=planner-catalog
npm run test:e2e:report         # Open last HTML report
```

## Writing new tests

1. Add interactions to the relevant page object in `e2e/pages/`.
2. Import `test` and `expect` from `e2e/fixtures/test.ts` (not `@playwright/test` directly) when using page objects.
3. Prefer `data-testid` for product-specific elements; use roles/labels for standard controls.
4. Wait on network: `waitForApiResponse(page, /\/catalog\/courses/, { method: 'GET' })`.
5. Tag long journeys with `@critical` or domain tags for selective CI sharding later.
6. Cross-feature journeys (`critical-paths.spec.ts`) register a **fresh user** so they stay isolated from shared `auth.setup` state.

## CI

`.github/workflows/ci.yml` runs the full suite against `docker compose` with `AUTO_SEED_CATALOG=true`. On failure, download **playwright-report** and **playwright-test-results** artifacts from the Actions run.
