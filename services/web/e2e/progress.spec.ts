import { expect, test } from './fixtures/test'

test.describe('Graduation progress — industry E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/progress')
    await expect(page.getByTestId('progress-summary-card')).toBeVisible({ timeout: 20_000 })
  })

  test('renders summary, curriculum graph, pools, and mandatory sections', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /התקדמות לתואר|Graduation progress/i }),
    ).toBeVisible()
    await expect(page.getByTestId('progress-summary-card')).toBeVisible()
    await expect(page.getByTestId('curriculum-graph-section')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('elective-pools-panel')).toBeVisible({ timeout: 15_000 })
    await expect(
      page.getByRole('heading', { name: /Mandatory requirements|דרישות חובה/i }),
    ).toBeVisible()
  })

  test('shows General Technion pools below faculty pools', async ({ page }) => {
    const panel = page.getByTestId('elective-pools-panel')
    await expect(panel).toBeVisible({ timeout: 15_000 })

    await expect(
      page.getByRole('heading', {
        name: /General Technion requirements|דרישות כלל-טכניוניות/i,
      }),
    ).toBeVisible()

    const facultyBeforeGeneral = await panel.evaluate((root) => {
      const firstPool = root.querySelector('[data-testid^="elective-pool-card-"]')
      const generalHeading = Array.from(root.querySelectorAll('h3')).find((node) =>
        /General Technion|דרישות כלל-טכניוניות/.test(node.textContent ?? ''),
      )
      if (!firstPool || !generalHeading) return false
      return Boolean(
        firstPool.compareDocumentPosition(generalHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
      )
    })
    expect(facultyBeforeGeneral).toBe(true)
  })

  test('expands and collapses a pool with keyboard-friendly toggle', async ({ page }) => {
    const panel = page.getByTestId('elective-pools-panel')
    const poolCard = panel.locator('[data-testid^="elective-pool-card-"]').first()
    await expect(poolCard).toBeVisible()

    const toggle = poolCard.locator('button[aria-expanded]').first()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(poolCard.locator('[data-testid^="elective-pool-detail-"]')).toBeVisible()

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  test('filters pools via search', async ({ page }) => {
    const panel = page.getByTestId('elective-pools-panel')
    const search = panel.getByPlaceholder(/Search pools|חיפוש בריכות/i)
    await search.fill('physical education')
    await expect(
      panel.locator('[data-testid*="physical-education-pool"]'),
    ).toBeVisible({ timeout: 10_000 })
    await expect(panel.locator('[data-testid*="elective-ds-pool"]')).toHaveCount(0)
  })

  test('does not expose removed bucket explorer UI', async ({ page }) => {
    await expect(page.getByRole('button', { name: /פתח בריכה|Browse pool/i })).toHaveCount(0)
    await expect(page.getByTestId('elective-pool-explorer')).toHaveCount(0)
    await expect(page.getByText(/still needed|עדיין חסר/i)).toHaveCount(0)
  })

  test('supports Hebrew default and English switch with dir attribute', async ({ page }) => {
    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('en')
    await expect(page.getByRole('heading', { name: /Graduation progress/i })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')

    await page.getByRole('combobox', { name: /שפה|Language/i }).first().selectOption('he')
    await expect(page.getByRole('heading', { name: /התקדמות לתואר/i })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  })
})

test.describe('Graduation progress — guest access', () => {
  test('redirects unauthenticated users away from progress', async ({ browser }) => {
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()
    await page.goto('/progress')
    await expect(page.getByRole('button', { name: /התחברות|Sign in/i })).toBeVisible({
      timeout: 15_000,
    })
    await context.close()
  })
})
