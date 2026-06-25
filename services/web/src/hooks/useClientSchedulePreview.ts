import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { catalogApi } from '../api/endpoints'
import {
  buildClientWeeklySchedule,
  eventsFromOffering,
  type ClientScheduleCourse,
} from '../lib/clientSchedulePreview'
import { buildClientExamSummary } from '../lib/clientExamSummary'
import { courseNumberKeys, lookupByCourseNumberKeys } from '../lib/courseNumbers'

import type { CustomEvent } from '../types/api'

type UseClientSchedulePreviewArgs = {
  courses: ClientScheduleCourse[]
  academicYear?: number
  semesterCode?: number
  customEvents?: CustomEvent[]
}

function offeringIsMissing<T extends { scheduleGroups?: unknown[] }>(
  offeringsByCourse: Record<string, T>,
  courseNumber: string,
): boolean {
  const offering = lookupByCourseNumberKeys(offeringsByCourse, courseNumber)
  return !offering?.scheduleGroups?.length
}

export function useClientSchedulePreview({
  courses,
  academicYear,
  semesterCode,
  customEvents = [],
}: UseClientSchedulePreviewArgs) {
  const activeCourses = courses.filter((course) => course.courseNumber)
  const courseNumbersKey = activeCourses
    .map((course) => course.courseNumber)
    .sort()
    .join(',')

  const offeringsQuery = useQuery({
    queryKey: ['client-schedule-offerings', academicYear, semesterCode, courseNumbersKey],
    queryFn: async () => {
      const courseNumbers = activeCourses.map((course) => course.courseNumber)
      const response = await catalogApi.offeringsBatch(courseNumbers, {
        academicYear: academicYear!,
        semesterCode: semesterCode!,
      })

      const offeringsByCourse = Object.fromEntries(
        Object.entries(response.offeringsByCourseNumber).map(([courseNumber, offerings]) => [
          courseNumber,
          offerings[0],
        ]),
      )

      return {
        offeringsByCourse,
        missingOfferings: courseNumbers.filter((courseNumber) =>
          offeringIsMissing(offeringsByCourse, courseNumber),
        ),
      }
    },
    enabled: Boolean(academicYear && semesterCode && activeCourses.length),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  })

  const data = useMemo(() => {
    if (!offeringsQuery.data || activeCourses.length === 0) return undefined

    const offeringsByCourse = offeringsQuery.data.offeringsByCourse
    const allEvents = activeCourses.flatMap((course) =>
      eventsFromOffering(
        { ...course, isActive: course.isActive ?? true },
        lookupByCourseNumberKeys(offeringsByCourse, course.courseNumber),
      ),
    )

    return {
      schedule: buildClientWeeklySchedule(allEvents, customEvents),
      offeringsByCourse,
      missingOfferings: offeringsQuery.data.missingOfferings.filter((courseNumber) =>
        activeCourses.some((course) => courseNumberKeys(course.courseNumber).includes(courseNumber)),
      ),
      examSummary: buildClientExamSummary(
        activeCourses,
        Object.fromEntries(
          activeCourses.flatMap((course) => {
            const offering = lookupByCourseNumberKeys(offeringsByCourse, course.courseNumber)
            return offering ? [[course.courseNumber, offering]] : []
          }),
        ),
      ),
    }
  }, [activeCourses, customEvents, offeringsQuery.data])

  return {
    ...offeringsQuery,
    data,
  }
}
