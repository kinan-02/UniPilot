import { expect } from '@playwright/test'
import { BasePage } from './BasePage'

export class TranscriptPage extends BasePage {
  readonly addForm = this.page.getByTestId('transcript-add-form')
  readonly courseSearch = this.page.getByTestId('transcript-course-search')

  async gotoTranscript() {
    await this.goto('/transcript')
    await expect(this.addForm).toBeVisible({ timeout: 15_000 })
  }

  async addCompletedCourse(courseNumber: string, semesterCode: string) {
    await this.courseSearch.fill(courseNumber)
    await expect(this.page.getByText(new RegExp(courseNumber))).toBeVisible({ timeout: 10_000 })
    await this.page.getByTestId('transcript-semester-custom').fill(semesterCode)
    await this.page.getByTestId('transcript-add-button').click()
    await expect(
      this.page.getByText(/course added to your transcript|הקורס נוסף לגיליון הציונים/i),
    ).toBeVisible({ timeout: 15_000 })
    await expect(this.page.getByTestId(`transcript-row-${courseNumber}`)).toBeVisible()
  }
}
