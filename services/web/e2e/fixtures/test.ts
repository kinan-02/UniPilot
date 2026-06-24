import { test as base } from '@playwright/test'
import { AuthPage } from '../pages/AuthPage'
import { CatalogPage } from '../pages/CatalogPage'
import { PlannerPage } from '../pages/PlannerPage'
import { ProgressPage } from '../pages/ProgressPage'
import { TranscriptPage } from '../pages/TranscriptPage'

type E2EFixtures = {
  authPage: AuthPage
  catalogPage: CatalogPage
  plannerPage: PlannerPage
  progressPage: ProgressPage
  transcriptPage: TranscriptPage
}

export const test = base.extend<E2EFixtures>({
  authPage: async ({ page }, use) => {
    await use(new AuthPage(page))
  },
  catalogPage: async ({ page }, use) => {
    await use(new CatalogPage(page))
  },
  plannerPage: async ({ page }, use) => {
    await use(new PlannerPage(page))
  },
  progressPage: async ({ page }, use) => {
    await use(new ProgressPage(page))
  },
  transcriptPage: async ({ page }, use) => {
    await use(new TranscriptPage(page))
  },
})

export { expect } from '@playwright/test'
