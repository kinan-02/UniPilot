import { expect } from '@playwright/test'
import { MAS_POLICY_SESSION_TIMEOUT_MS, MAS_SESSION_TIMEOUT_MS } from '../helpers/mas'
import { BasePage } from './BasePage'

export class AgentSessionsPage extends BasePage {
  readonly pageRoot = this.page.getByTestId('agent-sessions-page')
  readonly goalInput = this.page.getByTestId('agent-sessions-goal-input')
  readonly startButton = this.page.getByTestId('agent-sessions-start')
  readonly avoidFridayCheckbox = this.page.getByTestId('agent-sessions-avoid-friday')
  readonly approveButton = this.page.getByTestId('agent-sessions-approve')
  readonly applyButton = this.page.getByTestId('agent-sessions-apply')
  readonly openPlannerLink = this.page.getByTestId('agent-sessions-open-planner')

  readonly activePanel = this.page.getByTestId('agent-sessions-active-panel')
  readonly activeStatus = this.page.getByTestId('agent-sessions-active-status')
  readonly policyAnswerPanel = this.page.getByTestId('agent-sessions-policy-answer')

  private activeSessionId: string | null = null

  setActiveSessionId(sessionId: string | null) {
    this.activeSessionId = sessionId
  }

  async gotoAgents() {
    await this.page.getByRole('link', { name: /מתכנן סוכנים|Agent planner/i }).click()
    await expect(this.pageRoot).toBeVisible({ timeout: 15_000 })
  }

  async submitGoal(goal: string) {
    await this.goalInput.fill(goal)
    const createResponse = this.page.waitForResponse(
      (response) => response.url().includes('/agent/sessions') && response.status() === 202,
      { timeout: 30_000 },
    )
    await this.startButton.click()
    const response = await createResponse
    const body = (await response.json()) as {
      data?: { session?: { id?: string } }
    }
    this.activeSessionId = body.data?.session?.id ?? null
  }

  async waitForSessionCompleted() {
    if (!this.activeSessionId) {
      throw new Error('No active MAS session id — call submitGoal() first.')
    }

    await expect
      .poll(
        async () => {
          const response = await this.page.request.get(
            `/api/agent/sessions/${this.activeSessionId}`,
          )
          if (!response.ok()) return null
          const body = (await response.json()) as {
            data?: {
              session?: {
                status?: string
                finalDecision?: { course_ids?: string[] }
              }
            }
          }
          const session = body.data?.session
          if (!session) return null
          if (session.status !== 'completed') return null
          const courseIds = session.finalDecision?.course_ids ?? []
          return courseIds.length > 0 ? courseIds : null
        },
        { timeout: MAS_SESSION_TIMEOUT_MS },
      )
      .not.toBeNull()

    await expect(this.approveButton).toBeVisible({ timeout: 15_000 })
    await expect(this.page.getByText(/Agents are negotiating|הסוכנים מנהלים משא ומתן/i)).toBeHidden({
      timeout: 5_000,
    })
  }

  async waitForPolicySessionCompleted() {
    if (!this.activeSessionId) {
      throw new Error('No active MAS session id — call submitGoal() first.')
    }

    await expect
      .poll(
        async () => {
          const response = await this.page.request.get(
            `/api/agent/sessions/${this.activeSessionId}`,
          )
          if (!response.ok()) return false
          const body = (await response.json()) as {
            data?: {
              session?: {
                status?: string
                finalDecision?: {
                  vertical?: string
                  answer?: string
                }
              }
            }
          }
          const session = body.data?.session
          const decision = session?.finalDecision
          const apiReady =
            session?.status === 'completed' &&
            decision?.vertical === 'policy_qa' &&
            typeof decision.answer === 'string' &&
            decision.answer.length > 0
          if (!apiReady) return false
          return this.policyAnswerPanel.isVisible()
        },
        { timeout: MAS_POLICY_SESSION_TIMEOUT_MS },
      )
      .toBe(true)

    await expect(this.page.getByText(/Agents are negotiating|הסוכנים מנהלים משא ומתן/i)).toBeHidden({
      timeout: 5_000,
    })
  }

  async expectPolicyAnswer() {
    await expect(this.policyAnswerPanel).toBeVisible({ timeout: 15_000 })
    await expect(
      this.policyAnswerPanel.getByText(/Regulations answer|תשובת תקנון/i),
    ).toBeVisible()
    await expect(this.approveButton).toHaveCount(0)
    await expect(this.applyButton).toHaveCount(0)
    await this.expectTranscriptSection()
  }

  async waitForSessionTerminal() {
    await expect(
      this.approveButton.or(this.page.getByText(/^failed$/)).or(this.activeStatus),
    ).toBeVisible({
      timeout: MAS_SESSION_TIMEOUT_MS,
    })
  }

  async expectRecommendedCourse(courseNumber: string) {
    await expect(
      this.page.getByRole('link', { name: courseNumber }).first(),
    ).toBeVisible({ timeout: 15_000 })
  }

  async expectScheduleSection() {
    await expect(
      this.activePanel.getByText(/Weekly schedule|מערכת שבועית/i),
    ).toBeVisible({ timeout: 15_000 })
  }

  async expectTranscriptSection() {
    await expect(
      this.activePanel.getByText(/Negotiation transcript|תמליל משא ומתן/i),
    ).toBeVisible({ timeout: 15_000 })
  }

  async expectUtilityScore() {
    await expect(
      this.activePanel.getByText(/Overall utility|ציון כולל/i),
    ).toBeVisible({ timeout: 15_000 })
  }

  async approveRecommendation() {
    const approveResponse = this.page.waitForResponse(
      (response) => response.url().includes('/approve') && response.status() === 200,
      { timeout: 30_000 },
    )
    await this.approveButton.click()
    await approveResponse
    await expect(this.page.getByText(/Approved|אושר/i)).toBeVisible({ timeout: 10_000 })
  }

  async applyToSemesterPlan() {
    const applyResponse = this.page.waitForResponse(
      (response) => response.url().includes('/apply') && response.status() === 200,
      { timeout: 60_000 },
    )
    await this.applyButton.click()
    await applyResponse
    await expect(this.page).toHaveURL(/\/plans\/[^/]+\/edit/, { timeout: 30_000 })
  }

  async expectCourseOnPlanner(courseNumber: string) {
    await expect(this.page.getByTestId('selected-courses-panel').getByText(courseNumber)).toBeVisible({
      timeout: 30_000,
    })
  }
}
