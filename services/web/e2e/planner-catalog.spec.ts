import { expect, test } from '@playwright/test'

/**
 * Semester planner against the live promoted vault catalog (Docker stack).
 * Requires catalog + course offerings from export → promote pipeline.
 */
test.describe('Planner with live vault catalog', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/plans/new')
    await expect(page.getByRole('heading', { name: /תוכנית חדשה|New plan/i })).toBeVisible()
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
      .locator('.planner-workspace')
      .getByRole('button')
      .filter({ hasText: '00940345' })
      .first()
    await expect(lessonBlock).toBeVisible({ timeout: 15_000 })
    await lessonBlock.click()
    await expect(page.getByText(/Lecture|הרצאה/i).first()).toBeVisible({ timeout: 10_000 })
  })

  test('profile loads three DDS degree programs from catalog', async ({ page }) => {
    await page.goto('/profile')
    const degreeSelect = page.getByLabel(/Degree program|תוכנית לימודים/i)
    await expect(degreeSelect.locator('option')).not.toHaveCount(1, { timeout: 15_000 })
    await expect(degreeSelect.locator('option')).toHaveCount(4)
    await expect(degreeSelect.locator('option', { hasText: /הנדסת נתונים|Data and Information/i })).toHaveCount(1)
    await expect(degreeSelect.locator('option', { hasText: /הנדסת תעשייה|Industrial Engineering/i })).toHaveCount(1)
    await expect(degreeSelect.locator('option', { hasText: /מערכות מידע|Information Systems/i })).toHaveCount(1)
  })
})
