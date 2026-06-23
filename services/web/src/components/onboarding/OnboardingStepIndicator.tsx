import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'

type OnboardingStepIndicatorProps = {
  steps: string[]
  currentStep: number
}

export function OnboardingStepIndicator({ steps, currentStep }: OnboardingStepIndicatorProps) {
  return (
    <nav aria-label="Profile setup progress" className="w-full">
      <ol className="flex items-center gap-2">
        {steps.map((label, index) => {
          const done = index < currentStep
          const active = index === currentStep
          return (
            <li key={label} className="flex min-w-0 flex-1 items-center gap-2">
              <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
                <span
                  className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors',
                    done && 'bg-[var(--color-primary)] text-white',
                    active && 'bg-[var(--color-primary)] text-white ring-4 ring-[var(--color-primary)]/20',
                    !done && !active && 'border border-[var(--color-border)] bg-white text-[var(--color-text-muted)]',
                  )}
                  aria-current={active ? 'step' : undefined}
                >
                  {done ? <Check className="h-4 w-4" aria-hidden /> : index + 1}
                </span>
                <span
                  className={cn(
                    'hidden w-full truncate text-center text-[10px] font-medium sm:block',
                    active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-muted)]',
                  )}
                >
                  {label}
                </span>
              </div>
              {index < steps.length - 1 ? (
                <span
                  className={cn(
                    'mb-5 hidden h-0.5 flex-1 rounded-full sm:block',
                    index < currentStep ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-border)]',
                  )}
                  aria-hidden
                />
              ) : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
