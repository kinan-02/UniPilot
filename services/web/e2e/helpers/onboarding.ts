import { expect, type Page } from '@playwright/test'

export const DEFAULT_E2E_PASSWORD = 'StrongPass123!'

export type OnboardingProgramType = 'BSc' | 'MSc' | 'PhD' | 'MBA'

export async function waitForOnboardingPage(page: Page) {
  await expect(
    page.getByRole('heading', {
      name: /What degree level are you in\?|באיזו רמת תואר אתה לומד\?/i,
    }),
  ).toBeVisible({ timeout: 15_000 })
}

export async function waitForDashboard(page: Page) {
  await expect(page.getByRole('heading', { name: /שלום|Hello/i })).toBeVisible({ timeout: 15_000 })
}

export async function registerUser(
  page: Page,
  email = `e2e-${Date.now()}@example.com`,
  password = DEFAULT_E2E_PASSWORD,
) {
  await page.goto('/register')
  await page.getByLabel(/אימייל|Email/i).fill(email)
  await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
  await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
  return { email, password }
}

export async function completeOnboarding(
  page: Page,
  options?: { programType?: OnboardingProgramType },
) {
  const programType = options?.programType ?? 'BSc'
  await waitForOnboardingPage(page)

  if (programType !== 'BSc') {
    await page.getByTestId(`program-type-${programType}`).click()
  }

  await page.getByTestId('onboarding-continue').click()

  await expect(
    page.getByRole('heading', { name: /Which faculty\?|באיזו פקולטה\?/i }),
  ).toBeVisible({ timeout: 15_000 })

  const firstFaculty = page.locator('[data-testid^="faculty-"]').first()
  await expect(firstFaculty).toBeVisible({ timeout: 15_000 })
  await firstFaculty.click()
  await expect(page.getByTestId('onboarding-continue')).toBeEnabled({ timeout: 15_000 })
  await page.getByTestId('onboarding-continue').click()

  const primaryProgramCard = page.locator('label:has(input[name="primary-program"])').first()
  await expect(primaryProgramCard).toBeVisible({ timeout: 15_000 })
  await primaryProgramCard.click()
  await page.getByTestId('onboarding-continue').click()

  await expect(
    page.getByRole('heading', { name: /What semester are you in\?|באיזה סמסטר אתה עכשיו\?/i }),
  ).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('onboarding-finish').click()

  await waitForDashboard(page)
}
