import { expect, test } from './fixtures/test'

import { E2E_KNOWN_COURSE } from './helpers/planner'

test.describe('Catalog', () => {
  test('search returns results and opens course detail', async ({ catalogPage, page }) => {
    await catalogPage.gotoCatalog()
    await catalogPage.search(E2E_KNOWN_COURSE)
    await catalogPage.openCourse(E2E_KNOWN_COURSE)
    await expect(page.getByText(/נק״ז|credits/i).first()).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('Semester planner workspace', () => {
  test.beforeEach(async ({ plannerPage }) => {
    await plannerPage.openNewPlanWithSemester()
  })

  test('maybe courses: add, grid preview, move between lists', async ({ plannerPage }) => {
    await plannerPage.searchCourse(E2E_KNOWN_COURSE)
    await plannerPage.addToMaybe()
    await expect(plannerPage.maybePanel.getByText(E2E_KNOWN_COURSE)).toBeVisible({ timeout: 10_000 })

    const maybeGridBlock = plannerPage.page
      .locator('.planner-workspace')
      .getByRole('button')
      .filter({ hasText: E2E_KNOWN_COURSE })
      .first()
    await expect(maybeGridBlock).toBeVisible({ timeout: 15_000 })

    await plannerPage.maybePanel
      .locator('button[title="העבר לנבחרים"], button[title="Move to selected"]')
      .click()
    await expect(plannerPage.selectedPanel.getByText(E2E_KNOWN_COURSE)).toBeVisible({ timeout: 10_000 })

    await plannerPage.selectedPanel
      .locator('button[title="העבר לאולי"], button[title="Move to maybe"]')
      .click()
    await expect(plannerPage.maybePanel.getByText(E2E_KNOWN_COURSE)).toBeVisible({ timeout: 10_000 })
  })

  test('CheeseFork-style flow: semester, search, add course, grid lesson selection, save', async ({
    plannerPage,
  }) => {
    await expect(
      plannerPage.page.getByText(/חיפוש קורסים לסמסטר|Search courses for semester/i),
    ).toBeVisible()
    await expect(plannerPage.page.getByText(/לוח שבועי|Weekly schedule/i).first()).toBeVisible()

    await plannerPage.searchCourse(E2E_KNOWN_COURSE)
    await plannerPage.addToPlan()
    await expect(plannerPage.page.getByText(/4.*נק|4.*cred/i).first()).toBeVisible()
    await plannerPage.expectLessonVisible(E2E_KNOWN_COURSE)
    await plannerPage.selectLesson(E2E_KNOWN_COURSE)
    await plannerPage.savePlan()
  })

  test('saved plan: move selected to maybe persists after reload', async ({ plannerPage }) => {
    await plannerPage.searchCourse(E2E_KNOWN_COURSE)
    await plannerPage.addToPlan()
    await expect(plannerPage.selectedPanel.getByText(E2E_KNOWN_COURSE)).toBeVisible({ timeout: 10_000 })

    await plannerPage.savePlan()

    const persistResponse = plannerPage.page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' &&
        /\/semester-plans\/[^/]+$/.test(response.url()) &&
        response.status() === 200,
    )
    await plannerPage.selectedPanel
      .locator('button[title="העבר לאולי"], button[title="Move to maybe"]')
      .click()
    await expect(plannerPage.maybePanel.getByText(E2E_KNOWN_COURSE)).toBeVisible({ timeout: 10_000 })
    await persistResponse

    await plannerPage.page.reload()
    await expect(plannerPage.heading(/עריכת תוכנית|Edit plan/i)).toBeVisible({ timeout: 15_000 })
    await expect(plannerPage.page.getByTestId('maybe-courses-panel').getByText(E2E_KNOWN_COURSE)).toBeVisible({
      timeout: 15_000,
    })
    await expect(plannerPage.selectedPanel.getByText(E2E_KNOWN_COURSE)).toHaveCount(0)
  })

  test('plans list links to new planner route', async ({ page }) => {
    await page.goto('/plans')
    await page.getByRole('button', { name: /תוכנית חדשה|New plan/i }).click()
    await expect(page).toHaveURL(/\/plans\/new/)
    await expect(page.getByRole('heading', { name: /תוכנית חדשה|New plan/i })).toBeVisible()
  })
})

test.describe('i18n', () => {
  test('switches to English on plans page', async ({ page }) => {
    await page.goto('/plans')
    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')
    await expect(page.getByRole('heading', { name: /Semester plans/i })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  })
})

test.describe('Protected routes', () => {
  test('guest without session is redirected to login', async ({ browser }) => {
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()
    await page.goto('/')
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
    await context.close()
  })

  test('planner accessible at /plans/new without embedded wizard tab', async ({ page }) => {
    await page.goto('/plans')
    await expect(page.getByRole('button', { name: /בנייה ידנית|Build manually/i })).toHaveCount(0)
    await page.getByRole('button', { name: /תוכנית חדשה|New plan/i }).click()
    await expect(page.getByText(/חיפוש קורסים לסמסטר|Search courses for semester/i)).toBeVisible()
  })
})
