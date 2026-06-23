import { useQuery } from '@tanstack/react-query'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { catalogApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import { courseTitle } from '../../lib/planning'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Card'
import { CourseDetailBody } from '../catalog/CourseDetailBody'

type CourseDetailModalProps = {
  courseNumber: string | null
  academicYear?: number
  semesterCode?: number
  onClose: () => void
}

export function CourseDetailModal({
  courseNumber,
  academicYear,
  semesterCode,
  onClose,
}: CourseDetailModalProps) {
  const { t, locale } = useTranslation()

  const detailQuery = useQuery({
    queryKey: ['course-detail', courseNumber, academicYear, semesterCode],
    queryFn: async () => {
      const detail = await catalogApi.course(courseNumber!, true)
      if (academicYear && semesterCode) {
        const offerings = await catalogApi.offerings(courseNumber!, {
          academicYear,
          semesterCode,
        })
        return {
          ...detail.course,
          offerings: offerings.offerings.length
            ? offerings.offerings
            : detail.course.offerings ?? [],
        }
      }
      return detail.course
    },
    enabled: Boolean(courseNumber),
  })

  if (!courseNumber) return null

  const course = detailQuery.data

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="course-detail-title"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-[var(--color-primary)]">{courseNumber}</p>
            <h2 id="course-detail-title" className="text-lg font-semibold">
              {course ? courseTitle(course, locale) : '…'}
            </h2>
          </div>
          <Button variant="ghost" size="sm" aria-label={t('common.cancel')} onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {detailQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : detailQuery.isError || !course ? (
          <p className="text-sm text-[var(--color-danger)]">{t('common.errorGeneric')}</p>
        ) : (
          <CourseDetailBody course={course} />
        )}
      </div>
    </div>,
    document.body,
  )
}
