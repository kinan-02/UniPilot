import type { CurriculumGraph, ElectivePoolCourse } from '../types/api'
import { courseNumberKeys } from './courseNumbers'

/** Same course under different track catalog codes (see vault wiki 0960211 vs 0960221). */
export const KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS: string[][] = [['00960211', '00960221']]

export function mergeOverlappingEquivalenceGroups(groups: Array<Set<string>>): Array<Set<string>> {
  const merged: Array<Set<string>> = []
  for (const rawGroup of groups) {
    const group = new Set(rawGroup)
    if (!group.size) continue

    const overlapIndexes: number[] = []
    merged.forEach((existing, index) => {
      if ([...group].some((key) => existing.has(key))) {
        overlapIndexes.push(index)
      }
    })

    for (const index of overlapIndexes.reverse()) {
      for (const key of merged[index] ?? []) {
        group.add(key)
      }
      merged.splice(index, 1)
    }

    merged.push(group)
  }
  return merged
}

function keysForMembers(members: string[]): Set<string> {
  const keys = new Set<string>()
  for (const member of members) {
    for (const key of courseNumberKeys(member)) {
      keys.add(key)
    }
  }
  return keys
}

export function knownCrossTrackEquivalenceGroups(): Array<Set<string>> {
  return KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS.map((members) => keysForMembers(members))
}

export function crossTrackEquivalenceGroupsFromGraph(
  curriculumGraph?: CurriculumGraph | null,
): Array<Set<string>> {
  const fromApi = curriculumGraph?.crossTrackEquivalenceGroups ?? []
  if (fromApi.length) {
    return fromApi.map((members) => keysForMembers(members))
  }
  return knownCrossTrackEquivalenceGroups()
}

export function buildMandatoryEquivalenceGroups(options?: {
  curriculumGraph?: CurriculumGraph | null
  remainingMandatory?: Array<{ courseNumber?: string | null }>
  completedMandatory?: Array<{ courseNumber?: string | null }>
}): Array<Set<string>> {
  const groups: Array<Set<string>> = [...crossTrackEquivalenceGroupsFromGraph(options?.curriculumGraph)]

  const relevantKeys = new Set<string>()
  for (const course of [
    ...(options?.remainingMandatory ?? []),
    ...(options?.completedMandatory ?? []),
  ]) {
    for (const key of courseNumberKeys(course.courseNumber ?? '')) {
      relevantKeys.add(key)
    }
  }

  for (const node of options?.curriculumGraph?.nodes ?? []) {
    const members = [node.courseNumber, ...(node.alternatives ?? [])]
    const memberKeys = members.flatMap((member) => [...courseNumberKeys(member)])
    if (memberKeys.some((key) => relevantKeys.has(key))) {
      groups.push(keysForMembers(members))
    }
  }

  return mergeOverlappingEquivalenceGroups(groups)
}

export function buildCourseEquivalenceGroups(options?: {
  curriculumGraph?: CurriculumGraph | null
  poolCourses?: ElectivePoolCourse[]
}): Array<Set<string>> {
  const groups: Array<Set<string>> = []

  for (const node of options?.curriculumGraph?.nodes ?? []) {
    groups.push(keysForMembers([node.courseNumber, ...(node.alternatives ?? [])]))
  }

  for (const course of options?.poolCourses ?? []) {
    groups.push(keysForMembers([course.courseNumber, ...(course.alternatives ?? [])]))
  }

  groups.push(...crossTrackEquivalenceGroupsFromGraph(options?.curriculumGraph))
  return mergeOverlappingEquivalenceGroups(groups)
}

export function equivalenceGroupForCourse(
  courseNumber: string,
  groups: Array<Set<string>>,
): Set<string> | null {
  const keys = new Set(courseNumberKeys(courseNumber))
  return groups.find((group) => [...keys].some((key) => group.has(key))) ?? null
}

export function equivalenceGroupKey(group: Set<string>): string {
  return [...group].sort().join('|')
}

export function expandNumbersWithEquivalence(
  numbers: Set<string>,
  groups: Array<Set<string>>,
): Set<string> {
  const expanded = new Set(numbers)
  for (const number of numbers) {
    const group = equivalenceGroupForCourse(number, groups)
    if (group) {
      for (const key of group) {
        expanded.add(key)
      }
    }
  }
  return expanded
}

export function isCountedViaEquivalence(
  courseNumber: string,
  countedNumbers: Set<string>,
  groups: Array<Set<string>>,
): boolean {
  const expanded = expandNumbersWithEquivalence(countedNumbers, groups)
  return courseNumberKeys(courseNumber).some((key) => expanded.has(key))
}

export function dedupeEquivalentPoolCourses(
  courses: ElectivePoolCourse[],
  options: {
    countedNumbers: Set<string>
    requiredCurriculumNumbers?: Set<string>
    curriculumGraph?: CurriculumGraph | null
  },
): ElectivePoolCourse[] {
  const groups = buildCourseEquivalenceGroups({
    curriculumGraph: options.curriculumGraph,
    poolCourses: courses,
  })
  const countedExpanded = expandNumbersWithEquivalence(options.countedNumbers, groups)
  const required = options.requiredCurriculumNumbers ?? new Set<string>()
  const seenGroupKeys = new Set<string>()
  const result: ElectivePoolCourse[] = []

  for (const course of courses) {
    const group = equivalenceGroupForCourse(course.courseNumber, groups)
    if (!group) {
      result.push(course)
      continue
    }

    const groupKey = equivalenceGroupKey(group)
    if (seenGroupKeys.has(groupKey)) continue

    const members = courses.filter(
      (entry) => equivalenceGroupForCourse(entry.courseNumber, groups) === group,
    )
    const countedMembers = members.filter((entry) =>
      isCountedViaEquivalence(entry.courseNumber, countedExpanded, groups),
    )

    if (countedMembers.length) {
      const preferred =
        countedMembers.find((entry) =>
          courseNumberKeys(entry.courseNumber).some((key) => options.countedNumbers.has(key)),
        ) ?? countedMembers[0]
      result.push(preferred!)
      seenGroupKeys.add(groupKey)
      continue
    }

    const preferred =
      members.find((entry) =>
        courseNumberKeys(entry.courseNumber).some((key) => required.has(key)),
      ) ?? members[0]
    result.push(preferred!)
    seenGroupKeys.add(groupKey)
  }

  return result
}
