import { expect, test } from '@playwright/test'

test.describe('Catalog', () => {
  test('search returns results and opens course detail', async ({ page }) => {
    await page.goto('/catalog')
    await expect(page.getByRole('heading', { name: /קטלוג קורסים|Course catalog/i })).toBeVisible()

    await page.getByPlaceholder(/חיפוש לפי מספר|Search by course number/i).fill('02340117')
    await expect(page.getByText(/02340117/).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /02340117/ }).first().click()
    await expect(page.getByText(/נק״ז|credits/i).first()).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('Semester planner workspace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/plans/new')
    await expect(page.getByRole('heading', { name: /תוכנית חדשה|New plan/i })).toBeVisible()
  })

  test('maybe courses: add, grid preview, move between lists', async ({ page }) => {
    const search = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
    await search.fill('02340117')
    await expect(page.getByText(/02340117/).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /הוסף לאולי|Add to maybe/i }).click()
    const maybePanel = page.getByTestId('maybe-courses-panel')
    await expect(maybePanel.getByText('02340117')).toBeVisible({ timeout: 10_000 })

    const maybeGridBlock = page
      .locator('.planner-workspace')
      .getByRole('button')
      .filter({ hasText: '02340117' })
      .first()
    await expect(maybeGridBlock).toBeVisible({ timeout: 15_000 })

    await maybePanel.locator('button[title="העבר לנבחרים"], button[title="Move to selected"]').click()
    const selectedPanel = page.getByTestId('selected-courses-panel')
    await expect(selectedPanel.getByText('02340117')).toBeVisible({ timeout: 10_000 })

    await selectedPanel.locator('button[title="העבר לאולי"], button[title="Move to maybe"]').click()
    await expect(maybePanel.getByText('02340117')).toBeVisible({ timeout: 10_000 })
  })

  test('CheeseFork-style flow: semester, search, add course, grid lesson selection, save', async ({ page }) => {
    await expect(page.getByText(/חיפוש קורסים לסמסטר|Search courses for semester/i)).toBeVisible()
    await expect(page.getByText(/לוח שבועי|Weekly schedule/i).first()).toBeVisible()

    const search = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
    await search.fill('02340117')
    await expect(page.getByText(/02340117/).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()
    await expect(page.getByText(/4.*נק|4.*cred/i).first()).toBeVisible()

    const lessonBlock = page
      .locator('.planner-workspace button')
      .filter({ has: page.locator('p.font-mono', { hasText: '02340117' }) })
      .first()
    await expect(lessonBlock).toBeVisible({ timeout: 15_000 })
    await lessonBlock.click()
    await expect(lessonBlock).toHaveClass(/ring-2/)

    await page.getByRole('button', { name: /שמירת תוכנית|Save plan/i }).click()
    await expect(page).toHaveURL(/\/plans\/[^/]+\/edit/, { timeout: 20_000 })
  })

  test('saved plan: move selected to maybe persists after reload', async ({ page }) => {
    const search = page.getByPlaceholder(/חיפוש מספר|Search course number|חפש קורס/i)
    await search.fill('02340117')
    await expect(page.getByText(/02340117/).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: /הוסף לתוכנית|Add to plan/i }).click()
    const selectedPanel = page.getByTestId('selected-courses-panel')
    await expect(selectedPanel.getByText('02340117')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: /שמירת תוכנית|Save plan/i }).click()
    await expect(page).toHaveURL(/\/plans\/([^/]+)\/edit/, { timeout: 20_000 })

    const persistResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' &&
        /\/semester-plans\/[^/]+$/.test(response.url()) &&
        response.status() === 200,
    )
    await selectedPanel.locator('button[title="העבר לאולי"], button[title="Move to maybe"]').click()
    const maybePanel = page.getByTestId('maybe-courses-panel')
    await expect(maybePanel.getByText('02340117')).toBeVisible({ timeout: 10_000 })
    await persistResponse

    await page.reload()
    await expect(page.getByRole('heading', { name: /עריכת תוכנית|Edit plan/i })).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByTestId('maybe-courses-panel').getByText('02340117')).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByTestId('selected-courses-panel').getByText('02340117')).toHaveCount(0)
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
