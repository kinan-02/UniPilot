import { expect, test as setup } from '@playwright/test'

const password = 'StrongPass123!'
const email = `e2e-shared-${Date.now()}@example.com`

setup('prepare authenticated session', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel(/אימייל|Email/i).fill(email)
  await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
  const registerResponse = page.waitForResponse(
    (response) => response.url().includes('/auth/register') && response.status() === 201,
  )
  await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
  await registerResponse
  await page.waitForURL('**/onboarding', { timeout: 15_000 })

  const degreeSelect = page.locator('#degree-program')
  await expect(degreeSelect.locator('option')).not.toHaveCount(1, { timeout: 15_000 })

  const ieOption = degreeSelect.locator('option').filter({
    hasText: /Industrial Engineering|הנדסת תעשייה/i,
  })
  const programId =
    (await ieOption.first().getAttribute('value')) ??
    (await degreeSelect.locator('option').nth(1).getAttribute('value'))
  if (programId) {
    await degreeSelect.selectOption(programId)
    await page.getByRole('button', { name: /המשך ללוח הבקרה|Continue to dashboard/i }).click()
    await page.waitForURL('**/', { timeout: 15_000 })
  }

  await page.context().storageState({ path: 'e2e/.auth/user.json' })
})
