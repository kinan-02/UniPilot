import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'
const isCI = Boolean(process.env.CI)
const workers = process.env.PLAYWRIGHT_WORKERS
  ? Number(process.env.PLAYWRIGHT_WORKERS)
  : isCI
    ? 4
    : undefined

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers,
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  reporter: isCI
    ? [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-report' }],
        ['junit', { outputFile: 'test-results/junit.xml' }],
        ['json', { outputFile: 'test-results/results.json' }],
      ]
    : [
        ['list'],
        ['html', { open: 'on-failure', outputFolder: 'playwright-report' }],
      ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    locale: 'he-IL',
  },
  projects: [
    {
      name: 'smoke',
      testMatch: /smoke\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'auth-session',
      testMatch: /auth-session\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'onboarding',
      testMatch: /onboarding\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'features',
      testMatch: /features\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'progress',
      testMatch: /progress(-polish)?\.spec\.ts/,
      testIgnore: /transcript-progress/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'transcript-progress',
      testMatch: /transcript-progress\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'planner-catalog',
      testMatch: /planner-catalog\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'planner-auto-assist',
      testMatch: /planner-auto-assist\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'critical-paths',
      testMatch: /(critical-paths|civil-critical-path)\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'accessibility',
      testMatch: /accessibility\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
