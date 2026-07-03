import { AlertCircle, BookOpen, ClipboardList, PanelRightClose } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router-dom'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { useTranslation } from '../../i18n'
import type { AgentProposedAction, AgentStructuredBlock } from '../../types/agent'
import type { StudentProfile } from '../../types/api'
import { AgentBlockRenderer } from './AgentBlocks'
import { agentFadeUp, useAgentMotionEnabled } from './agentMotion'

type AgentContextPanelProps = {
  profile?: StudentProfile | null
  programName?: string | null
  blocks: AgentStructuredBlock[]
  pendingActions: AgentProposedAction[]
  assumptions?: string[]
  collapsed: boolean
  onToggleCollapsed: () => void
  onConfirmAction?: (actionId: string) => void
  onRejectAction?: (actionId: string) => void
  isConfirming?: boolean
}

function ContextSection({
  title,
  children,
  delay = 0,
}: {
  title: string
  children: React.ReactNode
  delay?: number
}) {
  const motionEnabled = useAgentMotionEnabled()
  if (!motionEnabled) {
    return (
      <Card className="mb-4 border-[var(--color-border)]/80 bg-white/90 p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
        <h3 className="text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
          {title}
        </h3>
        <div className="mt-3">{children}</div>
      </Card>
    )
  }
  return (
    <motion.div
      variants={agentFadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay }}
    >
      <Card className="mb-4 border-[var(--color-border)]/80 bg-white/90 p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
        <h3 className="text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
          {title}
        </h3>
        <div className="mt-3">{children}</div>
      </Card>
    </motion.div>
  )
}

export function AgentContextPanel({
  profile,
  programName,
  blocks,
  pendingActions,
  assumptions = [],
  collapsed,
  onToggleCollapsed,
  onConfirmAction,
  onRejectAction,
  isConfirming,
}: AgentContextPanelProps) {
  const { t } = useTranslation()
  const motionEnabled = useAgentMotionEnabled()

  if (collapsed) {
    return (
      <div className="hidden border-s border-[var(--color-border)]/80 bg-white/60 lg:block lg:w-12">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex h-full w-full flex-col items-center gap-2 py-4 text-[var(--color-text-muted)] transition hover:text-[var(--color-primary)]"
          aria-label={t('agent.showContext')}
        >
          <ClipboardList className="h-4 w-4" />
        </button>
      </div>
    )
  }

  const sourceBlock = blocks.find((block) => block.type === 'SourceSummaryBlock')
  const warningBlocks = blocks.filter((block) => block.type === 'WarningBlock')

  const Panel = motionEnabled ? motion.aside : 'aside'

  return (
    <Panel
      className="hidden w-[min(360px,28vw)] shrink-0 overflow-y-auto border-s border-[var(--color-border)]/80 bg-white/40 p-4 backdrop-blur-sm lg:block"
      data-testid="agent-context-panel"
      {...(motionEnabled
        ? {
            initial: { opacity: 0, x: 20 },
            animate: { opacity: 1, x: 0 },
            exit: { opacity: 0, x: 20 },
            transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
          }
        : {})}
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="text-sm font-semibold tracking-tight">{t('agent.contextTitle')}</h2>
        </div>
        <Button variant="ghost" size="sm" onClick={onToggleCollapsed} className="gap-1 text-xs">
          <PanelRightClose className="h-3.5 w-3.5" />
          {t('agent.hideContext')}
        </Button>
      </div>

      <ContextSection title={t('agent.studentContext')}>
        {profile ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">{t('agent.degreeProgram')}</dt>
              <dd className="mt-0.5 font-medium">{programName ?? t('agent.notSet')}</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">{t('agent.catalogYear')}</dt>
              <dd className="mt-0.5 font-medium">{profile.catalogYear ?? t('agent.missing')}</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">{t('agent.currentSemester')}</dt>
              <dd className="mt-0.5 font-medium">{profile.currentSemesterCode ?? t('agent.missing')}</dd>
            </div>
            {profile.academicPath?.trackSlug ? (
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">{t('agent.track')}</dt>
                <dd className="mt-0.5 font-medium">{profile.academicPath.trackSlug}</dd>
              </div>
            ) : null}
          </dl>
        ) : (
          <div className="flex gap-2 text-sm text-amber-900">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p>{t('agent.profileIncomplete')}</p>
              <Link
                to="/profile"
                className="mt-2 inline-block font-medium text-[var(--color-primary)] transition hover:underline"
              >
                {t('agent.updateProfile')}
              </Link>
            </div>
          </div>
        )}
      </ContextSection>

      <AnimatePresence>
        {pendingActions.length > 0 ? (
          <motion.div
            key="pending-actions"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <ContextSection title={t('agent.pendingActions')} delay={0.05}>
              <ul className="space-y-2">
                {pendingActions.map((action) => (
                  <li
                    key={action.id}
                    className="rounded-xl border border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5 p-3 text-sm"
                  >
                    <p className="font-medium">{action.label}</p>
                    {action.description ? (
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{action.description}</p>
                    ) : null}
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" disabled={isConfirming} onClick={() => onConfirmAction?.(action.id)}>
                        {t('agent.confirm')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={isConfirming}
                        onClick={() => onRejectAction?.(action.id)}
                      >
                        {t('agent.reject')}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </ContextSection>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {assumptions.length > 0 ? (
        <ContextSection title={t('agent.assumptions')} delay={0.08}>
          <ul className="space-y-1.5 text-sm text-[var(--color-text-muted)]">
            {assumptions.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-[var(--color-accent)]">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </ContextSection>
      ) : null}

      {warningBlocks.length > 0 ? (
        <div className="mb-4 space-y-2">
          {warningBlocks.map((block, index) => (
            <AgentBlockRenderer key={`warning-${index}`} block={block} index={index} />
          ))}
        </div>
      ) : null}

      {sourceBlock ? (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
            <BookOpen className="h-3.5 w-3.5" />
            {t('agent.sourcesUsed')}
          </div>
          <AgentBlockRenderer block={sourceBlock} index={0} />
        </div>
      ) : null}
    </Panel>
  )
}
