import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { WorkflowStepId } from './agentSessionUtils'
import { workflowStepIndex } from './agentSessionUtils'

type StepDef = { id: WorkflowStepId; label: string }

type AgentWorkflowStepperProps = {
  steps: StepDef[]
  activeStep: WorkflowStepId
}

export function AgentWorkflowStepper({ steps, activeStep }: AgentWorkflowStepperProps) {
  const activeIndex = workflowStepIndex(activeStep)

  return (
    <nav
      aria-label="Planning workflow"
      className="rounded-2xl border border-[var(--color-border)] bg-white px-4 py-4 shadow-sm sm:px-5"
      data-testid="agent-sessions-workflow"
    >
      <ol className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {steps.map((step, index) => {
          const isComplete = index < activeIndex
          const isCurrent = step.id === activeStep
          const isLast = index === steps.length - 1
          return (
            <li key={step.id} className="flex min-w-0 flex-1 items-start gap-2.5">
              <span
                className={cn(
                  'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums transition-colors',
                  isComplete && 'bg-[var(--color-primary)] text-white',
                  isCurrent && !isComplete && 'border-2 border-[var(--color-primary)] text-[var(--color-primary)]',
                  !isComplete && !isCurrent && 'bg-stone-100 text-stone-500',
                )}
                aria-current={isCurrent ? 'step' : undefined}
              >
                {isComplete ? <Check className="h-3.5 w-3.5" aria-hidden /> : index + 1}
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <p
                  className={cn(
                    'text-xs font-medium sm:text-sm',
                    isCurrent ? 'text-[var(--color-text)]' : 'text-[var(--color-text-muted)]',
                  )}
                >
                  {step.label}
                </p>
              </div>
              {!isLast ? (
                <span
                  className={cn(
                    'mx-2 mt-3.5 hidden h-0.5 min-w-[1.5rem] flex-1 sm:block',
                    isComplete ? 'bg-[var(--color-primary)]' : 'bg-stone-200',
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
