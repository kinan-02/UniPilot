import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'

export type BuilderStep = 'basics' | 'courses' | 'schedule'

type PlanBuilderStepperProps = {
  step: BuilderStep
  labels: Record<BuilderStep, string>
}

const ORDER: BuilderStep[] = ['basics', 'courses', 'schedule']

export function PlanBuilderStepper({ step, labels }: PlanBuilderStepperProps) {
  const currentIndex = ORDER.indexOf(step)

  return (
    <ol className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-0">
      {ORDER.map((id, index) => {
        const done = index < currentIndex
        const active = id === step
        return (
          <li
            key={id}
            className={cn(
              'flex flex-1 items-center gap-3 sm:flex-col sm:gap-2 sm:text-center',
              index < ORDER.length - 1 && 'sm:pb-0',
            )}
          >
            <div className="flex items-center gap-3 sm:flex-col">
              <div
                className={cn(
                  'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition',
                  done && 'bg-[var(--color-success)] text-white',
                  active && !done && 'bg-[var(--color-primary)] text-white shadow-sm',
                  !done && !active && 'border border-[var(--color-border)] bg-white text-[var(--color-text-muted)]',
                )}
                aria-current={active ? 'step' : undefined}
              >
                {done ? <Check className="h-4 w-4" /> : index + 1}
              </div>
              <span
                className={cn(
                  'text-sm font-medium',
                  active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-muted)]',
                )}
              >
                {labels[id]}
              </span>
            </div>
            {index < ORDER.length - 1 ? (
              <div
                className={cn(
                  'hidden h-px flex-1 bg-[var(--color-border)] sm:block',
                  done && 'bg-[var(--color-success)]/40',
                )}
                aria-hidden
              />
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}
