import type { CourseSummary } from '../../types/api'
import type { Locale } from '../../i18n/types'
import type { PlannerFilters } from '../../types/planner'
import { useTranslation } from '../../i18n'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { CourseFiltersPanel } from './CourseFiltersPanel'
import { CourseSearchPanel } from './CourseSearchPanel'

type PlannerCourseSearchProps = {
  locale: Locale
  searchQuery: string
  onSearchQueryChange: (value: string) => void
  semesterSelected: boolean
  searchMinLength: number
  debouncedSearch: string
  loading: boolean
  error: boolean
  items: CourseSummary[]
  selectedCourseNumbers: Set<string>
  maybeCourseNumbers: Set<string>
  onAdd: (course: CourseSummary) => void
  onAddMaybe: (course: CourseSummary) => void
  onInfo: (courseNumber: string) => void
  filters: PlannerFilters
  onFiltersChange: (patch: Partial<PlannerFilters>) => void
  filtersExpanded: boolean
  onToggleFilters: () => void
}

export function PlannerCourseSearch({
  locale,
  searchQuery,
  onSearchQueryChange,
  semesterSelected,
  searchMinLength,
  debouncedSearch,
  loading,
  error,
  items,
  selectedCourseNumbers,
  maybeCourseNumbers,
  onAdd,
  onAddMaybe,
  onInfo,
  filters,
  onFiltersChange,
  filtersExpanded,
  onToggleFilters,
}: PlannerCourseSearchProps) {
  const { t } = useTranslation()
  const isSearching = debouncedSearch.length >= searchMinLength

  return (
    <Card className="print:hidden">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <Input
            label={t('planner.searchTitle')}
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            placeholder={t('planner.searchPlaceholder')}
            disabled={!semesterSelected}
          />
        </div>
        <button
          type="button"
          className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[var(--color-primary)] sm:pb-2"
          onClick={onToggleFilters}
          disabled={!semesterSelected}
        >
          {filtersExpanded ? t('planner.hideFilters') : t('planner.showFilters')}
        </button>
      </div>

      {filtersExpanded ? (
        <div className="mt-3 border-t border-[var(--color-border)] pt-3">
          <CourseFiltersPanel
            filters={filters}
            onChange={onFiltersChange}
            expanded
            onToggleExpanded={onToggleFilters}
            disabled={!semesterSelected}
            hideToggle
          />
        </div>
      ) : null}

      {isSearching || loading ? (
        <div className="mt-3 border-t border-[var(--color-border)] pt-3">
          <CourseSearchPanel
            locale={locale}
            searchMinLength={searchMinLength}
            debouncedSearch={debouncedSearch}
            loading={loading}
            error={error}
            items={items}
            selectedCourseNumbers={selectedCourseNumbers}
            maybeCourseNumbers={maybeCourseNumbers}
            onAdd={onAdd}
            onAddMaybe={onAddMaybe}
            onInfo={onInfo}
            disabled={!semesterSelected}
            listClassName="max-h-52 space-y-2 overflow-y-auto sm:max-h-60"
          />
        </div>
      ) : !semesterSelected ? (
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{t('planner.selectSemesterFirst')}</p>
      ) : (
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{t('plans.searchCourseHint')}</p>
      )}
    </Card>
  )
}
