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

test.describe('Graduation progress — transcript vs degree credits', () => {
  test('shows ineligible transcript credits for out-of-pool course', async ({
    progressPage,
    transcriptPage,
    page,
  }) => {
    await transcriptPage.removeCompletedCourseIfPresent(E2E_OUT_OF_POOL_COURSE)
    await transcriptPage.addCompletedCourse(E2E_OUT_OF_POOL_COURSE, '2020-2')

    const progressResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress') && response.status() === 200,
    )
    await progressPage.gotoProgress()
    const response = await progressResponse
    const body = (await response.json()) as {
      data?: {
        graduationProgress?: {
          completedCredits?: number
          degreeAppliedCredits?: number
          transcriptCreditsTotal?: number
          ineligibleCredits?: Array<{ courseNumber?: string }>
        }
      }
    }
    const progress = body.data?.graduationProgress
    const transcriptTotal = progress?.transcriptCreditsTotal ?? 0
    const degreeApplied = progress?.degreeAppliedCredits ?? progress?.completedCredits ?? 0
    expect(transcriptTotal).toBeGreaterThan(degreeApplied)
    expect(progress?.ineligibleCredits?.some((row) => row.courseNumber === E2E_OUT_OF_POOL_COURSE)).toBe(
      true,
    )

    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')

    await expect(
      progressPage.summaryCard.getByText(/recorded on your transcript|רשומות בגיליון הציונים/i),
    ).toBeVisible()
    await expect(progressPage.attentionPanel).toBeVisible({ timeout: 15_000 })
    await progressPage.attentionPanel.locator('button[aria-expanded="false"]').first().click()
    await expect(
      progressPage.attentionPanel.getByText(
        /Transcript credits not applied|נק״ז שלא נספרו|נק"ז שלא נספרו/i,
      ),
    ).toBeVisible()
  })

  test('failed latest retake excludes previously passing course from degree credits', async ({
    progressPage,
    transcriptPage,
    page,
  }) => {
    await transcriptPage.removeCompletedCourseIfPresent(E2E_DNE_ELECTIVE_COURSE)
    await transcriptPage.addCompletedCourse(E2E_DNE_ELECTIVE_COURSE, '2020-2', { grade: 85 })

    const progressAfterPass = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress') && response.status() === 200,
    )
    await progressPage.gotoProgress()
    const passResponse = await progressAfterPass
    const passBody = (await passResponse.json()) as {
      data?: {
        graduationProgress?: {
          completedCredits?: number
          degreeAppliedCredits?: number
        }
      }
    }
    const passProgress = passBody.data?.graduationProgress
    const creditsAfterPass =
      passProgress?.degreeAppliedCredits ?? passProgress?.completedCredits ?? 0
    expect(creditsAfterPass).toBeGreaterThan(0)

    await transcriptPage.addCompletedCourse(E2E_DNE_ELECTIVE_COURSE, '2021-1', {
      grade: 40,
      creditsEarned: 0,
    })

    const progressAfterFail = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress') && response.status() === 200,
    )
    await progressPage.gotoProgress()
    const failResponse = await progressAfterFail
    const failBody = (await failResponse.json()) as {
      data?: {
        graduationProgress?: {
          completedCredits?: number
          degreeAppliedCredits?: number
          ineligibleCredits?: Array<{ courseNumber?: string; reason?: string }>
        }
      }
    }
    const failProgress = failBody.data?.graduationProgress
    const creditsAfterFail =
      failProgress?.degreeAppliedCredits ?? failProgress?.completedCredits ?? 0
    expect(creditsAfterFail).toBeLessThan(creditsAfterPass)
  })
})

