import { expect, test } from '@playwright/test'

test.describe('Transcript ↔ Graduation progress E2E', () => {
  test('adding a completed course updates progress summary and pool counts', async ({ page }) => {
    await page.goto('/progress')
    await expect(page.getByTestId('progress-summary-card')).toBeVisible({ timeout: 20_000 })

    const summaryBefore = await page.getByTestId('progress-summary-card').innerText()

    await page.goto('/transcript')
    await expect(page.getByTestId('transcript-add-form')).toBeVisible({ timeout: 15_000 })

    const courseSearch = page.getByTestId('transcript-course-search')
    await courseSearch.fill('00940345')
    await expect(page.getByText(/00940345/)).toBeVisible({ timeout: 10_000 })

    const semesterCustom = page.getByTestId('transcript-semester-custom')
    await semesterCustom.fill('2020-2')

    await page.getByTestId('transcript-add-button').click()
    await expect(
      page.getByText(/course added to your transcript|הקורס נוסף לגיליון הציונים/i),
    ).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByTestId('transcript-row-00940345')).toBeVisible()

    await page.goto('/progress')
    await expect(page.getByTestId('progress-summary-card')).toBeVisible({ timeout: 20_000 })
    const summaryAfter = await page.getByTestId('progress-summary-card').innerText()
    expect(summaryAfter).not.toEqual(summaryBefore)

    await expect(
      page.getByText(/add completed courses on your transcript|הוסף קורסים שהושלמו/i),
    ).toHaveCount(0)

    const panel = page.getByTestId('elective-pools-panel')
    await expect(panel).toBeVisible({ timeout: 15_000 })
    const poolCard = panel.locator('[data-testid*="elective-ds-pool"]').first()
    if (await poolCard.count()) {
      await poolCard.locator('button[aria-expanded="false"]').first().click()
      await expect(poolCard.getByText('00940345')).toBeVisible({ timeout: 10_000 })
      await expect(poolCard.getByText(/counted|נספר/i)).toBeVisible()
    }
  })
})
