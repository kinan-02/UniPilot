import { describe, expect, it } from 'vitest'
import {
  buildCatalogSearchParams,
  catalogPagePath,
  creditBandRange,
  parseCatalogSearchParams,
} from './catalog'

describe('catalogPagePath', () => {
  it('builds query, faculty, credit band, and course deep links', () => {
    expect(catalogPagePath({ query: '00940345', faculty: '', creditBand: 'all' })).toBe('/catalog?q=00940345')
    expect(
      catalogPagePath({ query: '', faculty: '', creditBand: 'all', courseNumber: '00940345' }),
    ).toBe('/catalog?course=00940345')
    expect(catalogPagePath({ query: 'math', faculty: 'DNE', creditBand: 'mid' })).toBe(
      '/catalog?q=math&faculty=DNE&credits=mid',
    )
  })

  it('parses URL params back into search state', () => {
    const params = new URLSearchParams('q=algebra&faculty=DNE&credits=high&course=00940345')
    expect(parseCatalogSearchParams(params)).toEqual({
      query: 'algebra',
      faculty: 'DNE',
      creditBand: 'high',
      courseNumber: '00940345',
    })
  })

  it('maps credit bands to API ranges', () => {
    expect(creditBandRange('low')).toEqual({ minCredits: 0, maxCredits: 3 })
    expect(creditBandRange('high')).toEqual({ minCredits: 5.5 })
    expect(creditBandRange('all')).toEqual({})
  })

  it('returns bare catalog path when empty', () => {
    expect(buildCatalogSearchParams({ query: '', faculty: '', creditBand: 'all' }).toString()).toBe('')
    expect(catalogPagePath({ query: '', faculty: '', creditBand: 'all' })).toBe('/catalog')
  })
})
