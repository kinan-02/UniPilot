import { useTranslation } from '../../i18n'
import type { PlannerFilters } from '../../types/planner'
import { Input } from '../ui/Input'

type CourseFiltersPanelProps = {
  filters: PlannerFilters
  onChange: (patch: Partial<PlannerFilters>) => void
  expanded: boolean
  onToggleExpanded: () => void
  disabled?: boolean
  hideToggle?: boolean
}

export function CourseFiltersPanel({
  filters,
  onChange,
  expanded,
  onToggleExpanded,
  disabled,
  hideToggle = false,
}: CourseFiltersPanelProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      {hideToggle ? null : (
        <button
          type="button"
          className="text-xs font-semibold uppercase tracking-wide text-[var(--color-primary)]"
          onClick={onToggleExpanded}
          disabled={disabled}
        >
          {expanded ? t('planner.hideFilters') : t('planner.showFilters')}
        </button>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          label={t('catalog.faculty')}
          value={filters.faculty}
          onChange={(e) => onChange({ faculty: e.target.value })}
          placeholder={t('catalog.allFaculties')}
          disabled={disabled}
        />
        <Input
          label={t('planner.minCredits')}
          type="number"
          step="0.5"
          value={filters.minCredits}
          onChange={(e) => onChange({ minCredits: e.target.value })}
          disabled={disabled}
        />
        <Input
          label={t('planner.maxCreditsFilter')}
          type="number"
          step="0.5"
          value={filters.maxCredits}
          onChange={(e) => onChange({ maxCredits: e.target.value })}
          disabled={disabled}
        />
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t('planner.slotTypeFilter')}</span>
          <select
            className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm disabled:opacity-60"
            value={filters.slotType}
            onChange={(e) => onChange({ slotType: e.target.value })}
            disabled={disabled}
          >
            <option value="">{t('planner.slotTypeAll')}</option>
            <option value="lecture">{t('planner.slot.lecture')}</option>
            <option value="tutorial">{t('planner.slot.tutorial')}</option>
            <option value="lab">{t('planner.slot.lab')}</option>
          </select>
        </label>
      </div>

      {expanded ? (
        <div className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-3">
          <p className="text-xs text-[var(--color-text-muted)]">{t('planner.filtersExperimentalHint')}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <FilterCheckbox
              label={t('planner.hideMissingPrereqs')}
              checked={filters.hideMissingPrereqs}
              onChange={(checked) => onChange({ hideMissingPrereqs: checked })}
              disabled={disabled}
            />
            <FilterCheckbox
              label={t('planner.hideMissingCoreqs')}
              checked={filters.hideMissingCoreqs}
              onChange={(checked) => onChange({ hideMissingCoreqs: checked })}
              disabled={disabled}
            />
            <FilterCheckbox
              label={t('planner.hideNoCreditConflicts')}
              checked={filters.hideNoCreditConflicts}
              onChange={(checked) => onChange({ hideNoCreditConflicts: checked })}
              disabled={disabled}
            />
            <FilterCheckbox
              label={t('planner.hideWithExam')}
              checked={filters.hideWithExam}
              onChange={(checked) => onChange({ hideWithExam: checked })}
              disabled={disabled}
            />
            <FilterCheckbox
              label={t('planner.hideWithoutExam')}
              checked={filters.hideWithoutExam}
              onChange={(checked) => onChange({ hideWithoutExam: checked })}
              disabled={disabled}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t('planner.includeOnlyCourses')}
              value={filters.includeOnly}
              onChange={(e) => onChange({ includeOnly: e.target.value })}
              placeholder="02340114, 104031"
              disabled={disabled}
            />
            <Input
              label={t('planner.excludeCourses')}
              value={filters.exclude}
              onChange={(e) => onChange({ exclude: e.target.value })}
              placeholder="104166"
              disabled={disabled}
            />
          </div>
          <button
            type="button"
            className="text-xs text-[var(--color-primary)] underline disabled:opacity-50"
            disabled={disabled}
            onClick={() =>
              onChange({
                faculty: '',
                minCredits: '',
                maxCredits: '',
                slotType: '',
                hideMissingPrereqs: false,
                hideMissingCoreqs: false,
                hideNoCreditConflicts: false,
                includeOnly: '',
                exclude: '',
                moedAFrom: '',
                moedATo: '',
                moedBFrom: '',
                moedBTo: '',
                hideWithExam: false,
                hideWithoutExam: false,
              })
            }
          >
            {t('planner.clearFilters')}
          </button>
        </div>
      ) : null}

      <FilterCheckbox
        label={t('planner.hideSelected')}
        checked={filters.hideSelected}
        onChange={(checked) => onChange({ hideSelected: checked })}
        disabled={disabled}
      />
    </div>
  )
}

function FilterCheckbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      {label}
    </label>
  )
}
