import { Card, Spinner } from '../ui/Card'
import { OnboardingStepIndicator } from './OnboardingStepIndicator'

type OnboardingShellProps = {
  stepLabels: string[]
  currentStep: number
  stepTitle: string
  stepHint: string
  children: React.ReactNode
  footer: React.ReactNode
  loading?: boolean
}

export function OnboardingShell({
  stepLabels,
  currentStep,
  stepTitle,
  stepHint,
  children,
  footer,
  loading,
}: OnboardingShellProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-8 sm:py-12">
      <div className="w-full max-w-xl animate-fade-in">
        <header className="mb-6 text-center">
          <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-primary)] text-base font-bold text-white shadow-[var(--shadow-card)]">
            UP
          </div>
          <OnboardingStepIndicator steps={stepLabels} currentStep={currentStep} />
          <h1 className="mt-6 text-xl font-semibold tracking-tight text-[var(--color-text)] sm:text-2xl">
            {stepTitle}
          </h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-[var(--color-text-muted)]">
            {stepHint}
          </p>
        </header>

        <Card className="overflow-hidden p-0">
          <div className="p-6 sm:p-8">
            {loading ? (
              <div className="flex justify-center py-12">
                <Spinner />
              </div>
            ) : (
              children
            )}
          </div>
          <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-4 sm:px-8">
            {footer}
          </div>
        </Card>
      </div>
    </div>
  )
}
