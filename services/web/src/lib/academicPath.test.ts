import { describe, expect, it } from 'vitest'
import { buildAcademicPathForProgram, trackSlugFromProgram } from './academicPath'
import type { DegreeProgram } from '../types/api'

const dneProgram: DegreeProgram = {
  id: '1',
  programCode: '009216-1-000',
  metadata: { wikiPage: 'track-data-information-engineering' },
}

describe('academicPath helpers', () => {
  it('resolves track slug from program metadata', () => {
    expect(trackSlugFromProgram(dneProgram)).toBe('track-data-information-engineering')
  })

  it('builds academic path with track slug', () => {
    expect(buildAcademicPathForProgram(dneProgram)?.trackSlug).toBe(
      'track-data-information-engineering',
    )
  })
})
