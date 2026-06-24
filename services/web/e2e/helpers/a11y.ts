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
export async function expectNoSeriousA11yViolations(page: Page, options: A11yScanOptions = {}) {
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
