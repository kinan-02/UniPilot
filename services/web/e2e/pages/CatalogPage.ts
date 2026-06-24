import { expect } from '@playwright/test'
import { waitForApiResponse } from '../helpers/api'
import { BasePage } from './BasePage'

export class CatalogPage extends BasePage {
  readonly searchInput = this.page.getByTestId('catalog-search-input')

  async gotoCatalog() {
    await this.goto('/catalog')
    await expect(this.heading(/קטלוג קורסים|Course catalog/i)).toBeVisible()
  }

  async search(courseNumber: string) {
    const responsePromise = waitForApiResponse(this.page, /\/catalog\/courses/, { timeout: 20_000 })
    await this.searchInput.fill(courseNumber)
    await responsePromise.catch(() => undefined)
    await expect(this.page.getByText(new RegExp(courseNumber)).first()).toBeVisible({ timeout: 15_000 })
  }

  async openCourse(courseNumber: string) {
    const row = this.page.getByTestId(`catalog-course-row-${courseNumber}`)
    if (await row.count()) {
      await row.click()
    } else {
      await this.page.getByRole('button', { name: new RegExp(courseNumber) }).first().click()
    }
    await expect(this.page.getByText(/נק״ז|credits/i).first()).toBeVisible({ timeout: 10_000 })
  }
}
