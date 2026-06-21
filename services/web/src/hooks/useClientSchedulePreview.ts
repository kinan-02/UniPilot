import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { catalogApi } from '../api/endpoints'
import {
  buildClientWeeklySchedule,
  eventsFromOffering,
  type ClientScheduleCourse,
} from '../lib/clientSchedulePreview'

import type { CustomEvent } from '../types/api'

type UseClientSchedulePreviewArgs = {
  courses: ClientScheduleCourse[]
  academicYear?: number
  semesterCode?: number
  customEvents?: CustomEvent[]
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
        missingOfferings: courseNumbers.filter(
          (courseNumber) => !offeringsByCourse[courseNumber]?.scheduleGroups?.length,
        ),
      }
    },
    enabled: Boolean(academicYear && semesterCode && activeCourses.length),
    staleTime: 30_000,
  })

  const data = useMemo(() => {
    if (!offeringsQuery.data) return undefined

    const allEvents = activeCourses.flatMap((course) =>
      eventsFromOffering(
        { ...course, isActive: course.isActive ?? true },
        offeringsQuery.data!.offeringsByCourse[course.courseNumber],
      ),
    )

    return {
      schedule: buildClientWeeklySchedule(allEvents, customEvents),
      offeringsByCourse: offeringsQuery.data.offeringsByCourse,
      missingOfferings: offeringsQuery.data.missingOfferings,
    }
  }, [activeCourses, customEvents, offeringsQuery.data])

  return {
    ...offeringsQuery,
    data,
  }
}
