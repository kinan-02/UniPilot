import { expect, test } from './fixtures/test'

/** DNE data-science elective pool course present in promoted catalog_rules explorer lists. */
const DNE_ELECTIVE_DS_COURSE = '00960200'

test.describe('Transcript ↔ Graduation progress E2E', () => {
  test('adding a completed course updates progress summary and pool counts', async ({
    progressPage,
    transcriptPage,
    page,
  }) => {
    await progressPage.gotoProgress()
    const summaryBefore = await progressPage.summaryCard.innerText()

    await transcriptPage.gotoTranscript()
    await transcriptPage.addCompletedCourse(DNE_ELECTIVE_DS_COURSE, '2020-2')

    await progressPage.gotoProgress()
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
    const courseLink = poolCard.getByRole('link', { name: DNE_ELECTIVE_DS_COURSE })
    await courseLink.scrollIntoViewIfNeeded()
    await expect(courseLink).toBeVisible({ timeout: 10_000 })
    await expect(poolCard.getByTestId('virtual-pool-course-list').getByText(/counted|נספר/i)).toBeVisible()
  })
})
