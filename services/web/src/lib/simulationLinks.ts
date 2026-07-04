import type { AcademicRiskAnalysis, SemesterPlan } from '../types/api'

export type SimulationLinkParams = {
  text: string
  planId?: string
  autoBuild?: boolean
}

const COURSE_CODE_RE = /\b0\d{7}\b/g

const SIMULATION_INTENT_PATTERNS: RegExp[] = [
  /\bwhat\s+if\b/i,
  /\bwhat\s+happens\s+if\b/i,
  /\bwhat\s+would\s+happen\b/i,
  /מה\s+אם/,
  /מה\s+יקרה\s+אם/,
  /\bdrop\s+(?:course\s+)?0\d{7}\b/i,
  /\bremove\s+(?:course\s+)?0\d{7}\b/i,
  /לזרוק\s+(?:את\s+)?(?:קורס\s+)?0\d{7}/,
  /להוריד\s+(?:את\s+)?(?:קורס\s+)?0\d{7}/,
  /\bswitch\s+to\s+track\b/i,
  /\bchange\s+track\b/i,
  /לעבור\s+למסלול/,
  /\badd\s+0\d{7}\s+to\s+my\s+plan\b/i,
  /להוסיף\s+לתוכנית\s+0\d{7}/,
  /לקחת\s+0\d{7}\s+בסמסטר/,
  /\bsimulate\b/i,
  /סימולציה/,
]

export function extractCourseNumbers(text: string): string[] {
  const matches = text.match(COURSE_CODE_RE) ?? []
  return [...new Set(matches)]
}

export function detectSimulationIntent(text: string): boolean {
  const normalized = text.trim()
  if (!normalized) {
    return false
  }
  return SIMULATION_INTENT_PATTERNS.some((pattern) => pattern.test(normalized))
}

export function buildSimulationPath(params: SimulationLinkParams): string {
  const search = new URLSearchParams()
  search.set('text', params.text)
  if (params.planId) {
    search.set('planId', params.planId)
  }
  if (params.autoBuild ?? true) {
    search.set('autoBuild', '1')
  }
  return `/simulations?${search.toString()}`
}

export function buildDropCourseText(courseNumber: string): string {
  return `What if I drop course ${courseNumber} from my transcript?`
}

export function buildAddPlannedCourseText(courseNumber: string): string {
  return `What if I add course ${courseNumber} to my next semester plan?`
}

export function buildPlanWhatIfText(plan: SemesterPlan): string {
  const courseNumbers = plan.semesters.flatMap((semester) =>
    semester.plannedCourses
      .map((course) => course.courseNumber)
      .filter((courseNumber): courseNumber is string => Boolean(courseNumber)),
  )
  const uniqueNumbers = [...new Set(courseNumbers)]
  const planLabel = plan.name ?? `semester plan v${plan.version}`

  if (!uniqueNumbers.length) {
    return `What if I follow my semester plan "${planLabel}"?`
  }

  if (uniqueNumbers.length === 1) {
    return `What if I add course ${uniqueNumbers[0]} to my plan?`
  }

  return `What if I add these courses to my plan: ${uniqueNumbers.join(', ')}?`
}

export function buildRiskMitigationText(
  risk: NonNullable<AcademicRiskAnalysis['risks']>[number],
  planId?: string,
): string {
  const combined = `${risk.title ?? ''} ${risk.message ?? ''}`
  const courseNumbers = extractCourseNumbers(combined)

  if (courseNumbers.length === 1) {
    return `What if I add course ${courseNumbers[0]} to my plan to address: ${risk.title ?? 'this risk'}?`
  }

  if (courseNumbers.length > 1) {
    return `What if I add courses ${courseNumbers.join(', ')} to my plan to address: ${risk.title ?? 'this risk'}?`
  }

  const label = risk.title ?? risk.message ?? 'this academic risk'
  if (planId) {
    return `What if I adjust my semester plan to mitigate: ${label}?`
  }

  return `What if I adjust my plan to mitigate: ${label}?`
}
