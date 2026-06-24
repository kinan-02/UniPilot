import type { Page, Response } from '@playwright/test'

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
