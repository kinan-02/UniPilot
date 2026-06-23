export type CatalogCreditBand = 'all' | 'low' | 'mid' | 'high'

export type CatalogSearchState = {
  query: string
  faculty: string
  creditBand: CatalogCreditBand
  courseNumber?: string
}

export function creditBandRange(
  band: CatalogCreditBand,
): { minCredits?: number; maxCredits?: number } {
  switch (band) {
    case 'low':
      return { minCredits: 0, maxCredits: 3 }
    case 'mid':
      return { minCredits: 3.5, maxCredits: 5 }
    case 'high':
      return { minCredits: 5.5 }
    default:
      return {}
  }
}

export function buildCatalogSearchParams(state: CatalogSearchState): URLSearchParams {
  const params = new URLSearchParams()
  const query = (state.query ?? '').trim()
  const faculty = (state.faculty ?? '').trim()
  const courseNumber = state.courseNumber?.trim()

  if (query) params.set('q', query)
  if (faculty) params.set('faculty', faculty)
  if (state.creditBand !== 'all') params.set('credits', state.creditBand)
  if (courseNumber) params.set('course', courseNumber)
  return params
}

export function parseCatalogSearchParams(params: URLSearchParams): CatalogSearchState {
  const creditParam = params.get('credits')
  const creditBand: CatalogCreditBand =
    creditParam === 'low' || creditParam === 'mid' || creditParam === 'high' ? creditParam : 'all'

  return {
    query: params.get('q') ?? '',
    faculty: params.get('faculty') ?? '',
    creditBand,
    courseNumber: params.get('course') ?? undefined,
  }
}

export function catalogPagePath(state: CatalogSearchState): string {
  const params = buildCatalogSearchParams(state)
  const suffix = params.toString()
  return suffix ? `/catalog?${suffix}` : '/catalog'
}
