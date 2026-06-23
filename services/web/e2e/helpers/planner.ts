import type { Page } from '@playwright/test'

/** AUTO_SEED catalog offerings use Technion spring (201) for academic year 2025. */
export const E2E_PLANNER_SEMESTER = '2025-2'

export async function selectPlannerSemester(page: Page, semesterCode = E2E_PLANNER_SEMESTER) {
  await page.locator('#planner-semester').selectOption(semesterCode)
}
