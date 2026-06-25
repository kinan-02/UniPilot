import { Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from '../../i18n'
import { validateCredits, validateSemesterCode } from '../../lib/validation'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'

type PlannerAutoAssistPanelProps = {
  semesterCode: string
  semesterSelected: boolean
  defaultMaxCredits?: number
  pickingCourses: boolean
  statusMessage?: string
  statusTone?: 'success' | 'warning'
  errorMessage?: string
  onAutoPickCourses: (maxCredits: number) => void
}

export function PlannerAutoAssistPanel({
  semesterCode,
  semesterSelected,
  defaultMaxCredits,
  pickingCourses,
  statusMessage,
  statusTone = 'success',
  errorMessage,
  onAutoPickCourses,
}: PlannerAutoAssistPanelProps) {
  const { t } = useTranslation()
  const [maxCredits, setMaxCredits] = useState(String(defaultMaxCredits ?? 18))
  const [maxCreditsTouched, setMaxCreditsTouched] = useState(false)
  const [localError, setLocalError] = useState('')

  useEffect(() => {
    if (!maxCreditsTouched && defaultMaxCredits != null) {
      setMaxCredits(String(defaultMaxCredits))
    }
  }, [defaultMaxCredits, maxCreditsTouched])

  const handleAutoPick = () => {
    const semesterResult = validateSemesterCode(semesterCode)
    if (!semesterResult.ok) {
      setLocalError(t(semesterResult.message))
      return
    }
    const creditsResult = validateCredits(Number(maxCredits))
    if (!creditsResult.ok) {
      setLocalError(t(creditsResult.message))
      return
    }
    setLocalError('')
    onAutoPickCourses(Number(maxCredits))
  }

  const displayError = errorMessage || localError

  return (
    <Card className="print:hidden" data-testid="planner-auto-assist-panel">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-[var(--color-primary)]" />
        {t('planner.autoAssistTitle')}
      </h2>
      <p className="mb-4 text-xs text-[var(--color-text-muted)]">{t('planner.autoAssistHint')}</p>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <Input
          label={t('plans.maxCredits')}
          type="number"
          step="0.5"
          value={maxCredits}
          onChange={(event) => {
            setMaxCreditsTouched(true)
            setMaxCredits(event.target.value)
          }}
          className="sm:max-w-[180px]"
        />
        <Button
          type="button"
          variant="secondary"
          loading={pickingCourses}
          disabled={!semesterSelected || pickingCourses}
          onClick={handleAutoPick}
          data-testid="planner-auto-pick-button"
        >
          {t('planner.autoPickCourses')}
        </Button>
      </div>

      {displayError ? (
        <p className="mt-3 text-sm text-[var(--color-danger)]">{displayError}</p>
      ) : null}
      {statusMessage ? (
        <p
          className={
            statusTone === 'warning'
              ? 'mt-3 text-sm text-[var(--color-warning)]'
              : 'mt-3 text-sm text-[var(--color-success)]'
          }
          data-testid="planner-auto-pick-status"
        >
          {statusMessage}
        </p>
      ) : null}
    </Card>
  )
}
