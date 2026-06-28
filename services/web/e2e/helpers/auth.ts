import { expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  completeOnboarding,
  DEFAULT_E2E_PASSWORD,
  waitForDashboard,
  waitForOnboardingPage,
  type OnboardingProgramType,
} from './onboarding'
import { E2E_KNOWN_COURSE, E2E_PLANNER_SEMESTER } from './planner'

export { DEFAULT_E2E_PASSWORD }

export async function isGoogleAuthEnabled(request: APIRequestContext): Promise<boolean> {
  const response = await request.get('/api/auth/providers')
  if (!response.ok()) return false
  const body = (await response.json()) as {
    data?: { google?: boolean; googleE2eStub?: boolean }
  }
  return body.data?.google === true && body.data?.googleE2eStub === true
}

export async function signOut(page: Page) {
  await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
  await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible({
    timeout: 15_000,
  })
}

export async function loginWithPassword(
  page: Page,
  email: string,
  password = DEFAULT_E2E_PASSWORD,
) {
  await page.goto('/login')
  await page.getByLabel(/אימייל|Email/i).fill(email)
  await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
  const loginResponse = page.waitForResponse(
    (response) => response.url().includes('/auth/login') && response.status() === 200,
  )
  await page.getByRole('button', { name: /התחברות|Sign in/i }).click()
  await loginResponse
}

export async function signInWithGoogleStub(
  page: Page,
  options: { email: string; googleId: string },
) {
  const start = await page.request.get('/api/auth/google', { maxRedirects: 0 })
  expect(start.status()).toBe(302)
  const location = start.headers().location
  if (!location) {
    throw new Error('Google OAuth start did not return a redirect location')
  }

  const state = new URL(location).searchParams.get('state')
  if (!state) {
    throw new Error('Google OAuth start did not include OAuth state')
  }

  const code = `e2e|${options.email}|${options.googleId}`
  const callbackUrl = `/api/auth/google/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`
  await page.goto(callbackUrl)
  await page.waitForURL((url) => !url.pathname.includes('/auth/callback'), { timeout: 20_000 })
}

export async function expectSidebarEmail(page: Page, email: string) {
  await expect(page.locator('aside').getByText(email, { exact: true })).toBeVisible({
    timeout: 15_000,
  })
}

export function dashboardProgramTypeHeadingPattern(programType: OnboardingProgramType): RegExp {
  return new RegExp(
    `(?:Hello,? ${programType} student|שלום,? ${programType} סטודנט)`,
    'i',
  )
}

export function dashboardProgramTypeLeakPattern(programType: OnboardingProgramType): RegExp {
  return new RegExp(`${programType} (?:student|סטודנט)`, 'i')
}

export async function expectDashboardProgramType(page: Page, programType: OnboardingProgramType) {
  await expect(
    page.getByRole('heading', { name: dashboardProgramTypeHeadingPattern(programType) }),
  ).toBeVisible({ timeout: 15_000 })
}

export async function createNamedPlan(page: Page, planName: string) {
  await page.goto('/plans/new')
  await page.locator('#planner-semester').selectOption(E2E_PLANNER_SEMESTER)
  await page.getByLabel(/שם התוכנית|Plan name/i).fill(planName)

  const searchInput = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
  const searchResponse = page.waitForResponse(
    (response) => response.url().includes('/catalog/courses') && response.status() === 200,
    { timeout: 30_000 },
  )
  await searchInput.fill(E2E_KNOWN_COURSE)
  await searchResponse

  await expect(page.getByText(new RegExp(E2E_KNOWN_COURSE)).first()).toBeVisible({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()

  const lesson = page
    .getByTestId('weekly-schedule-grid')
    .getByRole('button')
    .filter({ hasText: E2E_KNOWN_COURSE })
    .first()
  await expect(lesson).toBeVisible({ timeout: 15_000 })
  await lesson.click()
  await page.getByRole('button', { name: /שמירת תוכנית|Save plan/i }).click()
  await expect(page).toHaveURL(/\/plans\/[^/]+\/edit/, { timeout: 20_000 })
}

export async function registerOnboardAndReturnToDashboard(
  page: Page,
  email: string,
  options?: { programType?: OnboardingProgramType },
) {
  await page.goto('/register')
  await page.getByLabel(/אימייל|Email/i).fill(email)
  await page.getByLabel(/^סיסמה$|^Password$/i).fill(DEFAULT_E2E_PASSWORD)
  await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
  await completeOnboarding(page, options)
  await waitForDashboard(page)
}

export async function loginExistingUserExpectingDashboard(page: Page, email: string) {
  await loginWithPassword(page, email)
  await waitForDashboard(page)
}

export async function loginExistingUserExpectingOnboarding(page: Page, email: string) {
  await loginWithPassword(page, email)
  await waitForOnboardingPage(page)
}
