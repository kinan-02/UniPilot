import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { catalogApi } from '../../api/endpoints'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useTranslation } from '../../i18n'
import { courseTitle } from '../../lib/planning'
import type { CourseSummary } from '../../types/api'
import { cn } from '../../lib/utils'

type CourseSearchComboboxProps = {
  onSelect: (course: CourseSummary) => void
  excludeIds?: string[]
  placeholder?: string
  hint?: string
  className?: string
}

export function CourseSearchCombobox({
  onSelect,
  excludeIds = [],
  placeholder,
  hint,
  className,
}: CourseSearchComboboxProps) {
  const { t, locale } = useTranslation()
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const debounced = useDebouncedValue(query.trim(), 280)

  const searchQuery = useQuery({
    queryKey: ['course-search', debounced],
    queryFn: () => {
      const params: Record<string, string | number | boolean> = {
        q: debounced,
        limit: 12,
        offset: 0,
      }
      if (/^0\d{7}$/.test(debounced)) {
        params.courseNumber = debounced
      }
      return catalogApi.courses(params)
    },
    enabled: debounced.length >= 2,
  })

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const items = (searchQuery.data?.items ?? []).filter(
    (course) => course.id && !excludeIds.includes(course.id),
  )

  const handlePick = (course: CourseSummary) => {
    onSelect(course)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <label className="sr-only" htmlFor={listId}>
        {placeholder ?? t('plans.searchCourse')}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          id={listId}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? t('plans.searchCourse')}
          className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm transition focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${listId}-list`}
        />
      </div>
      {hint ? <p className="mt-1.5 text-xs text-[var(--color-text-muted)]">{hint}</p> : null}
      {open && debounced.length >= 2 ? (
        <ul
          id={`${listId}-list`}
          role="listbox"
          className="absolute z-20 mt-2 max-h-72 w-full overflow-auto rounded-xl border border-[var(--color-border)] bg-white py-1 shadow-[var(--shadow-card)]"
        >
          {searchQuery.isLoading ? (
            <li className="px-4 py-3 text-sm text-[var(--color-text-muted)]">{t('common.loading')}</li>
          ) : items.length ? (
            items.map((course) => (
              <li key={course.courseNumber}>
                <button
                  type="button"
                  role="option"
                  className="flex w-full flex-col gap-0.5 px-4 py-3 text-start transition hover:bg-[var(--color-surface-muted)]"
                  onClick={() => handlePick(course)}
                >
                  <span className="font-mono text-xs text-[var(--color-primary)]">{course.courseNumber}</span>
                  <span className="text-sm">{courseTitle(course, locale)}</span>
                  {course.faculty ? (
                    <span className="text-xs text-[var(--color-text-muted)]">{course.faculty}</span>
                  ) : null}
                </button>
              </li>
            ))
          ) : (
            <li className="px-4 py-3 text-sm text-[var(--color-text-muted)]">{t('common.noResults')}</li>
          )}
        </ul>
      ) : null}
    </div>
  )
}
