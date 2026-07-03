import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { Button } from '../ui/Button'
import { cn } from '../../lib/utils'

type AgentActionBarProps = {
  isApproved: boolean
  isApplied: boolean
  appliedPlanId?: string | null
  approving: boolean
  applying: boolean
  onApprove: () => void
  onApply: () => void
  approveLabel: string
  approvedLabel: string
  applyLabel: string
  appliedLabel: string
  openPlannerLabel: string
  approvalRequiredLabel: string
  className?: string
}

export function AgentActionBar({
  isApproved,
  isApplied,
  appliedPlanId,
  approving,
  applying,
  onApprove,
  onApply,
  approveLabel,
  approvedLabel,
  applyLabel,
  appliedLabel,
  openPlannerLabel,
  approvalRequiredLabel,
  className,
}: AgentActionBarProps) {
  return (
    <div
      className={cn(
        'sticky bottom-4 z-10 rounded-2xl border border-[var(--color-border)] bg-white/95 p-4 shadow-lg backdrop-blur-sm',
        className,
      )}
      data-testid="agent-sessions-action-bar"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Button
          type="button"
          variant={isApproved ? 'secondary' : 'primary'}
          onClick={onApprove}
          loading={approving}
          disabled={isApproved || isApplied}
          data-testid="agent-sessions-approve"
        >
          <Check className="h-4 w-4" />
          {isApproved ? approvedLabel : approveLabel}
        </Button>
        <Button
          type="button"
          onClick={onApply}
          loading={applying}
          disabled={!isApproved || isApplied}
          data-testid="agent-sessions-apply"
        >
          {isApplied ? appliedLabel : applyLabel}
        </Button>
        {isApplied && appliedPlanId ? (
          <Link
            to={`/plans/${appliedPlanId}/edit`}
            className="inline-flex items-center text-sm font-medium text-[var(--color-primary)] underline-offset-2 hover:underline"
            data-testid="agent-sessions-open-planner"
          >
            {openPlannerLabel}
          </Link>
        ) : null}
        {!isApproved && !isApplied ? (
          <p className="text-xs text-[var(--color-text-muted)] sm:ms-auto">{approvalRequiredLabel}</p>
        ) : null}
      </div>
    </div>
  )
}
