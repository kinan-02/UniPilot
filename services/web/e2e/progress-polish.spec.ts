import { expect, test } from './fixtures/test'
import { E2E_DNE_ELECTIVE_COURSE, E2E_OUT_OF_POOL_COURSE } from './helpers/planner'

test.describe('Graduation progress — attention and deep links', () => {
  test('expands and collapses attention panel when many items need attention', async ({
    progressPage,
    page,
  }) => {
    await progressPage.gotoProgress()
    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')

    await expect(progressPage.attentionPanel).toBeVisible({ timeout: 15_000 })
    const toggle = progressPage.attentionPanel.locator('button[aria-expanded]').first()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(
      progressPage.attentionPanel.getByText(/Remaining mandatory courses|קורסי חובה שנותרו/i),
    ).toBeVisible()

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  test('summary attention link scrolls to the attention panel', async ({ progressPage, page }) => {
    await progressPage.gotoProgress()
    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')

    await expect(progressPage.attentionLink).toBeVisible({ timeout: 15_000 })
    await progressPage.attentionLink.click()
    await expect(progressPage.attentionPanel).toBeInViewport()
  })

  test('reports invalid pool deep link', async ({ progressPage, page }) => {
    await progressPage.gotoProgressWithPool('nonexistent-pool-id-xyz')
    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')
    await expect(progressPage.poolsPanel).toBeVisible({ timeout: 15_000 })

    const missingMessage = page
      .getByTestId('progress-deep-link-pool-missing')
      .or(page.getByText(/was not found for your track|לא נמצאה למסלול שלך/i))
    await expect(missingMessage).toBeVisible({ timeout: 15_000 })
    await expect(missingMessage).toContainText('nonexistent-pool-id-xyz')
  })
})

test.describe('Graduation progress — transcript integration', () => {
  test('progress page loads after recording a catalog course on the transcript', async ({
    progressPage,
    transcriptPage,
  }) => {
    await transcriptPage.removeCompletedCourseIfPresent(E2E_DNE_ELECTIVE_COURSE)
    await transcriptPage.addCompletedCourse(E2E_DNE_ELECTIVE_COURSE, '2020-2', { grade: 85 })
    await progressPage.gotoProgress()
    await expect(progressPage.summaryCard).toBeVisible({ timeout: 15_000 })
    await expect(progressPage.poolsPanel).toBeVisible({ timeout: 15_000 })
  })

  test('progress page loads after recording an out-of-pool catalog course', async ({
    progressPage,
    transcriptPage,
  }) => {
    await transcriptPage.removeCompletedCourseIfPresent(E2E_OUT_OF_POOL_COURSE)
    await transcriptPage.addCompletedCourse(E2E_OUT_OF_POOL_COURSE, '2020-2')
    await progressPage.gotoProgress()
    await expect(progressPage.summaryCard).toBeVisible({ timeout: 15_000 })
  })
})
