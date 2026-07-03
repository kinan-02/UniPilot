import { expect, test } from './fixtures/test'
import {
  E2E_MAS_COURSE,
  E2E_MAS_SECOND_COURSE,
  escapeRegExp,
  MAS_GOALS,
  MAS_SESSION_TIMEOUT_MS,
} from './helpers/mas'
import { AgentSessionsPage } from './pages/AgentSessionsPage'

/**
 * Full user journeys: prompt on /agents → MAS negotiation → visible output → approve → apply → planner.
 * Requires Docker stack with api + mas + web (PLAYWRIGHT_BASE_URL=http://localhost:3000).
 *
 * Run: npm run test:e2e -- --project=mas-user-journey
 */
test.describe.serial('MAS user journey @critical', () => {
  test.setTimeout(MAS_SESSION_TIMEOUT_MS + 60_000)

  test('student prompts explicit course and receives plan through to semester planner', async ({
    page,
  }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/')
    await agents.gotoAgents()

    await agents.submitGoal(MAS_GOALS.explicitCourseEn())
    await agents.waitForSessionCompleted()

    await agents.expectRecommendedCourse(E2E_MAS_COURSE)
    await agents.expectScheduleSection()
    await agents.expectUtilityScore()
    await agents.expectTranscriptSection()

    await agents.approveRecommendation()
    await agents.applyToSemesterPlan()
    await agents.expectCourseOnPlanner(E2E_MAS_COURSE)
  })

  test('student uses suggested prompt chip and completes session', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    const chip = page.getByTestId('agent-sessions-suggestions').getByRole('button', {
      name: new RegExp(E2E_MAS_COURSE),
    })
    await expect(chip).toBeVisible()
    const createResponse = page.waitForResponse(
      (response) => response.url().includes('/agent/sessions') && response.status() === 202,
    )
    await chip.click()
    const response = await createResponse
    const body = (await response.json()) as { data?: { session?: { id?: string } } }
    agents.setActiveSessionId(body.data?.session?.id ?? null)

    await agents.waitForSessionCompleted()
    await agents.expectRecommendedCourse(E2E_MAS_COURSE)
  })

  test('student enables avoid-Friday preference and still gets a completed plan', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.avoidFridayCheckbox.check()
    await agents.submitGoal(MAS_GOALS.explicitCourseEn())
    await agents.waitForSessionCompleted()

    await agents.expectRecommendedCourse(E2E_MAS_COURSE)
    await agents.expectTranscriptSection()
  })

  test('student sees session in history after completion', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    const goal = `${MAS_GOALS.explicitCourseEn(E2E_MAS_SECOND_COURSE)} (e2e-${Date.now()})`
    await page.goto('/agents')

    await agents.submitGoal(goal)
    await agents.waitForSessionCompleted()

    await expect(page.getByText(/Recent sessions|סשנים אחרונים/i)).toBeVisible()
    await expect(page.getByRole('button', { name: new RegExp(escapeRegExp(goal)) }).first()).toBeVisible()
  })

  test('apply stays disabled until student approves recommendation', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.submitGoal(MAS_GOALS.explicitCourseEn())
    await agents.waitForSessionCompleted()

    await expect(agents.applyButton).toBeDisabled()
    await expect(
      page.getByText(/Approve the recommendation|יש לאשר את ההמלצה/i),
    ).toBeVisible()
  })

  test('Hebrew goal produces completed session with visible output', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.submitGoal(MAS_GOALS.explicitCourseHe())
    await agents.waitForSessionCompleted()

    await agents.expectRecommendedCourse(E2E_MAS_COURSE)
    await agents.expectScheduleSection()
  })

  test('multi-course goal shows negotiation output with at least one course', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.submitGoal(MAS_GOALS.multiCourseEn())
    await agents.waitForSessionCompleted()

    await agents.expectRecommendedCourse(E2E_MAS_COURSE)
    await agents.expectRecommendedCourse(E2E_MAS_SECOND_COURSE)
    await agents.expectTranscriptSection()
  })

  test('student receives regulations answer for policy Q&A goal', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.submitGoal(MAS_GOALS.policyQaEn)
    await agents.waitForPolicySessionCompleted()
    await agents.expectPolicyAnswer()
  })

  test('Hebrew policy Q&A goal shows regulations answer panel', async ({ page }) => {
    const agents = new AgentSessionsPage(page)
    await page.goto('/agents')

    await agents.submitGoal(MAS_GOALS.policyQaHe)
    await agents.waitForPolicySessionCompleted()
    await agents.expectPolicyAnswer()
  })
})
