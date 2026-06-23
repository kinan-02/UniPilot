import { useTranslation } from '../../i18n'
import { formatCredits } from '../../lib/utils'
import type { CourseDetail } from '../../types/api'

type CourseDetailBodyProps = {
  course: CourseDetail
}

function DetailSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details open={defaultOpen} className="group rounded-xl border border-[var(--color-border)] bg-white/70">
      <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] marker:content-none [&::-webkit-details-marker]:hidden">
        {title}
      </summary>
      <div className="border-t border-[var(--color-border)] px-4 py-3">{children}</div>
    </details>
  )
}

export function CourseDetailBody({ course }: CourseDetailBodyProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3 text-sm">
      <DetailSection title={t('catalog.sectionOverview')} defaultOpen>
        <dl className="space-y-3">
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
          {course.instructors ? (
            <div>
              <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.instructors')}</dt>
              <dd>{course.instructors}</dd>
            </div>
          ) : null}
        </dl>
      </DetailSection>

      {course.syllabus ? (
        <DetailSection title={t('planner.syllabus')}>
          <p className="whitespace-pre-wrap text-[var(--color-text-muted)]">{course.syllabus}</p>
        </DetailSection>
      ) : null}

      {course.prerequisitesText || course.corequisitesText || course.noAdditionalCreditText ? (
        <DetailSection title={t('catalog.sectionRequirements')}>
          <dl className="space-y-3">
            {course.prerequisitesText ? (
              <div>
                <dt className="text-xs font-medium text-[var(--color-text-muted)]">{t('planner.prerequisites')}</dt>
                <dd className="whitespace-pre-wrap">{course.prerequisitesText}</dd>
                <p className="mt-1 text-xs text-[var(--color-warning)]">{t('planner.prereqManualVerify')}</p>
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
          </dl>
        </DetailSection>
      ) : null}

      {course.notes ? (
        <DetailSection title={t('planner.notes')} defaultOpen={false}>
          <p className="whitespace-pre-wrap">{course.notes}</p>
        </DetailSection>
      ) : null}

      <DetailSection title={t('catalog.offerings')}>
        {course.offerings?.length ? (
          <div className="space-y-2">
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
                        {(group.day || group.יום) ?? ''} {(group.time || group.שעה) ?? ''}{' '}
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
          </div>
        ) : (
          <p className="text-xs text-[var(--color-text-muted)]">{t('catalog.noOfferings')}</p>
        )}
      </DetailSection>
    </div>
  )
}
