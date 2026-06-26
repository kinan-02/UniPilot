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
    const catalogSearch = this.page.waitForResponse(
      (response) =>
        response.url().includes('/catalog/courses') &&
        response.request().method() === 'GET' &&
        response.status() === 200,
    )

    await this.courseSearch.fill(courseNumber)
    await catalogSearch
    await expect(this.addForm.getByText(new RegExp(courseNumber))).toBeVisible({ timeout: 10_000 })

    const suggestion = this.addForm
      .getByRole('button')
      .filter({ hasText: new RegExp(courseNumber) })
      .first()
    if (await suggestion.isVisible().catch(() => false)) {
      await suggestion.click()
    }

    await this.page.getByTestId('transcript-semester-custom').fill(semesterCode)
    const createResponse = this.page.waitForResponse(
      (response) =>
        response.url().includes('/completed-courses') &&
        response.request().method() === 'POST' &&
        response.status() === 201,
    )
    await this.page.getByTestId('transcript-add-button').click()
    await createResponse

    await expect(
      this.page.getByText(/course added to your transcript|הקורס נוסף לגיליון הציונים/i),
    ).toBeVisible({ timeout: 15_000 })
    await expect(this.page.getByTestId(`transcript-row-${courseNumber}`)).toBeVisible()
  }
}
