import { expect, test } from './fixtures/test'
import { E2E_PLANNER_SEMESTER } from './helpers/planner'

/**
 * Auto-pick assistant on /plans/new against the live promoted catalog.
 */
test.describe('Planner auto-pick assistant', () => {
  test.beforeEach(async ({ plannerPage }) => {
    await plannerPage.openNewPlanWithSemester(E2E_PLANNER_SEMESTER)
  })

  test('auto-pick adds courses and shows localized status (not backend English)', async ({
    plannerPage,
  }) => {
    await plannerPage.autoPickCourses()

    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.autoPickStatus).toHaveText(/נוספו|לא נמצאו/)
    await expect(plannerPage.autoPickStatus).not.toHaveText(/Partial plan generated/i)

    await expect(
      plannerPage.selectedPanel.locator('span').filter({ hasText: /קורסים|courses/i }),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('second auto-pick shows already-in-list localized message', async ({ plannerPage }) => {
    await plannerPage.autoPickCourses()
    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })

    await plannerPage.autoPickCourses()
    await expect(plannerPage.autoPickStatus).toHaveText(
      /כבר נמצאים ברשימה|already in your list/i,
      { timeout: 15_000 },
    )
  })

  test('low max credits shows partial-fill localized hint', async ({ plannerPage }) => {
    await plannerPage.autoPickCourses('5')
    await expect(plannerPage.autoPickStatus).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.autoPickStatus).toHaveText(/מתוך|of/)
    await expect(plannerPage.autoPickStatus).not.toHaveText(/maxCredits|Partial plan generated/i)
  })
})
