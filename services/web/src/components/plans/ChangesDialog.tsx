import { X } from 'lucide-react'
import type { PlanChangeItem } from '../../types/planner'
import { useTranslation } from '../../i18n'
import { Button } from '../ui/Button'

type ChangesDialogProps = {
  changes: PlanChangeItem[]
  onClose: () => void
}

export function ChangesDialog({ changes, onClose }: ChangesDialogProps) {
  const { t } = useTranslation()

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center print:hidden"
      role="dialog"
      aria-modal="true"
      aria-label={t('planner.changesTitle')}
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">{t('planner.changesTitle')}</h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('planner.changesHint')}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={t('common.close')}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {changes.length ? (
          <ul className="space-y-2">
            {changes.map((change) => (
              <li
                key={change.id}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-3 py-2 text-sm"
              >
                {change.courseNumber ? (
                  <p className="font-mono text-xs text-[var(--color-primary)]">{change.courseNumber}</p>
                ) : null}
                <p>{change.message}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">{t('planner.noChanges')}</p>
        )}

        <div className="mt-6 flex justify-end">
          <Button onClick={onClose}>{t('common.close')}</Button>
        </div>
      </div>
    </div>
  )
}
