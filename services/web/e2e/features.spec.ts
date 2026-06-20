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

test.describe('Manual plan wizard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/plans')
    await expect(page.getByRole('heading', { name: /תכנון סמסטר|Semester plans/i })).toBeVisible()
  })

  test('3-step flow: basics, courses, save', async ({ page }) => {
    await page.getByRole('button', { name: /בנייה ידנית|Build manually/i }).click()

    await expect(page.getByText(/לאיזה סמסטר|Which semester/i)).toBeVisible()
    await page.getByRole('main').getByRole('button', { name: /המשך|Continue/i }).click()

    const search = page.getByPlaceholder(/חפש קורס|Search course/i)
    await search.fill('02340117')
    await page.getByRole('listbox').getByRole('option').first().click({ timeout: 15_000 })

    await page.getByRole('main').getByRole('button', { name: /המשך|Continue/i }).click()
    await expect(page.getByText(/לוח שבועי|Weekly schedule/i).first()).toBeVisible()

    await page.getByRole('button', { name: /שמירת תוכנית|Save plan/i }).click()
    await expect(page.getByRole('heading', { name: /תוכנית|Plan/i })).toBeVisible({ timeout: 20_000 })
  })

  test('blocks continue without courses on step 2', async ({ page }) => {
    await page.getByRole('button', { name: /בנייה ידנית|Build manually/i }).click()
    await page.getByRole('main').getByRole('button', { name: /המשך|Continue/i }).click()
    await page.getByRole('main').getByRole('button', { name: /המשך|Continue/i }).click()

    await expect(page.getByText(/לפחות קורס אחד|at least one course/i)).toBeVisible()
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

  test('plans accessible without completing onboarding', async ({ page }) => {
    await page.goto('/plans')
    await page.getByRole('button', { name: /בנייה ידנית|Build manually/i }).click()
    await expect(page.getByText(/ניתן לבנות תוכנית|build a plan without/i)).toBeVisible()
  })
})
