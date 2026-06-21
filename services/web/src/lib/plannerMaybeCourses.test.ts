import { describe, expect, it } from 'vitest'
import type { DraftCourse, PlannerSnapshot } from '../types/planner'
import {
  activeDraftCourses,
  addMaybeCourseToSnapshot,
  buildMaybePersistSignature,
  buildPlannerPersistSignature,
  buildSelectedPersistSignature,
  draftCoursesFromPlanned,
  filterSearchItemsForPlanner,
  hydratePlannerFromServer,
  isCourseInPlannerLists,
  moveMaybeToSelectedSnapshot,
  moveSelectedToMaybeSnapshot,
  plannedCoursesForSave,
  previewCourseNumbers,
  removeMaybeCourseFromSnapshot,
  savePayloadCourseIds,
  savePayloadMaybeCourseIds,
  updateMaybeCourseLessons,
} from './plannerMaybeCourses'

const courseA: DraftCourse = {
  courseId: 'a1',
  courseNumber: '02340117',
  courseTitle: 'Course A',
  credits: 4,
  isActive: true,
}

const courseB: DraftCourse = {
  courseId: 'b1',
  courseNumber: '02340114',
  courseTitle: 'Course B',
  credits: 3,
  isActive: true,
}

const emptySnapshot = (): PlannerSnapshot => ({
  courses: [],
  maybeCourses: [],
  customEvents: [],
})

describe('plannerMaybeCourses', () => {
  it('detects course membership across selected and maybe lists', () => {
    expect(isCourseInPlannerLists([courseA], [], 'a1')).toBe(true)
    expect(isCourseInPlannerLists([], [courseB], 'b1')).toBe(true)
    expect(isCourseInPlannerLists([courseA], [courseB], 'missing')).toBe(false)
  })

  it('moves selected → maybe atomically without losing the course', () => {
    const start: PlannerSnapshot = { courses: [courseA], maybeCourses: [], customEvents: [] }
    const next = moveSelectedToMaybeSnapshot(start, 'a1')

    expect(next.courses).toHaveLength(0)
    expect(next.maybeCourses).toEqual([courseA])
  })

  it('moves maybe → selected atomically', () => {
    const start: PlannerSnapshot = { courses: [], maybeCourses: [courseB], customEvents: [] }
    const next = moveMaybeToSelectedSnapshot(start, 'b1')

    expect(next.maybeCourses).toHaveLength(0)
    expect(next.courses).toEqual([courseB])
  })

  it('ignores move when course id is missing', () => {
    const start: PlannerSnapshot = { courses: [courseA], maybeCourses: [], customEvents: [] }
    expect(moveSelectedToMaybeSnapshot(start, 'missing')).toBe(start)
    expect(moveMaybeToSelectedSnapshot(start, 'missing')).toBe(start)
  })

  it('prevents duplicate maybe adds', () => {
    const start: PlannerSnapshot = { courses: [courseA], maybeCourses: [], customEvents: [] }
    expect(addMaybeCourseToSnapshot(start, courseA)).toBe(start)
  })

  it('adds a new course to maybe when not already listed', () => {
    const next = addMaybeCourseToSnapshot(emptySnapshot(), courseB)
    expect(next.maybeCourses).toEqual([courseB])
  })

  it('removes maybe courses by id', () => {
    const start: PlannerSnapshot = { courses: [], maybeCourses: [courseA, courseB], customEvents: [] }
    const next = removeMaybeCourseFromSnapshot(start, 'a1')
    expect(next.maybeCourses).toEqual([courseB])
  })

  it('updates maybe lesson selections locally', () => {
    const start: PlannerSnapshot = { courses: [], maybeCourses: [courseA], customEvents: [] }
    const events = [{ eventId: 'ev-1', type: 'lecture', group: '10' }]
    const next = updateMaybeCourseLessons(start, courseA.courseNumber, events, 'Lecture 10')

    expect(next.maybeCourses[0].selectedLessonEvents).toEqual(events)
    expect(next.maybeCourses[0].groupSummary).toBe('Lecture 10')
  })

  it('builds preview course numbers from selected and maybe lists', () => {
    const inactive: DraftCourse = { ...courseB, isActive: false }
    expect(previewCourseNumbers([courseA], [inactive])).toEqual(['02340117'])
    expect(previewCourseNumbers([courseA], [courseB])).toEqual(['02340117', '02340114'])
  })

  it('filters search results when hideSelected includes maybe list', () => {
    const items = [
      { id: 'a1', courseNumber: '02340117' },
      { id: 'b1', courseNumber: '02340114' },
      { id: 'c1', courseNumber: '00999999' },
    ]
    const snapshot: PlannerSnapshot = {
      courses: [courseA],
      maybeCourses: [courseB],
      customEvents: [],
    }

    expect(filterSearchItemsForPlanner(items, snapshot, true)).toEqual([{ id: 'c1', courseNumber: '00999999' }])
    expect(filterSearchItemsForPlanner(items, snapshot, false)).toEqual(items)
  })

  it('save payload includes selected and maybe courses in separate fields', () => {
    const payload = {
      semesters: [
        {
          plannedCourses: plannedCoursesForSave([courseA]),
          maybeCourses: plannedCoursesForSave([courseB]),
        },
      ],
    }
    expect(savePayloadCourseIds(payload)).toEqual(['a1'])
    expect(savePayloadMaybeCourseIds(payload)).toEqual(['b1'])
    expect(savePayloadMaybeCourseIds({ semesters: [{ maybeCourses: plannedCoursesForSave([]) }] })).toEqual(
      [],
    )
  })

  it('buildPlannerPersistSignature tracks lesson selections in both lists', () => {
    const withLessons: DraftCourse = {
      ...courseA,
      selectedLessonEvents: [{ eventId: 'ev-1', type: 'lecture', group: '10' }],
    }
    const sigA = buildPlannerPersistSignature([withLessons], [])
    const sigB = buildPlannerPersistSignature([courseA], [])
    expect(sigA).not.toBe(sigB)

    const sigMaybe = buildPlannerPersistSignature([], [withLessons])
    expect(buildPlannerPersistSignature([], [withLessons])).toBe(sigMaybe)
  })

  it('buildPlannerPersistSignature separates selected and maybe lists', () => {
    const selectedOnly = buildPlannerPersistSignature([courseA], [])
    const maybeOnly = buildPlannerPersistSignature([], [courseA])
    expect(selectedOnly).not.toBe(maybeOnly)
  })

  it('draftCoursesFromPlanned maps server planned courses to draft shape', () => {
    const drafts = draftCoursesFromPlanned([
      {
        courseId: 'a1',
        courseNumber: '02340117',
        courseTitle: 'Course A',
        credits: 4,
        isActive: true,
      },
    ])
    expect(drafts).toEqual([courseA])
  })

  it('hydrates maybe courses from server when provided', () => {
    const local: PlannerSnapshot = {
      courses: [],
      maybeCourses: [courseB],
      customEvents: [{ id: '1', title: 'Gym', day: 'Sunday', startTime: '08:00', endTime: '09:00' }],
    }
    const hydrated = hydratePlannerFromServer(local, [courseA], [courseB])

    expect(hydrated.courses).toEqual([courseA])
    expect(hydrated.maybeCourses).toEqual([courseB])
    expect(hydrated.customEvents).toEqual(local.customEvents)
  })

  it('preserves local maybe courses when server maybe list is omitted', () => {
    const local: PlannerSnapshot = {
      courses: [],
      maybeCourses: [courseB],
      customEvents: [],
    }
    const hydrated = hydratePlannerFromServer(local, [courseA])

    expect(hydrated.courses).toEqual([courseA])
    expect(hydrated.maybeCourses).toEqual([courseB])
  })

  it('activeDraftCourses excludes inactive entries', () => {
    expect(activeDraftCourses([courseA, { ...courseB, isActive: false }])).toEqual([courseA])
  })
})
