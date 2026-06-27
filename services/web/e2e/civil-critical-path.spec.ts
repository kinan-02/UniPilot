import { expect, test } from '@playwright/test'
import { completeOnboarding, registerUser } from './helpers/onboarding'
import { E2E_PLANNER_SEMESTER } from './helpers/planner'

/**
 * Non-DDS faculty critical path (civil structures track).
 * register → login → onboarding → graduation-progress → semester-plan generate
 */
test.describe('Civil faculty critical path @critical', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('onboarding yields progress buckets/pools and a generated semester plan', async ({ page }) => {
    const email = `civil-critical-${Date.now()}@example.com`
    await registerUser(page, email)
    await completeOnboarding(page, {
      facultyTestId: 'faculty-faculty-civil-environmental-engineering',
      primaryProgramLabel:
        /מסלול הנדסה אזרחית.*מבנים|Structures Track|Civil Engineering.*Structures/i,
    })

    const progressResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress') &&
        !response.url().includes('curriculum-graph') &&
        response.request().method() === 'GET' &&
        response.status() === 200,
    )
    const graphResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/graduation-progress/curriculum-graph') &&
        response.request().method() === 'GET' &&
        response.status() === 200,
    )

    await page.goto('/progress')
    const progressPayload = (await (await progressResponse).json()) as {
      data: { graduationProgress: { requirementProgress: unknown[] } }
    }
    const graphPayload = (await (await graphResponse).json()) as {
      data: {
        curriculumGraph: { semesterLanes: unknown[]; electiveBuckets: unknown[] }
      }
    }

    expect(progressPayload.data.graduationProgress.requirementProgress.length).toBeGreaterThan(0)
    expect(graphPayload.data.curriculumGraph.semesterLanes.length).toBeGreaterThan(0)
    expect(graphPayload.data.curriculumGraph.electiveBuckets.length).toBeGreaterThan(0)
    await expect(page.getByTestId('elective-pools-panel')).toBeVisible({ timeout: 15_000 })

    const generateResponse = await page.request.post('/api/semester-plans/generate', {
      data: { semesterCode: E2E_PLANNER_SEMESTER, maxCredits: 12 },
    })
    expect(generateResponse.ok()).toBeTruthy()
    const generatePayload = (await generateResponse.json()) as {
      data: {
        semesterPlan: {
          semesters: Array<{ plannedCourses: unknown[] }>
          explanation: { partialPlan?: boolean }
        }
      }
    }
    const planned = generatePayload.data.semesterPlan.semesters[0]?.plannedCourses ?? []
    expect(planned.length).toBeGreaterThan(0)
    expect(generatePayload.data.semesterPlan.explanation.partialPlan).not.toBe(true)
  })
})
