import { expect, test } from '@playwright/test'

const password = 'StrongPass123!'
const email = `e2e-${Date.now()}@example.com`

test.describe('UniPilot smoke flow', () => {
  test('register, onboard, browse catalog, plans, and sign out', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: /יצירת חשבון|Create your account/i })).toBeVisible()

    await page.getByLabel(/אימייל|Email/i).fill(email)
    await page.getByLabel(/^סיסמה$|^Password$/i).fill(password)
    await page.getByRole('button', { name: /יצירת חשבון|Create account/i }).click()

    await expect(page.getByRole('heading', { name: /הגדרת פרופיל|Set up your profile/i })).toBeVisible({
      timeout: 15_000,
    })

    const degreeSelect = page.locator('#degree-program')
    await expect(degreeSelect.locator('option')).toHaveCount(4, { timeout: 15_000 })
    const programId = await degreeSelect.locator('option').nth(1).getAttribute('value')
    expect(programId).toBeTruthy()
    await degreeSelect.selectOption(programId!)
    await page.getByRole('button', { name: /המשך ללוח הבקרה|Continue to dashboard/i }).click()

    await expect(page.getByRole('heading', { name: /שלום|Hello/i })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('navigation').getByRole('link', { name: /קטלוג|Catalog/i }).click()
    await expect(page.getByRole('heading', { name: /קטלוג קורסים|Course catalog/i })).toBeVisible()

    await page.getByRole('navigation').getByRole('link', { name: /תכנון סמסטר|Plans/i }).click()
    await expect(page.getByRole('heading', { name: /תכנון סמסטר|Semester plans/i })).toBeVisible()

    await page.getByRole('button', { name: /תוכנית חדשה|New plan/i }).click()
    await expect(page.getByText(/חיפוש קורסים לסמסטר|Search courses for semester/i)).toBeVisible()

    await page.getByRole('navigation').getByRole('link', { name: /לוח בקרה|Dashboard/i }).click()
    await page.getByRole('button', { name: /התנתקות|Sign out/i }).click()
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  })

  test('login page renders for guests', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible()
  })
})
