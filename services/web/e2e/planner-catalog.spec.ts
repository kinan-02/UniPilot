import { expect, test } from './fixtures/test'

/**
 * Semester planner against the live promoted vault catalog (Docker stack).
 * Requires catalog + course offerings from export → promote pipeline.
 */
test.describe('Planner with live vault catalog', () => {
  test.beforeEach(async ({ plannerPage }) => {
    await plannerPage.openNewPlanWithSemester()
  })

  test('DNE catalog course 00940345 appears in search and adds to plan', async ({ plannerPage }) => {
    await plannerPage.searchCourse('00940345')
    await plannerPage.addToPlan()
    await expect(plannerPage.selectedPanel.getByText('00940345')).toBeVisible({ timeout: 10_000 })
    await expect(plannerPage.page.getByText(/4.*נק|4.*cred/i).first()).toBeVisible()
  })

  test('vault DNE discrete math schedules on weekly grid', async ({ plannerPage }) => {
    await plannerPage.searchCourse('00940345')
    await plannerPage.addToPlan()
    await plannerPage.expectLessonVisible('00940345')
    await plannerPage.selectLesson('00940345')
  })

  test('profile loads three DDS degree programs from catalog', async ({ page }) => {
    await page.goto('/profile')
    await expect(page.getByText(/הנדסת נתונים|Data and Information Engineering/i).first()).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByText(/הנדסת תעשייה|Industrial Engineering/i).first()).toBeVisible()
    await expect(page.getByText(/מערכות מידע|Information Systems Engineering/i).first()).toBeVisible()
  })
})
