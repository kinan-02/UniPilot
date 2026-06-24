import { expect, test } from './fixtures/test'

test.describe('Transcript ↔ Graduation progress E2E', () => {
  test('adding a completed course updates progress summary and pool counts', async ({
    progressPage,
    transcriptPage,
    page,
  }) => {
    await progressPage.gotoProgress()
    const summaryBefore = await progressPage.summaryCard.innerText()

    await transcriptPage.gotoTranscript()
    await transcriptPage.addCompletedCourse('00940345', '2020-2')

    await progressPage.gotoProgress()
    const summaryAfter = await progressPage.summaryCard.innerText()
    expect(summaryAfter).not.toEqual(summaryBefore)

    await expect(
      page.getByText(/add completed courses on your transcript|הוסף קורסים שהושלמו/i),
    ).toHaveCount(0)

    const poolCard = progressPage.poolsPanel.locator('[data-testid*="elective-ds-pool"]').first()
    if (await poolCard.count()) {
      await poolCard.locator('button[aria-expanded="false"]').first().click()
      await expect(poolCard.getByText('00940345')).toBeVisible({ timeout: 10_000 })
      await expect(poolCard.getByText(/counted|נספר/i)).toBeVisible()
    }
  })
})
