import type { AcademicPathSelection, CatalogPathOption, StudentAcademicPath } from '../types/api'

export function resolveDegreeIdFromPathOption(option: CatalogPathOption | undefined): string | undefined {
  if (!option) return undefined
  if (option.linkedDegreeProgramId) return option.linkedDegreeProgramId
  if (option.selectableAsPrimary && option.id) return option.id
  return undefined
}

export function trackSlugFromPathOption(option: CatalogPathOption | undefined): string | undefined {
  if (!option) return undefined
  if (option.kind === 'bsc_track') return option.wikiSlug
  return undefined
}

export function pathSelectionFromOption(
  option: CatalogPathOption,
): AcademicPathSelection {
  return {
    kind: option.kind as AcademicPathSelection['kind'],
    trackSlug: option.kind === 'bsc_track' ? option.wikiSlug : undefined,
    programCode: option.linkedProgramCode ?? undefined,
    label: option.nameHe ?? option.name ?? option.nameEn ?? option.wikiSlug,
  }
}

export function buildAcademicPathPayload(
  primaryOption: CatalogPathOption | undefined,
  supplementalOptions: CatalogPathOption[],
  existing?: StudentAcademicPath | null,
): StudentAcademicPath | undefined {
  const trackSlug = trackSlugFromPathOption(primaryOption)
  const primaryGraduate =
    primaryOption?.kind === 'graduate_program' ? [pathSelectionFromOption(primaryOption)] : []
  const minors = supplementalOptions
    .filter((option) => option.kind === 'minor')
    .map(pathSelectionFromOption)
  const specialPrograms = supplementalOptions
    .filter((option) => option.kind === 'special_program')
    .map(pathSelectionFromOption)
  const specializations = supplementalOptions
    .filter((option) => option.kind === 'dne_specialization')
    .map(pathSelectionFromOption)
  const graduatePrograms = supplementalOptions
    .filter((option) => option.kind === 'graduate_program')
    .map(pathSelectionFromOption)

  if (
    !trackSlug &&
    primaryGraduate.length === 0 &&
    minors.length === 0 &&
    specialPrograms.length === 0 &&
    specializations.length === 0 &&
    graduatePrograms.length === 0 &&
    !existing
  ) {
    return undefined
  }

  return {
    trackSlug: trackSlug ?? existing?.trackSlug ?? undefined,
    minors: minors.length ? minors : existing?.minors ?? [],
    specialPrograms: specialPrograms.length ? specialPrograms : existing?.specialPrograms ?? [],
    specializations: specializations.length ? specializations : existing?.specializations ?? [],
    graduatePrograms: graduatePrograms.length
      ? graduatePrograms
      : primaryGraduate.length
        ? primaryGraduate
        : existing?.graduatePrograms ?? [],
  }
}

const WIKI_META_LINE = /^\*\*[^*]+:\*\*/

export function cleanPathOptionTitle(title: string): string {
  return title
    .replace(/^Track\s*[—–-]\s*/i, '')
    .replace(/^Program\s*[—–-]\s*/i, '')
    .replace(/^Minor\s*[—–-]\s*/i, '')
    .replace(/\s*\([^)]*[\u0590-\u05FF][^)]*\)\s*$/u, '')
    .trim()
}

export function parsePathOptionWikiMeta(description: string | undefined) {
  if (!description?.trim()) {
    return { credits: undefined as string | undefined, duration: undefined as string | undefined }
  }
  const credits = description.match(/\*\*Total credits(?:\s+required)?:\*\*\s*([\d.]+)/i)?.[1]
  const duration = description.match(/\*\*Duration:\*\*\s*([^*]+?)(?:\s*\*\*|$)/i)?.[1]?.trim()
  return { credits, duration }
}

export function resolvePathOptionMeta(option: CatalogPathOption) {
  const parsed = parsePathOptionWikiMeta(option.description)
  return {
    duration: option.duration ?? parsed.duration,
    credits: option.totalCreditsRequired ?? parsed.credits,
  }
}

export function formatPathOptionCredits(credits: string, locale: 'he' | 'en'): string {
  return locale === 'he' ? `${credits} נק״ז` : `${credits} credits`
}

export function formatPathOptionDuration(raw: string, locale: 'he' | 'en'): string {
  const trimmed = raw.trim()

  const yearsWithSemesters = trimmed.match(/^(\d+(?:\.\d+)?)\s+years?\s*\((\d+)\s+semesters?\)$/i)
  if (yearsWithSemesters) {
    const [, years, semesters] = yearsWithSemesters
    return locale === 'he'
      ? `${years} שנים (${semesters} סמסטרים)`
      : `${years} years (${semesters} semesters)`
  }

  const semestersWithYears = trimmed.match(
    /^(\d+)\s+semesters?\s*\((?:≈\s*)?(\d+(?:\.\d+)?)\s+years?\)$/i,
  )
  if (semestersWithYears) {
    const [, semesters, years] = semestersWithYears
    return locale === 'he'
      ? `${semesters} סמסטרים (כ-${years} שנים)`
      : `${semesters} semesters (≈${years} years)`
  }

  const yearsOnly = trimmed.match(/^(\d+(?:\.\d+)?)\s+years?$/i)
  if (yearsOnly) {
    return locale === 'he' ? `${yearsOnly[1]} שנים` : `${yearsOnly[1]} years`
  }

  const semestersOnly = trimmed.match(/^(\d+)\s+semesters?$/i)
  if (semestersOnly) {
    return locale === 'he' ? `${semestersOnly[1]} סמסטרים` : `${semestersOnly[1]} semesters`
  }

  return trimmed
}

const STUDY_LEVEL_LABELS: Record<string, { he: string; en: string }> = {
  BSc: { he: 'תואר ראשון', en: 'Bachelor' },
  MSc: { he: 'תואר שני', en: 'Master' },
  PhD: { he: 'דוקטורט', en: 'PhD' },
  MBA: { he: 'MBA', en: 'MBA' },
}

function formatStudyLevels(levels: string[], locale: 'he' | 'en'): string {
  return levels
    .map((level) => STUDY_LEVEL_LABELS[level]?.[locale] ?? level)
    .join(locale === 'he' ? ' · ' : ' · ')
}

export function isWikiMetadataBlob(text: string | undefined): boolean {
  if (!text?.trim()) return false
  return WIKI_META_LINE.test(text.trim())
}

export function optionLabel(option: CatalogPathOption, locale: 'he' | 'en' = 'he'): string {
  const hebrew = option.nameHe ? cleanPathOptionTitle(option.nameHe) : undefined
  const english = option.nameEn
    ? cleanPathOptionTitle(option.nameEn)
    : option.name
      ? cleanPathOptionTitle(option.name)
      : undefined
  if (locale === 'he') {
    return hebrew ?? english ?? option.wikiSlug
  }
  return english ?? hebrew ?? option.wikiSlug
}

export function pathOptionSubtitle(
  option: CatalogPathOption,
  locale: 'he' | 'en' = 'he',
): string | undefined {
  const parts: string[] = []
  const meta = resolvePathOptionMeta(option)

  if (meta.duration) {
    parts.push(formatPathOptionDuration(meta.duration, locale))
  }
  if (meta.credits) {
    parts.push(formatPathOptionCredits(meta.credits, locale))
  }
  if (parts.length > 0) {
    return parts.join(' · ')
  }
  if (option.studyLevels?.length) {
    return formatStudyLevels(option.studyLevels, locale)
  }
  return undefined
}

export function findPrimaryOptionId(
  degreeId: string | null | undefined,
  options: CatalogPathOption[],
): string {
  if (!degreeId) return ''
  const direct = options.find((option) => option.id === degreeId)
  if (direct) return direct.id ?? ''
  const linked = options.find((option) => option.linkedDegreeProgramId === degreeId)
  return linked?.id ?? ''
}

export function resolveFacultyIdFromProfile(
  profileFacultyId: string | null | undefined,
  options: CatalogPathOption[],
  faculties: { facultyId: string }[],
): string {
  if (profileFacultyId) return profileFacultyId
  const fromPrimary = options.find((option) => option.selectableAsPrimary)?.facultyId
  if (fromPrimary) return fromPrimary
  return faculties[0]?.facultyId ?? ''
}

export function supplementalOptionIdsFromPath(
  academicPath: StudentAcademicPath | undefined,
  options: CatalogPathOption[],
): string[] {
  if (!academicPath || options.length === 0) return []
  const labels = new Set<string>()
  for (const selection of [
    ...(academicPath.minors ?? []),
    ...(academicPath.specialPrograms ?? []),
    ...(academicPath.specializations ?? []),
    ...(academicPath.graduatePrograms ?? []),
  ]) {
    if (selection.label) labels.add(selection.label)
    if (selection.trackSlug) labels.add(selection.trackSlug)
  }
  return options
    .filter((option) => !option.selectableAsPrimary)
    .filter((option) => labels.has(optionLabel(option)) || labels.has(option.wikiSlug))
    .map((option) => option.id ?? '')
    .filter(Boolean)
}
