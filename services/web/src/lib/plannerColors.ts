/** Deterministic course colors for planner UI (not copied from CheeseFork). */

const PALETTE = [
  '#2563eb',
  '#7c3aed',
  '#db2777',
  '#dc2626',
  '#ea580c',
  '#ca8a04',
  '#16a34a',
  '#0891b2',
  '#4f46e5',
  '#9333ea',
  '#0d9488',
  '#c026d3',
] as const

function hashCourseNumber(courseNumber: string): number {
  let hash = 0
  for (let index = 0; index < courseNumber.length; index += 1) {
    hash = (hash * 31 + courseNumber.charCodeAt(index)) >>> 0
  }
  return hash
}

export function courseColor(courseNumber: string, override?: string | null): string {
  if (override) return override
  const index = hashCourseNumber(courseNumber) % PALETTE.length
  return PALETTE[index]
}

/** Opaque pastel fill so grid lines do not show through event blocks. */
function blendHexWithWhite(hex: string, whiteRatio: number): string {
  const normalized = hex.replace('#', '')
  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  const colorRatio = 1 - whiteRatio
  const mix = (channel: number) =>
    Math.round(channel * colorRatio + 255 * whiteRatio)
      .toString(16)
      .padStart(2, '0')
  return `#${mix(r)}${mix(g)}${mix(b)}`
}

export function courseColorStyles(courseNumber: string, override?: string | null) {
  const color = courseColor(courseNumber, override)
  return {
    backgroundColor: blendHexWithWhite(color, 0.82),
    borderColor: color,
    color: '#0f172a',
  }
}
