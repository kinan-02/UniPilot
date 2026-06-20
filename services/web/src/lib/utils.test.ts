import { describe, expect, it } from 'vitest'
import { cn, formatCredits, formatPercent } from '../lib/utils'

describe('utils', () => {
  it('merges class names', () => {
    expect(cn('px-2', false && 'hidden', 'py-1')).toBe('px-2 py-1')
  })

  it('formats credits', () => {
    expect(formatCredits(3)).toBe('3')
    expect(formatCredits(3.5)).toBe('3.5')
  })

  it('formats percent', () => {
    expect(formatPercent(42.156)).toBe('42.2%')
  })
})
