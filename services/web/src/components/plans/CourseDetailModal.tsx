import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { catalogApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import { courseTitle } from '../../lib/planning'
import { formatCredits } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Card'

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

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
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
          <dl className="space-y-4 text-sm">
            {course.faculty ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('catalog.faculty')}</dt>
                <dd>{course.faculty}</dd>
              </div>
            ) : null}
            {course.credits != null ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('catalog.credits')}</dt>
                <dd>{formatCredits(course.credits)}</dd>
              </div>
            ) : null}
            {course.syllabus ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.syllabus')}</dt>
                <dd className="whitespace-pre-wrap text-[var(--color-text-muted)]">{course.syllabus}</dd>
              </div>
            ) : null}
            {course.prerequisitesText ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.prerequisites')}</dt>
                <dd className="whitespace-pre-wrap">{course.prerequisitesText}</dd>
              </div>
            ) : null}
            {course.corequisitesText ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.corequisites')}</dt>
                <dd className="whitespace-pre-wrap">{course.corequisitesText}</dd>
              </div>
            ) : null}
            {course.noAdditionalCreditText ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.noAdditionalCredit')}</dt>
                <dd className="whitespace-pre-wrap">{course.noAdditionalCreditText}</dd>
              </div>
            ) : null}
            {course.instructors ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.instructors')}</dt>
                <dd>{course.instructors}</dd>
              </div>
            ) : null}
            {course.notes ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.notes')}</dt>
                <dd className="whitespace-pre-wrap">{course.notes}</dd>
              </div>
            ) : null}
            {course.offerings?.length ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('catalog.offerings')}</dt>
                <dd className="space-y-2">
                  {course.offerings.map((offering, index) => (
                    <div
                      key={`${offering.academicYear}-${offering.semesterCode}-${index}`}
                      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-3 py-2"
                    >
                      <p className="text-xs text-[var(--color-text-muted)]">
                        {offering.academicYear} · {offering.semesterCode}
                        {offering.instructors ? ` · ${offering.instructors}` : ''}
                      </p>
                      {offering.scheduleGroups?.length ? (
                        <ul className="mt-1 space-y-0.5 text-xs">
                          {offering.scheduleGroups.map((group, slotIndex) => (
                            <li key={slotIndex}>
                              {(group.day || group.יום) ?? ''}{' '}
                              {(group.time || group.שעה) ?? ''}{' '}
                              {(group.type || group.סוג) ?? ''}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {offering.examDates && Object.keys(offering.examDates).length ? (
                        <p className="mt-1 text-xs">
                          {t('planner.exams')}:{' '}
                          {Object.entries(offering.examDates)
                            .filter(([, value]) => value)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join(' · ')}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </dd>
              </div>
            ) : (
              <p className="text-xs text-[var(--color-text-muted)]">{t('planner.noOfferingsSemester')}</p>
            )}
          </dl>
        )}
      </div>
    </div>
  )
}
