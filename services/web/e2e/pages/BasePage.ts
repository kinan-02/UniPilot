import type { Locator, Page } from '@playwright/test'

export abstract class BasePage {
  constructor(readonly page: Page) {}

  async goto(path: string) {
    await this.page.goto(path)
  }

  protected heading(name: RegExp): Locator {
    return this.page.getByRole('heading', { name })
  }

  async switchLanguage(locale: 'en' | 'he') {
    await this.page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption(locale)
  }
}
