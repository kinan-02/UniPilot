import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import type { Browser } from '@playwright/test'
import { completeOnboarding } from './onboarding'

const AUTH_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../.auth')
const PASSWORD = 'StrongPass123!'
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'

export function workerAuthFilePath(parallelIndex: number): string {
  return path.join(AUTH_DIR, `user-${parallelIndex}.json`)
}

/** Register + onboard once per parallel worker; reuse storage state file. */
export async function ensureWorkerAuthState(
  browser: Browser,
  parallelIndex: number,
): Promise<string> {
  const authFile = workerAuthFilePath(parallelIndex)
  fs.mkdirSync(AUTH_DIR, { recursive: true })
  if (fs.existsSync(authFile)) {
    return authFile
  }

  const context = await browser.newContext({ storageState: undefined, baseURL })
  const page = await context.newPage()
  const email = `e2e-worker-${parallelIndex}-${Date.now()}@example.com`

  try {
    await page.goto('/register')
    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(PASSWORD)
    const registerResponse = page.waitForResponse(
      (response) => response.url().includes('/auth/register') && response.status() === 201,
    )
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()
    await registerResponse
    await page.waitForURL('**/onboarding', { timeout: 15_000 })

    await completeOnboarding(page)
    await page.waitForURL('**/', { timeout: 15_000 })

    await page.context().storageState({ path: authFile })
    return authFile
  } finally {
    await context.close()
  }
}
