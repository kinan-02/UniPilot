import { expect, test } from '@playwright/test'
import {
  completeOnboarding,
  DEFAULT_E2E_PASSWORD,
  registerUser,
  waitForDashboard,
  waitForOnboardingPage,
} from './helpers/onboarding'

test.describe('Onboarding and profile routing', () => {
  test('deep link to a protected route sends incomplete users to onboarding', async ({ browser }) => {
    const email = `deeplink-${Date.now()}@example.com`

    const context = await browser.newContext()
    const page = await context.newPage()
    await registerUser(page, email)
    await waitForOnboardingPage(page)

    await page.goto('/catalog')
    await waitForOnboardingPage(page)
    await expect(
      page.getByRole('heading', { name: /קטלוג קורסים|Course catalog/i }),
    ).not.toBeVisible()
    await expect(page.getByRole('link', { name: /לוח בקרה|Dashboard/i })).not.toBeVisible()

    await page.goto('/plans')
    await waitForOnboardingPage(page)
    await expect(
      page.getByRole('heading', { name: /תכנון סמסטר|Semester plans/i }),
    ).not.toBeVisible()

    await context.close()
  })

  test('authenticated users with a profile are redirected away from login and register', async ({
    page,
  }) => {
    await registerUser(page, `public-route-${Date.now()}@example.com`)
    await completeOnboarding(page)

    await page.goto('/login')
    await waitForDashboard(page)
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).not.toBeVisible()

    await page.goto('/register')
    await waitForDashboard(page)
    await expect(
      page.getByRole('button', { name: /יצירת חשבון|Create account/i }),
    ).not.toBeVisible()
  })

  test('profile can be updated after onboarding', async ({ page }) => {
    await registerUser(page, `profile-edit-${Date.now()}@example.com`)
    await completeOnboarding(page)

    await page.getByRole('navigation').getByRole('link', { name: /פרופיל|Profile/i }).click()
    await expect(
      page.getByRole('button', { name: /שמור פרופיל|Save profile/i }),
    ).toBeVisible({ timeout: 15_000 })

    const maxCreditsInput = page.getByLabel(/מקסימום נקודות זכות לסמסטר|Max.*credits per semester/i)
    await maxCreditsInput.fill('21')

    const saveResponse = page.waitForResponse(
      (response) => response.url().includes('/student-profile') && response.request().method() === 'PUT',
    )
    await page.getByRole('button', { name: /שמור פרופיל|Save profile/i }).click()
    await saveResponse

    await expect(page.getByText(/הפרופיל נשמר|Profile saved/i)).toBeVisible({ timeout: 15_000 })

    await page.reload()
    await expect(maxCreditsInput).toHaveValue('21', { timeout: 15_000 })
  })

  test('MSc onboarding path completes successfully', async ({ page }) => {
    await registerUser(page, `msc-onboard-${Date.now()}@example.com`)
    await completeOnboarding(page, { programType: 'MSc' })

    await page.getByRole('navigation').getByRole('link', { name: /לוח בקרה|Dashboard/i }).click()
    await waitForDashboard(page)
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).not.toBeVisible()
  })

  test('CS general 4-year onboarding path completes successfully', async ({ page }) => {
    await registerUser(page, `cs-onboard-${Date.now()}@example.com`)
    await completeOnboarding(page, {
      facultyTestId: 'faculty-faculty-computer-science',
      primaryProgramLabel: /General Computer Science|מסלול כללי ארבע-שנתי/i,
    })

    await page.getByRole('navigation').getByRole('link', { name: /לוח בקרה|Dashboard/i }).click()
    await waitForDashboard(page)
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).not.toBeVisible()
  })
})
