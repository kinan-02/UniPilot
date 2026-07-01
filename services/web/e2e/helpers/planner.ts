import type { Page } from '@playwright/test'

/** Course present in AUTO_SEED catalog and promoted vault snapshots. */
export const E2E_KNOWN_COURSE = '00940345'

/** DNE data-science elective present in AUTO_SEED elective-ds-pool refs. */
export const E2E_DNE_ELECTIVE_COURSE = '00940411'

/** Catalog course outside DNE requirement pools — triggers ineligible credit on progress. */
export const E2E_OUT_OF_POOL_COURSE = '02340117'

/** AUTO_SEED catalog offerings use Technion spring (201) for academic year 2025. */
export const E2E_PLANNER_SEMESTER = '2025-2'

export async function selectPlannerSemester(page: Page, semesterCode = E2E_PLANNER_SEMESTER) {
  await page.locator('#planner-semester').selectOption(semesterCode)
}
