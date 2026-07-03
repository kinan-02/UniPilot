import type { AgentSession } from '../../types/api'

export const ACTIVE_STATUSES = new Set(['pending', 'processing'])

export function statusTone(
  status: string,
): 'success' | 'warning' | 'neutral' | 'danger' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'processing') return 'warning'
  if (status === 'awaiting_clarification') return 'warning'
  return 'neutral'
}

export function formatAgentRole(role: string): string {
  return role.replace(/_/g, ' ')
}

export const AGENT_ROSTER: ReadonlyArray<{ id: string }> = [
  { id: 'goal_analyst' },
  { id: 'planner' },
  { id: 'catalog_scout' },
  { id: 'risk_sentinel' },
  { id: 'student_advocate' },
  { id: 'arbiter' },
]

export type WorkflowStepId = 'compose' | 'negotiate' | 'review' | 'apply'

export function resolveWorkflowStep(session: AgentSession | undefined): WorkflowStepId {
  if (!session) return 'compose'
  if (ACTIVE_STATUSES.has(session.status) || session.status === 'awaiting_clarification') {
    return 'negotiate'
  }
  if (session.status === 'completed') {
    if (session.appliedPlanId) return 'apply'
    if (session.approvedAt) return 'apply'
    return 'review'
  }
  return 'review'
}

export function workflowStepIndex(step: WorkflowStepId): number {
  const order: WorkflowStepId[] = ['compose', 'negotiate', 'review', 'apply']
  return order.indexOf(step)
}

export function formatSessionTimestamp(value?: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatRelativeSessionTime(
  value: string | null | undefined,
  locale: string,
): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  const diffMs = date.getTime() - Date.now()
  const diffMinutes = Math.round(diffMs / 60_000)
  const rtf = new Intl.RelativeTimeFormat(locale === 'he' ? 'he' : 'en', { numeric: 'auto' })

  if (Math.abs(diffMinutes) < 60) {
    return rtf.format(diffMinutes, 'minute')
  }
  const diffHours = Math.round(diffMinutes / 60)
  if (Math.abs(diffHours) < 48) {
    return rtf.format(diffHours, 'hour')
  }
  const diffDays = Math.round(diffHours / 24)
  if (Math.abs(diffDays) < 14) {
    return rtf.format(diffDays, 'day')
  }
  return formatSessionTimestamp(value) ?? '—'
}
