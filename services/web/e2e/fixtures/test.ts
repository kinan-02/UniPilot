import { test as base } from '@playwright/test'
import { AuthPage } from '../pages/AuthPage'
import { CatalogPage } from '../pages/CatalogPage'
import { PlannerPage } from '../pages/PlannerPage'
import { ProgressPage } from '../pages/ProgressPage'
import { TranscriptPage } from '../pages/TranscriptPage'
import { ensureWorkerAuthState } from '../helpers/worker-auth'

type E2EFixtures = {
  authPage: AuthPage
  catalogPage: CatalogPage
  plannerPage: PlannerPage
  progressPage: ProgressPage
  transcriptPage: TranscriptPage
}

type WorkerFixtures = {
  workerStorageState: string
}

export const test = base.extend<E2EFixtures, WorkerFixtures>({
  storageState: async ({ workerStorageState }, use) => {
    await use(workerStorageState)
  },

  workerStorageState: [
    async ({ browser }, use, workerInfo) => {
      const authFile = await ensureWorkerAuthState(browser, workerInfo.parallelIndex)
      await use(authFile)
    },
    { scope: 'worker' },
  ],

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
