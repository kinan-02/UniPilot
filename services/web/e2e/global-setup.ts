import { request } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'
const maxAttempts = Number(process.env.PLAYWRIGHT_HEALTH_ATTEMPTS ?? 60)
const delayMs = Number(process.env.PLAYWRIGHT_HEALTH_DELAY_MS ?? 5_000)

async function waitForHealthy(url: string, label: string) {
  const client = await request.newContext()
  try {
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const response = await client.get(url, { timeout: 10_000 })
        if (response.ok()) {
          console.log(`[e2e setup] ${label} ready (${url})`)
          return
        }
        console.warn(`[e2e setup] ${label} returned ${response.status()} (attempt ${attempt}/${maxAttempts})`)
      } catch (error) {
        console.warn(
          `[e2e setup] ${label} not ready (attempt ${attempt}/${maxAttempts}): ${error instanceof Error ? error.message : error}`,
        )
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs))
    }
    throw new Error(`[e2e setup] ${label} did not become healthy at ${url}`)
  } finally {
    await client.dispose()
  }
}

export default async function globalSetup() {
  await waitForHealthy(`${baseURL}/`, 'Web UI')
}
