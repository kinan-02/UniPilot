import { Download, History, Redo2, Save, Undo2 } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { SemesterPicker } from './SemesterPicker'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

type PlannerTopBarProps = {
  semesterCode: string
  onSemesterChange: (value: string) => void
  semesterError?: string
  planName: string
  onPlanNameChange: (value: string) => void
  planNameError?: string
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onExportIcs?: () => void
  onSave: () => void
  onShowChanges?: () => void
  changesCount?: number
  saving?: boolean
  exportDisabled?: boolean
  readOnly?: boolean
}

export function PlannerTopBar({
  semesterCode,
  onSemesterChange,
  semesterError,
  planName,
  onPlanNameChange,
  planNameError,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onExportIcs,
  onSave,
  onShowChanges,
  changesCount = 0,
  saving,
  exportDisabled,
  readOnly,
}: PlannerTopBarProps) {
  const { t } = useTranslation()

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 shadow-[var(--shadow-soft)] print:hidden">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <SemesterPicker value={semesterCode} onChange={onSemesterChange} error={semesterError} disabled={readOnly} />
          <Input
            label={t('plans.planName')}
            value={planName}
            onChange={(e) => onPlanNameChange(e.target.value)}
            error={planNameError}
            required
            disabled={readOnly}
            className="h-9 min-w-[200px] text-sm"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!readOnly ? (
            <>
              <Button variant="ghost" size="sm" disabled={!canUndo} onClick={onUndo} aria-label={t('planner.undo')}>
                <Undo2 className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" disabled={!canRedo} onClick={onRedo} aria-label={t('planner.redo')}>
                <Redo2 className="h-4 w-4" />
              </Button>
            </>
          ) : null}
          {onShowChanges ? (
            <Button variant="secondary" size="sm" onClick={onShowChanges} aria-label={t('planner.changesTitle')}>
              <History className="h-4 w-4" />
              {t('planner.changes')}
              {changesCount ? ` (${changesCount})` : ''}
            </Button>
          ) : null}
          {onExportIcs ? (
            <Button variant="secondary" size="sm" onClick={onExportIcs} disabled={exportDisabled} aria-label={t('planner.exportIcs')}>
              <Download className="h-4 w-4" />
              {t('planner.exportIcsShort')}
            </Button>
          ) : null}
          {!readOnly ? (
            <Button size="sm" loading={saving} onClick={onSave}>
              <Save className="h-4 w-4" />
              {t('plans.savePlan')}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
