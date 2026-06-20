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
  await page.context().storageState({ path: 'e2e/.auth/user.json' })
})
