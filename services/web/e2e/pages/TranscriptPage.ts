import { expect } from '@playwright/test'
import { BasePage } from './BasePage'
import { waitForApiResponse } from '../helpers/api'

export class TranscriptPage extends BasePage {
  readonly addForm = this.page.getByTestId('transcript-add-form')
  readonly courseSearch = this.page.getByTestId('transcript-course-search')

  async gotoTranscript() {
    await this.goto('/transcript')
    await expect(this.addForm).toBeVisible({ timeout: 15_000 })
  }

  async removeCompletedCourseIfPresent(courseNumber: string) {
    await this.gotoTranscript()
    const row = this.page.getByTestId(`transcript-row-${courseNumber}`)
    if (!(await row.isVisible().catch(() => false))) {
      return
    }

    await row.getByRole('button', { name: /remove|הסר/i }).click()
    const deleteResponse = waitForApiResponse(this.page, /\/completed-courses\//, {
      method: 'DELETE',
      status: 200,
    })
    await row.getByRole('button', { name: /^remove$|^הסר$/i }).click()
    await deleteResponse
    await expect(this.page.getByTestId(`transcript-row-${courseNumber}`)).toHaveCount(0)
  }

  async addCompletedCourse(
    courseNumber: string,
    semesterCode: string,
    options?: { grade?: number; creditsEarned?: number },
  ) {
    await this.gotoTranscript()
    await expect(this.courseSearch).toBeVisible({ timeout: 15_000 })
    await expect(this.courseSearch).toBeEnabled()

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

    if (options?.grade != null) {
      await this.addForm.getByLabel(/grade|ציון/i).fill(String(options.grade))
    }
    if (options?.creditsEarned != null) {
      await this.addForm.getByLabel(/credits earned|נק״ז|נק"ז/i).fill(String(options.creditsEarned))
    }

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
