import { expect, test } from './fixtures/test'
import { expectNoSeriousA11yViolations } from './helpers/a11y'

test.describe('Accessibility — authenticated core routes @a11y', () => {
  test('planner workspace meets WCAG 2.x Level A/AA', async ({ plannerPage, page }) => {
    await plannerPage.openNewPlanWithSemester()
    await expect(page.getByText(/לוח שבועי|Weekly schedule/i).first()).toBeVisible()
    await expectNoSeriousA11yViolations(page, { include: '.planner-workspace' })
  })

  test('graduation progress meets WCAG 2.x Level A/AA', async ({ progressPage, page }) => {
    await progressPage.gotoProgress()
    await progressPage.expectCoreSections()
    await expectNoSeriousA11yViolations(page, { include: 'main' })
  })

  test('transcript page meets WCAG 2.x Level A/AA', async ({ transcriptPage, page }) => {
    await transcriptPage.gotoTranscript()
    await expectNoSeriousA11yViolations(page, { include: 'main' })
  })

  test('catalog browse meets WCAG 2.x Level A/AA', async ({ catalogPage, page }) => {
    await catalogPage.gotoCatalog()
    await expectNoSeriousA11yViolations(page, { include: 'main' })
  })
})

test.describe('Accessibility — public routes @a11y', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('login page meets WCAG 2.x Level A/AA', async ({ authPage, page }) => {
    await authPage.gotoLogin()
    await expectNoSeriousA11yViolations(page)
  })
})
