import { expect, test } from '@playwright/test'
import { selectPlannerSemester } from './helpers/planner'

/**
 * Semester planner against the live promoted vault catalog (Docker stack).
 * Requires catalog + course offerings from export → promote pipeline.
 */
test.describe('Planner with live vault catalog', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/plans/new')
    await expect(page.getByRole('heading', { name: /תוכנית חדשה|New plan/i })).toBeVisible()
    await selectPlannerSemester(page)
  })

  test('DNE catalog course 00940345 appears in search and adds to plan', async ({ page }) => {
    const search = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
    await search.fill('00940345')
    await expect(page.getByText(/00940345/).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()
    const selectedPanel = page.getByTestId('selected-courses-panel')
    await expect(selectedPanel.getByText('00940345')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/4.*נק|4.*cred/i).first()).toBeVisible()
  })

  test('vault DNE discrete math schedules on weekly grid', async ({ page }) => {
    const search = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
    await search.fill('00940345')
    await expect(page.getByText(/00940345/).first()).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()

    const lessonBlock = page
      .getByTestId('weekly-schedule-grid')
      .getByRole('button')
      .filter({ hasText: '00940345' })
      .first()
    await expect(lessonBlock).toBeVisible({ timeout: 15_000 })
    await lessonBlock.click()
    await expect(lessonBlock).toHaveClass(/ring-2/)
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
