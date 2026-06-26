import { expect, test } from './fixtures/test'
import { E2E_DNE_ELECTIVE_COURSE } from './helpers/planner'

test.describe('Transcript ↔ Graduation progress E2E', () => {
  test('adding a completed course updates progress summary and pool counts', async ({
    progressPage,
    transcriptPage,
    page,
  }) => {
    await progressPage.gotoProgress()
    const summaryBefore = await progressPage.summaryCard.innerText()

    await transcriptPage.gotoTranscript()
    await transcriptPage.addCompletedCourse(E2E_DNE_ELECTIVE_COURSE, '2020-2')

    const progressRefresh = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress') && response.status() === 200,
    )
    await progressPage.gotoProgress()
    await progressRefresh
    const summaryAfter = await progressPage.summaryCard.innerText()
    expect(summaryAfter).not.toEqual(summaryBefore)

    await expect(
      page.getByText(/add completed courses on your transcript|הוסף קורסים שהושלמו/i),
    ).toHaveCount(0)

    const poolCard = progressPage.poolsPanel.locator('[data-testid*="elective-ds-pool"]').first()
    await expect(poolCard).toBeVisible({ timeout: 15_000 })
    const collapsedToggle = poolCard.locator('button[aria-expanded="false"]').first()
    if (await collapsedToggle.count()) {
      await collapsedToggle.click()
    }
    const courseLink = poolCard.getByRole('link', { name: E2E_DNE_ELECTIVE_COURSE })
    await courseLink.scrollIntoViewIfNeeded()
    await expect(courseLink).toBeVisible({ timeout: 10_000 })
    await expect(poolCard.getByText(/counted|נספר/i).first()).toBeVisible()
  })
})
