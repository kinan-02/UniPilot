import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

type A11yScanOptions = {
  /** WCAG tags passed to axe (default: wcag2a + wcag2aa). */
  tags?: string[]
  /** Optional CSS selector to scope the scan; falls back to full page when missing. */
  include?: string
}

const DEFAULT_TAGS = ['wcag2a', 'wcag2aa']

/**
 * Run an axe accessibility scan and fail on serious/critical violations.
 * Matches common industry CI gates (WCAG 2.x Level A/AA).
 */
/**
 * Let every entry animation finish before anything is measured.
 *
 * axe reads the COMPUTED colour, so an element caught mid-fade reports the
 * blend of its colour and the background rather than its colour. At 84% through
 * a fade, muted text over the page surface computes as #818793 instead of
 * #6b7280 -- 3.45:1 instead of 4.63:1 -- and the scan fails on colours that are
 * actually fine. It failed on 79 nodes in CI for exactly this reason, and would
 * have passed or failed depending on how fast the machine was.
 *
 * `prefers-reduced-motion` is not enough on its own here: `motion` drives these
 * fades in JavaScript, where a CSS media query has no say. Waiting on the
 * animations themselves covers both, since WAAPI animations are what
 * `getAnimations()` returns whoever started them.
 *
 * Infinite animations are skipped for the obvious reason.
 */
async function waitForAnimationsToSettle(page: Page) {
  await page.evaluate(async () => {
    const finite = document
      .getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Infinity)

    // A cancelled animation rejects `finished`; that is settled enough for us.
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)))
  })
}

export async function expectNoSeriousA11yViolations(page: Page, options: A11yScanOptions = {}) {
  await waitForAnimationsToSettle(page)

  const builder = new AxeBuilder({ page }).withTags(options.tags ?? DEFAULT_TAGS)

  if (options.include) {
    const scoped = page.locator(options.include).first()
    if (await scoped.count()) {
      builder.include(options.include)
    }
  }

  const results = await builder.analyze()
  const blocking = results.violations.filter((violation) =>
    violation.impact === 'critical' || violation.impact === 'serious',
  )

  if (blocking.length) {
    const summary = blocking
      .map(
        (violation) =>
          `[${violation.impact}] ${violation.id}: ${violation.help} (${violation.nodes.length} nodes)`,
      )
      .join('\n')
    expect(blocking, `Accessibility violations:\n${summary}`).toHaveLength(0)
  }
}
