import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { request as playwrightRequest, type Browser } from '@playwright/test'
import { completeOnboarding } from './onboarding'

const AUTH_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../.auth')
const PASSWORD = 'StrongPass123!'
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'

export function workerAuthFilePath(parallelIndex: number): string {
  return path.join(AUTH_DIR, `user-${parallelIndex}.json`)
}

async function authFileIsValid(authFile: string): Promise<boolean> {
  const client = await playwrightRequest.newContext({ storageState: authFile, baseURL })
  try {
    const response = await client.get('/api/student-profile', { timeout: 10_000 })
    return response.ok()
  } catch {
    return false
  } finally {
    await client.dispose()
  }
}

/** Register + onboard once per parallel worker; reuse storage state when still valid. */
export async function ensureWorkerAuthState(
  browser: Browser,
  parallelIndex: number,
): Promise<string> {
  const authFile = workerAuthFilePath(parallelIndex)
  fs.mkdirSync(AUTH_DIR, { recursive: true })
  if (fs.existsSync(authFile) && (await authFileIsValid(authFile))) {
    return authFile
  }
  if (fs.existsSync(authFile)) {
    fs.unlinkSync(authFile)
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

    await completeOnboarding(page, {
      facultyTestId: 'faculty-faculty-dds',
      primaryProgramLabel: /Data.*Information Engineering|הנדסת נתונים ומידע/i,
    })
    await page.waitForURL('**/', { timeout: 15_000 })

    await page.context().storageState({ path: authFile })
    if (!(await authFileIsValid(authFile))) {
      throw new Error(`Worker auth state for parallel index ${parallelIndex} is not valid after onboarding`)
    }
    return authFile
  } finally {
    await context.close()
  }
}
