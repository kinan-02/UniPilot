import { expect, type Locator } from '@playwright/test'
import { E2E_PLANNER_SEMESTER } from '../helpers/planner'
import { BasePage } from './BasePage'

export class PlannerPage extends BasePage {
  readonly searchInput = this.page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
  readonly weeklyGrid = this.page.getByTestId('weekly-schedule-grid')
  readonly selectedPanel = this.page.getByTestId('selected-courses-panel')
  readonly maybePanel = this.page.getByTestId('maybe-courses-panel')

  async gotoNewPlan() {
    await this.goto('/plans/new')
    await expect(this.heading(/תוכנית חדשה|New plan/i)).toBeVisible()
  }

  async selectSemester(semesterCode = E2E_PLANNER_SEMESTER) {
    await this.page.locator('#planner-semester').selectOption(semesterCode)
  }

  async openNewPlanWithSemester(semesterCode = E2E_PLANNER_SEMESTER) {
    await this.gotoNewPlan()
    await this.selectSemester(semesterCode)
  }

  async searchCourse(courseNumber: string) {
    await this.searchInput.fill(courseNumber)
    await expect(this.page.getByText(new RegExp(courseNumber)).first()).toBeVisible({ timeout: 15_000 })
  }

  async addToPlan() {
    await this.page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()
  }

  async addToMaybe() {
    await this.page.getByRole('button', { name: /הוסף לאולי|Add to maybe/i }).click()
  }

  lessonBlock(courseNumber: string): Locator {
    return this.weeklyGrid.getByRole('button').filter({ hasText: courseNumber }).first()
  }

  async expectLessonVisible(courseNumber: string) {
    await expect(this.lessonBlock(courseNumber)).toBeVisible({ timeout: 15_000 })
  }

  async selectLesson(courseNumber: string) {
    const block = this.lessonBlock(courseNumber)
    await block.click()
    await expect(block).toHaveClass(/ring-2/)
  }

  async savePlan() {
    await this.page.getByRole('button', { name: /שמירת תוכנית|Save plan/i }).click()
    await expect(this.page).toHaveURL(/\/plans\/[^/]+\/edit/, { timeout: 20_000 })
  }

  get autoAssistPanel() {
    return this.page
      .getByTestId('planner-auto-assist-panel')
      .or(this.page.getByRole('heading', { name: /עוזר תכנון|Planning assistant/i }).locator('..'))
  }

  get autoPickButton() {
    return this.page
      .getByTestId('planner-auto-pick-button')
      .or(this.page.getByRole('button', { name: /בחירת קורסים אוטומטית|Auto-pick courses/i }))
  }

  get autoPickStatus() {
    return this.page.getByTestId('planner-auto-pick-status')
  }

  async setMaxCredits(value: string) {
    const input = this.page.getByRole('spinbutton', { name: /מקסימום נק״ז|Max credits/i })
    await input.fill(value)
  }

  async autoPickCourses(maxCredits?: string) {
    await expect(this.autoPickButton).toBeVisible({ timeout: 15_000 })
    if (maxCredits !== undefined) {
      await this.setMaxCredits(maxCredits)
    }
    const suggestResponse = this.page.waitForResponse(
      (response) =>
        response.url().includes('/semester-plans/suggest-courses') && response.status() === 200,
      { timeout: 30_000 },
    )
    await this.autoPickButton.click()
    await suggestResponse
  }

  async countSelectedCourses(): Promise<number> {
    const badge = this.selectedPanel.getByText(/\d+\s*(קורסים|courses)/i)
    if (!(await badge.isVisible().catch(() => false))) return 0
    const text = (await badge.textContent()) ?? ''
    const match = text.match(/(\d+)/)
    return match ? Number(match[1]) : 0
  }
}
