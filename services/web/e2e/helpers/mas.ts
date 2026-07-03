/** Course with no prerequisites in courses_2025_201.json — reliable for MAS deterministic goals. */
export const E2E_MAS_COURSE = '00140008'

export const E2E_MAS_SECOND_COURSE = '00140102'

/** Typical student goals (EN / HE) for UI journey tests. */
export const MAS_GOALS = {
  explicitCourseEn: (course = E2E_MAS_COURSE) =>
    `Plan course ${course} for next semester`,
  explicitCourseHe: (course = E2E_MAS_COURSE) =>
    `תכננו את קורס ${course} לסמסטר הבא`,
  balancedLoadEn: 'Plan my next semester with a balanced workload',
  balancedLoadHe: 'תכננו לי את הסמסטר הבא עם עומס מאוזן',
  multiCourseEn: (a = E2E_MAS_COURSE, b = E2E_MAS_SECOND_COURSE) =>
    `Plan courses ${a} and ${b} for next semester`,
  policyQaEn: 'What are my student rights for grade appeals?',
  policyQaHe: 'מה אומר התקנון על זכויות סטודנט בערעור ציון?',
} as const

/** Policy Q&A skips the planner loop — shorter wait is usually enough. */
export const MAS_POLICY_SESSION_TIMEOUT_MS = 60_000

/** Escape user text for safe use inside `new RegExp(...)`. */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** MAS worker can take up to ~2 min when LLM tool loop runs. */
export const MAS_SESSION_TIMEOUT_MS = 180_000
