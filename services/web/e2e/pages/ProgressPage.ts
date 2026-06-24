import { expect } from '@playwright/test'
import { BasePage } from './BasePage'

export class ProgressPage extends BasePage {
  readonly summaryCard = this.page.getByTestId('progress-summary-card')
  readonly poolsPanel = this.page.getByTestId('elective-pools-panel')

  async gotoProgress() {
    await this.goto('/progress')
    await expect(this.summaryCard).toBeVisible({ timeout: 20_000 })
  }

  async expectCoreSections() {
    await expect(this.heading(/התקדמות לתואר|Graduation progress/i)).toBeVisible()
    await expect(this.page.getByTestId('curriculum-graph-section')).toBeVisible({ timeout: 15_000 })
    await expect(this.poolsPanel).toBeVisible({ timeout: 15_000 })
  }
}
