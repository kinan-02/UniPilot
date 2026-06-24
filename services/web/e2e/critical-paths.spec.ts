import { expect, test } from './fixtures/test'
import { completeOnboarding, registerUser } from './helpers/onboarding'
import { E2E_KNOWN_COURSE, E2E_PLANNER_SEMESTER } from './helpers/planner'

/**
 * Cross-feature critical path exercised as one journey on a fresh user.
 * Tagged for selective runs: npm run test:e2e:critical
 */
test.describe('Student critical path @critical', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('catalog → planner → transcript → progress integration', async ({
    catalogPage,
    plannerPage,
    transcriptPage,
    progressPage,
    page,
  }) => {
    const courseNumber = E2E_KNOWN_COURSE

    await registerUser(page, `critical-${Date.now()}@example.com`)
    await completeOnboarding(page)

    await catalogPage.gotoCatalog()
    await catalogPage.search(courseNumber)
    await catalogPage.openCourse(courseNumber)
    await expect(page.getByText(/נק״ז|credits/i).first()).toBeVisible()

    await plannerPage.openNewPlanWithSemester(E2E_PLANNER_SEMESTER)
    await plannerPage.searchCourse(courseNumber)
    await plannerPage.addToPlan()
    await expect(plannerPage.selectedPanel.getByText(courseNumber)).toBeVisible()
    await plannerPage.expectLessonVisible(courseNumber)
    await plannerPage.selectLesson(courseNumber)
    await plannerPage.savePlan()

    await progressPage.gotoProgress()
    const summaryBefore = await progressPage.summaryCard.innerText()

    await transcriptPage.gotoTranscript()
    await transcriptPage.addCompletedCourse(courseNumber, '2020-2')

    const progressRefresh = page.waitForResponse(
      (response) => response.url().includes('/graduation-progress') && response.status() === 200,
    )
    await progressPage.gotoProgress()
    await progressRefresh
    const summaryAfter = await progressPage.summaryCard.innerText()
    expect(summaryAfter).not.toEqual(summaryBefore)
  })
})
