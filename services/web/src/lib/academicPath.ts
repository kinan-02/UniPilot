/** DDS track slug resolution for academic path (Phase 0). */

import type { DegreeProgram, StudentAcademicPath } from '../types/api'

const PROGRAM_CODE_TO_TRACK: Record<string, string> = {
  '009216-1-000': 'track-data-information-engineering',
  '009009-1-000': 'track-industrial-engineering-management',
  '009118-1-000': 'track-information-systems-engineering',
}

export function trackSlugFromProgram(program: DegreeProgram | undefined): string | undefined {
  if (!program) return undefined
  const metadata = program.metadata as { wikiPage?: string } | undefined
  if (metadata?.wikiPage) return metadata.wikiPage
  return PROGRAM_CODE_TO_TRACK[program.programCode]
}

export function buildAcademicPathForProgram(
  program: DegreeProgram | undefined,
  existing?: StudentAcademicPath | null,
): StudentAcademicPath | undefined {
  const trackSlug = trackSlugFromProgram(program)
  if (!trackSlug) return existing ?? undefined
  return {
    trackSlug,
    minors: existing?.minors ?? [],
    specialPrograms: existing?.specialPrograms ?? [],
    graduatePrograms: existing?.graduatePrograms ?? [],
    specializations: existing?.specializations ?? [],
  }
}

export type CurriculumNodeStatus =
  | 'completed'
  | 'failed'
  | 'in_progress'
  | 'available'
  | 'blocked'
  | 'verify_with_registrar'

export function nodeStatusTone(
  status: CurriculumNodeStatus,
): 'neutral' | 'success' | 'warning' | 'danger' | 'primary' {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'blocked':
      return 'warning'
    case 'verify_with_registrar':
      return 'primary'
    case 'in_progress':
      return 'primary'
    default:
      return 'neutral'
  }
}
