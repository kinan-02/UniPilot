import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom implements no layout, so it ships no scrollIntoView. Any component that
// scrolls a ref into view on mount (AdvisorPage's message list) throws without it.
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
  localStorage.clear()
})
