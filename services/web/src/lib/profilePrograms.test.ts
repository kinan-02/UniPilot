import { describe, expect, it } from 'vitest'
import type { CatalogPathOption } from '../types/api'
import {
  buildAcademicPathPayload,
  cleanPathOptionTitle,
  formatPathOptionDuration,
  isWikiMetadataBlob,
  optionLabel,
  parsePathOptionWikiMeta,
  pathOptionSubtitle,
  resolveDegreeIdFromPathOption,
} from './profilePrograms'

const dneOption: CatalogPathOption = {
  optionKey: 'technion:dds:track-data-information-engineering',
  facultyId: 'faculty-dds',
  wikiSlug: 'track-data-information-engineering',
  kind: 'bsc_track',
  name: 'Track — Data & Information Engineering (הנדסת נתונים ומידע)',
  nameHe: 'הנדסת נתונים ומידע',
  nameEn: 'Track — Data & Information Engineering',
  linkedProgramCode: '009216-1-000',
  selectableAsPrimary: true,
  description:
    '**Hebrew name:** הנדסת נתונים ומידע **Program code:** 009216-1-000 **Duration:** 4 years (8 semesters) **Total credits required:** 155',
}

const chemistryOption: CatalogPathOption = {
  optionKey: 'technion:chemistry:track-chemistry-haznek',
  facultyId: 'faculty-chemistry',
  wikiSlug: 'track-chemistry-haznek',
  kind: 'bsc_track',
  name: 'Chemistry — Haznek',
  nameHe: 'כימיה חזנק',
  selectableAsPrimary: true,
  description: '**Duration:** 9 semesters (≈ 4.5 years) **Total credits:** 124',
}

const avivimOption: CatalogPathOption = {
  optionKey: 'technion:dds:program-avivim',
  facultyId: 'faculty-dds',
  wikiSlug: 'program-avivim',
  kind: 'special_program',
  name: 'Avivim Excellence Program (תוכנית עילית "אביבים")',
  nameHe: 'תוכנית עילית "אביבים"',
  nameEn: 'Avivim Excellence Program',
  selectableAsPrimary: false,
}

describe('path option presentation', () => {
  it('preserves embedded quotes in Hebrew titles', () => {
    expect(optionLabel(avivimOption, 'he')).toBe('תוכנית עילית "אביבים"')
  })

  it('uses the Hebrew title without wiki prefixes', () => {
    expect(optionLabel(dneOption, 'he')).toBe('הנדסת נתונים ומידע')
    expect(optionLabel(dneOption, 'en')).toBe('Data & Information Engineering')
  })

  it('strips track prefixes from English titles', () => {
    expect(cleanPathOptionTitle('Track — Industrial Engineering & Management')).toBe(
      'Industrial Engineering & Management',
    )
  })

  it('localizes duration and credits without exposing program codes', () => {
    const withStructuredMeta: CatalogPathOption = {
      ...dneOption,
      duration: '4 years (8 semesters)',
      totalCreditsRequired: '155',
      description: 'Program overview without metadata fields.',
    }
    expect(pathOptionSubtitle(withStructuredMeta, 'en')).toBe('4 years (8 semesters) · 155 credits')
    expect(pathOptionSubtitle(withStructuredMeta, 'he')).toBe('4 שנים (8 סמסטרים) · 155 נק״ז')
    expect(pathOptionSubtitle(withStructuredMeta, 'he')).not.toContain('009216')
    expect(pathOptionSubtitle(withStructuredMeta, 'he')).not.toContain('years')
  })

  it('formats semester-first durations in the active locale', () => {
    expect(formatPathOptionDuration('9 semesters (≈ 4.5 years)', 'he')).toBe('9 סמסטרים (כ-4.5 שנים)')
    expect(pathOptionSubtitle(chemistryOption, 'he')).toBe('9 סמסטרים (כ-4.5 שנים) · 124 נק״ז')
  })

  it('detects wiki metadata blobs', () => {
    expect(isWikiMetadataBlob(dneOption.description)).toBe(true)
    expect(isWikiMetadataBlob('A short overview of the program.')).toBe(false)
  })

  it('parses credits and duration from wiki metadata blobs', () => {
    expect(parsePathOptionWikiMeta(dneOption.description)).toEqual({
      credits: '155',
      duration: '4 years (8 semesters)',
    })
    expect(parsePathOptionWikiMeta(chemistryOption.description)).toEqual({
      credits: '124',
      duration: '9 semesters (≈ 4.5 years)',
    })
  })
})

describe('profile payload builders', () => {
  it('prefers linkedDegreeProgramId when resolving degreeId', () => {
    expect(resolveDegreeIdFromPathOption(dneOption)).toBeUndefined()
    expect(
      resolveDegreeIdFromPathOption({
        ...dneOption,
        linkedDegreeProgramId: 'degree-dne-id',
      }),
    ).toBe('degree-dne-id')
    expect(
      resolveDegreeIdFromPathOption({
        ...dneOption,
        id: 'path-option-id',
        linkedDegreeProgramId: undefined,
      }),
    ).toBe('path-option-id')
  })

  it('builds academic path payload from primary and supplemental options', () => {
    const minor: CatalogPathOption = {
      ...avivimOption,
      id: 'minor-1',
      kind: 'minor',
      selectableAsPrimary: false,
    }
    const payload = buildAcademicPathPayload(
      { ...dneOption, id: 'dne-id' },
      [minor],
    )
    expect(payload?.trackSlug).toBe('track-data-information-engineering')
    expect(payload?.minors).toHaveLength(1)
    expect(payload?.minors?.[0]?.label).toBe('תוכנית עילית "אביבים"')
  })
})
