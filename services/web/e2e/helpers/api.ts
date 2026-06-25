import type { Page, Response } from '@playwright/test'
import { E2E_KNOWN_COURSE } from './planner'

type WaitForApiOptions = {
  method?: string
  status?: number
  timeout?: number
}

/** Wait for a matching API response instead of arbitrary sleeps. */
export async function waitForApiResponse(
  page: Page,
  urlPattern: RegExp | string,
  options: WaitForApiOptions = {},
): Promise<Response> {
  const { method, status, timeout = 30_000 } = options
  const pattern = typeof urlPattern === 'string' ? new RegExp(urlPattern) : urlPattern

  return page.waitForResponse(
    (response) => {
      if (!pattern.test(response.url())) return false
      if (method && response.request().method() !== method) return false
      if (status != null && response.status() !== status) return false
      return true
    },
    { timeout },
  )
}

export async function isCatalogCourseAvailable(
  request: Page['request'] | import('@playwright/test').APIRequestContext,
  courseNumber: string,
): Promise<boolean> {
  const probeEmail = `catalog-probe-${Date.now()}@example.com`
  const register = await request.post('/api/auth/register', {
    data: { email: probeEmail, password: 'StrongPass123!' },
  })
  if (!register.ok()) return false

  const response = await request.get(
    `/api/catalog/courses?search=${encodeURIComponent(courseNumber)}&limit=5`,
  )
  if (!response.ok()) return false
  const body = (await response.json()) as {
    data?: { items?: Array<{ courseNumber?: string }> }
  }
  return (body.data?.items ?? []).some((course) => course.courseNumber === courseNumber)
}

export { E2E_KNOWN_COURSE }
