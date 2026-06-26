import { expect, test } from '@playwright/test'
import { completeOnboarding, waitForDashboard, waitForOnboardingPage } from './helpers/onboarding'

const password = 'StrongPass123!'
const email = `e2e-${Date.now()}@example.com`

test.describe('UniPilot smoke flow', () => {
  test('register does not flash profile error before onboarding', async ({ page }) => {
    await page.goto('/register')
    await page.getByLabel(/אימייל|Email/i).fill(`flash-${Date.now()}@example.com`)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)

    const registerResponse = page.waitForResponse(
      (response) => response.url().includes('/auth/register') && response.status() === 201,
    )
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await registerResponse

    await expect(page.getByText('Student profile not found')).not.toBeVisible()
    await expect(page.getByRole('link', { name: /לוח בקרה|Dashboard/i })).not.toBeVisible()
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('register, onboard, browse catalog, plans, and sign out', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: /יצירת חשבון|Create your account/i })).toBeVisible()

    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()

    await completeOnboarding(page)

    await page.getByRole('navigation').getByRole('link', { name: /קטלוג|Catalog/i }).click()
    await expect(page.getByRole('heading', { name: /קטלוג קורסים|Course catalog/i })).toBeVisible()

    await page.getByRole('navigation').getByRole('link', { name: /תכנון סמסטר|Plans/i }).click()
    await expect(page.getByRole('heading', { name: /תכנון סמסטר|Semester plans/i })).toBeVisible()

    await page.getByRole('button', { name: /תוכנית חדשה|New plan/i }).click()
    await expect(page.getByText(/חיפוש קורסים לסמסטר|Search courses for semester/i)).toBeVisible()

    await page.getByRole('navigation').getByRole('link', { name: /לוח בקרה|Dashboard/i }).click()
    await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  })

  test('login page renders for guests', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  })

  test('login sends users without a profile to onboarding', async ({ browser }) => {
    const email = `login-onboard-${Date.now()}@example.com`
    const password = 'StrongPass123!'

    const registerContext = await browser.newContext()
    const registerPage = await registerContext.newPage()
    await registerPage.goto('/register')
    await registerPage.getByLabel(/אימייל|Email/i).fill(email)
    await registerPage.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await registerPage.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await waitForOnboardingPage(registerPage)
    await registerContext.close()

    const loginContext = await browser.newContext()
    const page = await loginContext.newPage()
    await page.goto('/login')
    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /התחברות|Sign in/i }).click()

    await waitForOnboardingPage(page)
    await expect(page.getByRole('link', { name: /לוח בקרה|Dashboard/i })).not.toBeVisible()
    await loginContext.close()
  })

  test('login sends users with a profile to the dashboard', async ({ page }) => {
    const email = `login-dash-${Date.now()}@example.com`
    const password = 'StrongPass123!'

    await page.goto('/register')
    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await completeOnboarding(page)

    await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()

    await page.goto('/login')
    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /התחברות|Sign in/i }).click()

    await expect(page.getByRole('heading', { name: /שלום|Hello/i })).toBeVisible({ timeout: 15_000 })
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).not.toBeVisible()
  })

  test('redirects away from onboarding when profile already exists', async ({ page }) => {
    const email = `revisit-onboard-${Date.now()}@example.com`

    await page.goto('/register')
    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await completeOnboarding(page)

    await page.goto('/onboarding')

    await waitForDashboard(page)
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).not.toBeVisible()
  })

  test('switching accounts in the same browser does not leak the previous profile', async ({
    page,
    browser,
  }) => {
    const userA = `switch-a-${Date.now()}@example.com`
    const userB = `switch-b-${Date.now()}@example.com`

    await page.goto('/register')
    await page.getByLabel(/אימייל|Email/i).fill(userA)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await completeOnboarding(page)

    await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()

    const setupContext = await browser.newContext()
    const setupPage = await setupContext.newPage()
    await setupPage.goto('/register')
    await setupPage.getByLabel(/אימייל|Email/i).fill(userB)
    await setupPage.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await setupPage.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await waitForOnboardingPage(setupPage)
    await setupContext.close()

    await page.goto('/login')
    await page.getByLabel(/אימייל|Email/i).fill(userB)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /התחברות|Sign in/i }).click()

    await waitForOnboardingPage(page)
    await expect(page.getByRole('heading', { name: /שלום|Hello/i })).not.toBeVisible()
    await expect(page.getByRole('link', { name: /לוח בקרה|Dashboard/i })).not.toBeVisible()

    await completeOnboarding(page)

    await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible({
      timeout: 15_000,
    })
    await page.goto('/login')
    await page.getByLabel(/אימייל|Email/i).fill(userA)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /התחברות|Sign in/i }).click()

    await waitForDashboard(page)
    await expect(
      page.getByRole('heading', { name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i }),
    ).not.toBeVisible()
  })
})
