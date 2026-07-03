import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Circle,
  GraduationCap,
  Info,
  Loader2,
} from 'lucide-react'
import { motion } from 'motion/react'
import { Badge, Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { cn, formatCredits, formatPercent } from '../../lib/utils'
import type { AgentStructuredBlock } from '../../types/agent'
import { agentFadeUp, agentStaggerContainer, useAgentMotionEnabled } from './agentMotion'

const STATUS_TONE: Record<string, string> = {
  completed: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  partial: 'bg-amber-50 text-amber-900 border-amber-200',
  missing: 'bg-rose-50 text-rose-900 border-rose-200',
  blocked: 'bg-rose-50 text-rose-900 border-rose-200',
  needs_review: 'bg-sky-50 text-sky-900 border-sky-200',
  ready_to_graduate: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  not_ready: 'bg-amber-50 text-amber-900 border-amber-200',
  missing_data: 'bg-slate-100 text-slate-700 border-slate-200',
}

function StatusBadge({ status, label }: { status?: string; label?: string }) {
  const tone = STATUS_TONE[status ?? ''] ?? 'bg-slate-100 text-slate-700 border-slate-200'
  return (
    <span className={cn('inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium', tone)}>
      {label ?? status ?? 'Unknown'}
    </span>
  )
}

function AnimatedProgressBar({ value }: { value: number }) {
  const motionEnabled = useAgentMotionEnabled()
  const width = `${Math.min(value, 100)}%`

  if (!motionEnabled) {
    return (
      <div className="h-2 overflow-hidden rounded-full bg-[var(--color-border)]">
        <div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width }} />
      </div>
    )
  }

  return (
    <div className="h-2 overflow-hidden rounded-full bg-[var(--color-border)]">
      <motion.div
        className="h-full rounded-full bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary-light)]"
        initial={{ width: 0 }}
        animate={{ width }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
      />
    </div>
  )
}

function BlockMotionShell({
  index = 0,
  children,
  className,
}: {
  index?: number
  children: React.ReactNode
  className?: string
}) {
  const motionEnabled = useAgentMotionEnabled()
  if (!motionEnabled) {
    return <div className={className}>{children}</div>
  }
  return (
    <motion.div
      className={className}
      variants={agentFadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay: index * 0.06 }}
    >
      {children}
    </motion.div>
  )
}

function RequirementSummaryCard({ data }: { data: Record<string, unknown> }) {
  const completion = Number(data.completionPercentage ?? 0)
  return (
    <Card className="overflow-hidden border-[var(--color-border)]/80 p-0 shadow-[var(--shadow-soft)]" data-testid="agent-requirement-summary">
      <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GraduationCap className="h-4 w-4 text-[var(--color-primary)]" />
            <h3 className="text-sm font-semibold">Graduation Progress</h3>
          </div>
          <StatusBadge
            status={String(data.graduationStatus ?? '')}
            label={String(data.graduationStatusLabel ?? data.graduationStatus ?? '')}
          />
        </div>
        {data.degreeName ? (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">{String(data.degreeName)}</p>
        ) : null}
      </div>
      <div className="space-y-4 p-4">
        <div>
          <div className="mb-1 flex justify-between text-xs text-[var(--color-text-muted)]">
            <span>Completion</span>
            <span>{formatPercent(completion)}</span>
          </div>
          <AnimatedProgressBar value={completion} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Completed" value={formatCredits(Number(data.creditsCompleted ?? 0))} />
          <Stat label="Required" value={formatCredits(Number(data.creditsRequired ?? 0))} />
          <Stat label="Remaining" value={formatCredits(Number(data.creditsRemaining ?? 0))} />
        </div>
        {Array.isArray(data.mainBlockers) && data.mainBlockers.length > 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            <span className="font-medium text-[var(--color-text)]">Main blocker: </span>
            {String(data.mainBlockers[0])}
          </p>
        ) : null}
      </div>
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white/90 px-3 py-2">
      <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function RequirementBucketCard({ data }: { data: Record<string, unknown> }) {
  const status = String(data.status ?? 'needs_review')
  return (
    <Card className="p-4" data-testid="agent-requirement-bucket">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold">{String(data.title ?? data.label ?? 'Requirement')}</h4>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {formatCredits(Number(data.creditsCompleted ?? 0))} /{' '}
            {formatCredits(Number(data.creditsRequired ?? 0))} credits
          </p>
        </div>
        <StatusBadge status={status} />
      </div>
      {Number(data.creditsRemaining) > 0 ? (
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          {formatCredits(Number(data.creditsRemaining))} credits still needed
        </p>
      ) : null}
      {data.wikiExcerpt ? (
        <p className="mt-3 rounded-lg bg-[var(--color-surface-muted)] p-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
          {String(data.wikiExcerpt)}
        </p>
      ) : null}
    </Card>
  )
}

function CourseRecommendationCard({ data }: { data: Record<string, unknown> }) {
  return (
    <Card className="p-4" data-testid="agent-course-card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {String(data.courseNumber ?? '')}
          </p>
          <h4 className="text-sm font-semibold">{String(data.title ?? data.courseTitle ?? 'Course')}</h4>
        </div>
        {data.verdictLabel ? <StatusBadge status={String(data.verdict ?? '')} label={String(data.verdictLabel)} /> : null}
      </div>
      <div className="mt-3 grid gap-2 text-sm text-[var(--color-text-muted)] sm:grid-cols-2">
        {data.credits != null ? <p>Credits: {formatCredits(Number(data.credits))}</p> : null}
        {data.prerequisiteStatus ? <p>Prerequisites: {String(data.prerequisiteStatus)}</p> : null}
        {data.offeringStatus ? <p>Offering: {String(data.offeringStatus)}</p> : null}
      </div>
      {data.recommendation ? (
        <p className="mt-3 text-sm text-[var(--color-text)]">{String(data.recommendation)}</p>
      ) : null}
    </Card>
  )
}

function PrerequisiteStatusCard({ data }: { data: Record<string, unknown> }) {
  return (
    <Card className="p-4" data-testid="agent-prerequisite-card">
      <h4 className="text-sm font-semibold">Prerequisites</h4>
      <p className="mt-1 text-sm">
        Status: <span className="font-medium">{String(data.statusLabel ?? data.status ?? 'Unknown')}</span>
      </p>
      {Array.isArray(data.missingPrerequisites) && data.missingPrerequisites.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-[var(--color-text-muted)]">
          {data.missingPrerequisites.map((item, index) => (
            <li key={`${String(item)}-${index}`}>{String(item)}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  )
}

function OfferingStatusCard({ data }: { data: Record<string, unknown> }) {
  return (
    <Card className="p-4" data-testid="agent-offering-card">
      <h4 className="text-sm font-semibold">Offering Status</h4>
      <p className="mt-1 text-sm text-[var(--color-text-muted)]">
        {data.semesterLabel ? String(data.semesterLabel) : String(data.targetSemester ?? 'Target semester')}
        {': '}
        <span className="font-medium text-[var(--color-text)]">
          {data.isOffered === false ? 'Not offered' : 'Offered'}
        </span>
      </p>
      {data.notes ? <p className="mt-2 text-sm text-[var(--color-text-muted)]">{String(data.notes)}</p> : null}
    </Card>
  )
}

function WarningBanner({ data }: { data: Record<string, unknown> }) {
  const messages = Array.isArray(data.messages)
    ? data.messages.map(String)
    : data.message
      ? [String(data.message)]
      : []
  return (
    <div
      className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950"
      data-testid="agent-warning"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        {data.title ? <p className="font-semibold">{String(data.title)}</p> : null}
        <ul className={cn('space-y-1', data.title ? 'mt-1' : '')}>
          {messages.map((message, index) => (
            <li key={`${message}-${index}`}>{message}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function SourceSummaryCard({ data }: { data: Record<string, unknown> }) {
  const sources = Array.isArray(data.provenance)
    ? data.provenance.map(String)
    : Array.isArray(data.usedSources)
      ? data.usedSources.map(String)
      : Array.isArray(data.sources)
        ? data.sources.map(String)
        : []
  return (
    <Card className="p-4" data-testid="agent-source-summary">
      <div className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-[var(--color-primary)]" />
        <h4 className="text-sm font-semibold">Based on</h4>
      </div>
      {sources.length ? (
        <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-muted)]">
          {sources.slice(0, 6).map((source, index) => (
            <li key={`${source}-${index}`}>• {source}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">Catalog and profile data</p>
      )}
    </Card>
  )
}

function SemesterPlanOptionsBlock({ data }: { data: Record<string, unknown> }) {
  const options = Array.isArray(data.options) ? data.options : []
  return (
    <Card className="overflow-hidden p-0" data-testid="agent-plan-options">
      <div className="border-b border-[var(--color-border)] px-4 py-3">
        <h4 className="text-sm font-semibold">Semester Plan Options</h4>
        {data.semesterCode ? (
          <p className="text-xs text-[var(--color-text-muted)]">Semester {String(data.semesterCode)}</p>
        ) : null}
      </div>
      <div className="divide-y divide-[var(--color-border)]">
        {options.map((option, index) => {
          const row = option as Record<string, unknown>
          return (
            <div key={String(row.optionId ?? index)} className="px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{String(row.label ?? `Option ${index + 1}`)}</p>
                <Badge tone="neutral">{formatCredits(Number(row.totalCredits ?? 0))} cr</Badge>
              </div>
              {Array.isArray(row.plannedCourses) ? (
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  {(row.plannedCourses as unknown[]).length} courses
                </p>
              ) : null}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function SchedulePreviewBlock({ data }: { data: Record<string, unknown> }) {
  const previews = Array.isArray(data.previews) ? data.previews : []
  return (
    <Card className="p-4" data-testid="agent-schedule-preview">
      <h4 className="text-sm font-semibold">Schedule Preview</h4>
      <div className="mt-3 space-y-3">
        {previews.map((preview, index) => {
          const row = preview as Record<string, unknown>
          const selections = Array.isArray(row.selections) ? row.selections : []
          return (
            <div key={String(row.optionId ?? index)} className="rounded-lg border border-[var(--color-border)] p-3">
              <p className="text-sm font-medium">{String(row.label ?? `Option ${index + 1}`)}</p>
              <ul className="mt-2 space-y-1 text-xs text-[var(--color-text-muted)]">
                {selections.slice(0, 8).map((selection, selIndex) => {
                  const item = selection as Record<string, unknown>
                  return (
                    <li key={selIndex}>
                      {String(item.courseNumber ?? item.courseId ?? 'Course')} —{' '}
                      {String(item.day ?? '')} {String(item.time ?? '')}
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function ConfirmationPanel({
  data,
  onConfirm,
  onReject,
  isConfirming,
}: {
  data: Record<string, unknown>
  onConfirm?: (actionId: string) => void
  onReject?: (actionId: string) => void
  isConfirming?: boolean
}) {
  const actions = Array.isArray(data.availableActions) ? data.availableActions : []
  return (
    <Card className="border-[var(--color-primary)]/20 bg-[var(--color-primary)]/5 p-4" data-testid="agent-confirmation">
      <div className="flex gap-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-primary)]" />
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold">{String(data.title ?? 'Confirm action')}</h4>
          {data.description ? (
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">{String(data.description)}</p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            {actions.map((action, index) => {
              const row = action as Record<string, unknown>
              const actionId = String(row.actionId ?? '')
              return (
                <Button
                  key={actionId || index}
                  size="sm"
                  disabled={isConfirming || !actionId}
                  onClick={() => actionId && onConfirm?.(actionId)}
                >
                  {String(row.label ?? data.confirmLabel ?? 'Confirm')}
                </Button>
              )
            })}
            {actions.length === 0 ? (
              <Button size="sm" disabled={isConfirming}>
                {String(data.confirmLabel ?? 'Confirm')}
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="ghost"
              disabled={isConfirming}
              onClick={() => {
                const first = actions[0] as Record<string, unknown> | undefined
                const actionId = String(first?.actionId ?? '')
                if (actionId) onReject?.(actionId)
              }}
            >
              {String(data.cancelLabel ?? 'Cancel')}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}

function TranscriptReviewBlock({ data }: { data: Record<string, unknown> }) {
  const rows = Array.isArray(data.rows) ? data.rows : Array.isArray(data.courses) ? data.courses : []
  return (
    <Card className="overflow-hidden p-0" data-testid="agent-transcript-review">
      <div className="border-b border-[var(--color-border)] px-4 py-3">
        <h4 className="text-sm font-semibold">Transcript Review</h4>
        <p className="text-xs text-[var(--color-text-muted)]">
          {rows.length} courses detected — nothing is saved until you confirm.
        </p>
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[var(--color-surface-muted)] text-xs uppercase text-[var(--color-text-muted)]">
            <tr>
              <th className="px-4 py-2 text-start">Course</th>
              <th className="px-4 py-2 text-start">Semester</th>
              <th className="px-4 py-2 text-start">Grade</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row, index) => {
              const item = row as Record<string, unknown>
              return (
                <tr key={index} className="border-t border-[var(--color-border)]">
                  <td className="px-4 py-2">{String(item.courseNumber ?? item.courseId ?? '—')}</td>
                  <td className="px-4 py-2">{String(item.semesterCode ?? '—')}</td>
                  <td className="px-4 py-2">{String(item.grade ?? '—')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

type AgentBlockRendererProps = {
  block: AgentStructuredBlock
  index?: number
  onConfirmAction?: (actionId: string) => void
  onRejectAction?: (actionId: string) => void
  isConfirming?: boolean
}

export function AgentBlockRenderer({
  block,
  index = 0,
  onConfirmAction,
  onRejectAction,
  isConfirming,
}: AgentBlockRendererProps) {
  const { type, data } = block

  const content = (() => {
    switch (type) {
      case 'RequirementSummaryBlock':
        return <RequirementSummaryCard data={data} />
      case 'RequirementBucketBlock':
        return <RequirementBucketCard data={data} />
      case 'CourseRecommendationBlock':
        return <CourseRecommendationCard data={data} />
      case 'PrerequisiteStatusBlock':
        return <PrerequisiteStatusCard data={data} />
      case 'OfferingStatusBlock':
      case 'OfferingSummaryBlock':
        return <OfferingStatusCard data={data} />
      case 'WarningBlock':
        return <WarningBanner data={data} />
      case 'SourceSummaryBlock':
        return <SourceSummaryCard data={data} />
      case 'SemesterPlanOptionsBlock':
        return <SemesterPlanOptionsBlock data={data} />
      case 'SchedulePreviewBlock':
        return <SchedulePreviewBlock data={data} />
      case 'ConfirmationBlock':
        return (
          <ConfirmationPanel
            data={data}
            onConfirm={onConfirmAction}
            onReject={onRejectAction}
            isConfirming={isConfirming}
          />
        )
      case 'TranscriptReviewBlock':
        return <TranscriptReviewBlock data={data} />
      default:
        return (
          <Card className="p-4 text-sm text-[var(--color-text-muted)]">
            <p className="font-medium text-[var(--color-text)]">{type}</p>
            <pre className="mt-2 overflow-auto text-xs">{JSON.stringify(data, null, 2)}</pre>
          </Card>
        )
    }
  })()

  return <BlockMotionShell index={index}>{content}</BlockMotionShell>
}

export function AgentActivitySteps({
  steps,
}: {
  steps: Array<{ label: string; status: string }>
}) {
  const motionEnabled = useAgentMotionEnabled()
  if (!steps.length) return null

  const Container = motionEnabled ? motion.div : 'div'
  const List = motionEnabled ? motion.ul : 'ul'
  const Item = motionEnabled ? motion.li : 'li'

  return (
    <Container
      className="rounded-xl border border-[var(--color-border)]/80 bg-white/90 px-4 py-3 shadow-[var(--shadow-soft)] backdrop-blur-sm"
      data-testid="agent-activity-steps"
      {...(motionEnabled
        ? {
            initial: { opacity: 0, y: 8 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.3 },
          }
        : {})}
    >
      <p className="mb-2 text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
        Agent activity
      </p>
      <List
        className="space-y-2"
        {...(motionEnabled ? { variants: agentStaggerContainer, initial: 'hidden', animate: 'visible' } : {})}
      >
        {steps.map((step) => (
          <Item
            key={step.label}
            className="flex items-center gap-2 text-sm"
            {...(motionEnabled ? { variants: agentFadeUp } : {})}
          >
            {step.status === 'completed' ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : step.status === 'running' ? (
              <Loader2 className="h-4 w-4 animate-spin text-[var(--color-primary)]" />
            ) : step.status === 'failed' ? (
              <AlertTriangle className="h-4 w-4 text-rose-600" />
            ) : (
              <Circle className="h-4 w-4 text-[var(--color-border)]" />
            )}
            <span
              className={cn(
                step.status === 'running' ? 'font-medium text-[var(--color-text)]' : 'text-[var(--color-text-muted)]',
              )}
            >
              {step.label}
            </span>
          </Item>
        ))}
      </List>
    </Container>
  )
}

export function SuggestedPromptChips({
  prompts,
  onSelect,
  disabled,
}: {
  prompts: string[]
  onSelect: (prompt: string) => void
  disabled?: boolean
}) {
  const motionEnabled = useAgentMotionEnabled()
  if (!prompts.length) return null

  const Container = motionEnabled ? motion.div : 'div'
  const Chip = motionEnabled ? motion.button : 'button'

  return (
    <Container
      className="flex flex-wrap gap-2"
      data-testid="agent-suggested-prompts"
      {...(motionEnabled ? { variants: agentStaggerContainer, initial: 'hidden', animate: 'visible' } : {})}
    >
      {prompts.map((prompt) => (
        <Chip
          key={prompt}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(prompt)}
          {...(motionEnabled
            ? {
                variants: agentFadeUp,
                whileHover: { scale: 1.02, y: -1 },
                whileTap: { scale: 0.98 },
              }
            : {})}
          className={cn(
            'rounded-full border border-[var(--color-border)]/90 bg-white/95 px-3.5 py-1.5',
            'text-xs font-medium text-[var(--color-text)] shadow-sm',
            'transition-colors hover:border-[var(--color-primary)]/30 hover:bg-[var(--color-primary)]/5',
            'disabled:opacity-50',
          )}
        >
          {prompt}
        </Chip>
      ))}
    </Container>
  )
}
