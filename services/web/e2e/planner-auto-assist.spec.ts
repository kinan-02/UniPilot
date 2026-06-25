import { expect, test } from './fixtures/test'
import { E2E_PLANNER_SEMESTER } from './helpers/planner'

/**
 * Auto-pick assistant on /plans/new.
 * Works with both AUTO_SEED (CI) and promoted vault catalogs — asserts localized
 * messaging only, never raw backend English summaries.
 */
test.describe('Planner auto-pick assistant', () => {
  test.beforeEach(async ({ plannerPage }) => {
    await plannerPage.openNewPlanWithSemester(E2E_PLANNER_SEMESTER)
  })

  test('auto-pick shows localized status (not backend English)', async ({ plannerPage }) => {
    await plannerPage.autoPickCourses()

    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.autoPickStatus).toHaveText(/נוספו|לא נמצאו|כבר נמצאים/)
    await expect(plannerPage.autoPickStatus).not.toHaveText(/Partial plan generated|maxCredits/i)
  })

  test('second auto-pick keeps localized status without backend English', async ({ plannerPage }) => {
    await plannerPage.autoPickCourses()
    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    const firstStatus = (await plannerPage.autoPickStatus.textContent()) ?? ''
    const countAfterFirst = await plannerPage.countSelectedCourses()

    await plannerPage.autoPickCourses()
    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.autoPickStatus).toHaveText(/נוספו|לא נמצאו|כבר נמצאים/)
    await expect(plannerPage.autoPickStatus).not.toHaveText(/Partial plan generated|maxCredits/i)

    const countAfterSecond = await plannerPage.countSelectedCourses()
    expect(countAfterSecond).toBeGreaterThanOrEqual(countAfterFirst)
    if (/נוספו/.test(firstStatus) && countAfterFirst > 0 && countAfterSecond === countAfterFirst) {
      await expect(plannerPage.autoPickStatus).toHaveText(/כבר נמצאים|לא נמצאו/)
    }
  })

  test('low max credits shows localized status without backend English', async ({ plannerPage }) => {
    await plannerPage.autoPickCourses('5')
    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.autoPickStatus).toHaveText(/נוספו|לא נמצאו|כבר נמצאים|מתוך/)
    await expect(plannerPage.autoPickStatus).not.toHaveText(/Partial plan generated|maxCredits/i)
  })
})
