import { expect, test } from '@playwright/test'
import {
  createNamedPlan,
  DEFAULT_E2E_PASSWORD,
  dashboardProgramTypeLeakPattern,
  expectDashboardProgramType,
  expectSidebarEmail,
  isGoogleAuthEnabled,
  loginExistingUserExpectingDashboard,
  loginExistingUserExpectingOnboarding,
  loginWithPassword,
  registerOnboardAndReturnToDashboard,
  signInWithGoogleStub,
  signOut,
} from './helpers/auth'
import { completeOnboarding, waitForDashboard, waitForOnboardingPage } from './helpers/onboarding'
import { E2E_KNOWN_COURSE, isCatalogCourseAvailable } from './helpers/api'

test.describe('Auth session isolation', () => {
  test('does not leak dashboard identity after password account switch', async ({ page, browser }) => {
    const userA = `session-a-${Date.now()}@example.com`
    const userB = `session-b-${Date.now()}@example.com`

    await registerOnboardAndReturnToDashboard(page, userA, { programType: 'BSc' })
    await expectDashboardProgramType(page, 'BSc')

    await signOut(page)

    const setupContext = await browser.newContext()
    const setupPage = await setupContext.newPage()
    await registerOnboardAndReturnToDashboard(setupPage, userB, { programType: 'MSc' })
    await setupContext.close()

    await loginExistingUserExpectingDashboard(page, userB)
    await expectDashboardProgramType(page, 'MSc')
    await expect(page.getByRole('heading', { name: dashboardProgramTypeLeakPattern('BSc') })).not.toBeVisible()
    await expectSidebarEmail(page, userB)
  })

  test('does not leak semester plans after password account switch on plans page', async ({
    page,
    browser,
    request,
  }) => {
    test.skip(
      !(await isCatalogCourseAvailable(request, E2E_KNOWN_COURSE)),
      'Catalog not seeded (AUTO_SEED_CATALOG=true required)',
    )
    const userA = `plans-a-${Date.now()}@example.com`
    const userB = `plans-b-${Date.now()}@example.com`
    const planName = `PRIVATE-PLAN-${Date.now()}`

    await registerOnboardAndReturnToDashboard(page, userA)
    await createNamedPlan(page, planName)
    await page.getByRole('navigation').getByRole('link', { name: /תכנון סמסטר|Plans/i }).click()
    await expect(page.getByText(planName)).toBeVisible()

    await signOut(page)

    const setupContext = await browser.newContext()
    const setupPage = await setupContext.newPage()
    await registerOnboardAndReturnToDashboard(setupPage, userB)
    await setupContext.close()

    await loginExistingUserExpectingDashboard(page, userB)
    await page.getByRole('navigation').getByRole('link', { name: /תכנון סמסטר|Plans/i }).click()
    await expect(page.getByRole('heading', { name: /תכנון סמסטר|Semester plans/i })).toBeVisible()
    await expect(page.getByText(planName)).not.toBeVisible()
    await expectSidebarEmail(page, userB)
  })

  test('does not show previous dashboard after logout and login as user without profile', async ({
    page,
    browser,
  }) => {
    const userA = `profile-a-${Date.now()}@example.com`
    const userB = `profile-b-${Date.now()}@example.com`

    await registerOnboardAndReturnToDashboard(page, userA, { programType: 'BSc' })
    await expectDashboardProgramType(page, 'BSc')

    await signOut(page)

    const setupContext = await browser.newContext()
    const setupPage = await setupContext.newPage()
    await setupPage.goto('/register')
    await setupPage.getByLabel(/אימייל|Email/i).fill(userB)
    await setupPage.getByLabel(/^סיסמה$|^Password$/i).fill(DEFAULT_E2E_PASSWORD)
    await setupPage.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await waitForOnboardingPage(setupPage)
    await setupContext.close()

    await loginExistingUserExpectingOnboarding(page, userB)
    await expect(page.getByRole('heading', { name: dashboardProgramTypeLeakPattern('BSc') })).not.toBeVisible()
    await expect(page.getByRole('link', { name: /לוח בקרה|Dashboard/i })).not.toBeVisible()
  })

  test('signing back into the same account after logout still restores that user data', async ({
    page,
  }) => {
    const email = `relogin-${Date.now()}@example.com`

    await registerOnboardAndReturnToDashboard(page, email, { programType: 'PhD' })
    await expectDashboardProgramType(page, 'PhD')

    await signOut(page)
    await loginExistingUserExpectingDashboard(page, email)
    await expectDashboardProgramType(page, 'PhD')
    await expectSidebarEmail(page, email)
  })

  test('google sign-in then password sign-in does not leak previous session data', async ({
    page,
    browser,
    request,
  }) => {
    test.skip(!(await isGoogleAuthEnabled(request)), 'Google OAuth is not configured for E2E')
    test.skip(
      !(await isCatalogCourseAvailable(request, E2E_KNOWN_COURSE)),
      'Catalog not seeded (AUTO_SEED_CATALOG=true required)',
    )

    const googleEmail = `google-user-${Date.now()}@example.com`
    const passwordEmail = `password-user-${Date.now()}@example.com`
    const planName = `GOOGLE-PLAN-${Date.now()}`

    await signInWithGoogleStub(page, {
      email: googleEmail,
      googleId: `google-sub-${Date.now()}`,
    })
    await completeOnboarding(page, { programType: 'BSc' })
    await waitForDashboard(page)
    await createNamedPlan(page, planName)
    await page.getByRole('navigation').getByRole('link', { name: /תכנון סמסטר|Plans/i }).click()
    await expect(page.getByText(planName)).toBeVisible()
    await expectSidebarEmail(page, googleEmail)

    await signOut(page)

    const setupContext = await browser.newContext()
    const setupPage = await setupContext.newPage()
    await registerOnboardAndReturnToDashboard(setupPage, passwordEmail, { programType: 'MSc' })
    await setupContext.close()

    await loginWithPassword(page, passwordEmail)
    await waitForDashboard(page)

    await expect(page.getByText(planName)).not.toBeVisible()
    await expect(page.getByRole('heading', { name: dashboardProgramTypeLeakPattern('BSc') })).not.toBeVisible()
    await expectDashboardProgramType(page, 'MSc')
    await expectSidebarEmail(page, passwordEmail)
  })

  test('password sign-in then google sign-in does not leak previous session data', async ({
    page,
    request,
  }) => {
    test.skip(!(await isGoogleAuthEnabled(request)), 'Google OAuth is not configured for E2E')

    const passwordEmail = `password-first-${Date.now()}@example.com`
    const googleEmail = `google-second-${Date.now()}@example.com`

    await registerOnboardAndReturnToDashboard(page, passwordEmail, { programType: 'MSc' })
    await expectDashboardProgramType(page, 'MSc')
    await expectSidebarEmail(page, passwordEmail)

    await signOut(page)

    await signInWithGoogleStub(page, {
      email: googleEmail,
      googleId: `google-sub-${Date.now()}`,
    })
    await waitForOnboardingPage(page)
    await expect(page.getByRole('heading', { name: dashboardProgramTypeLeakPattern('MSc') })).not.toBeVisible()
  })
})
