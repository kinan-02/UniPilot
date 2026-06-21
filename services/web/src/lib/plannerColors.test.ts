import { describe, expect, it } from 'vitest'
import { courseColor, courseColorStyles } from './plannerColors'

describe('plannerColors', () => {
  it('returns stable colors for the same course number', () => {
    expect(courseColor('02340114')).toBe(courseColor('02340114'))
  })

  it('uses override when provided', () => {
    expect(courseColor('02340114', '#ff0000')).toBe('#ff0000')
  })

  it('builds opaque style objects for event blocks', () => {
    const styles = courseColorStyles('02340114')
    expect(styles.color).toBe('#0f172a')
    expect(styles.backgroundColor).toMatch(/^#[0-9a-f]{6}$/i)
    expect(styles.backgroundColor).not.toMatch(/22$/)
    expect(styles.borderColor).toMatch(/^#/)
  })
})
