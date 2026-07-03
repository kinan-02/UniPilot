import { Bot, GraduationCap, Sparkles, User } from 'lucide-react'
import { motion } from 'motion/react'
import { cn } from '../../lib/utils'
import { useTranslation } from '../../i18n'
import type { AgentChatMessage, AgentLiveTurn, AgentStructuredBlock } from '../../types/agent'
import {
  agentFadeUp,
  agentSlideInEnd,
  agentSlideInStart,
  agentStaggerContainer,
  useAgentMotionEnabled,
} from './agentMotion'
import {
  AgentActivitySteps,
  AgentBlockRenderer,
  SuggestedPromptChips,
} from './AgentBlocks'

const EMPTY_PROMPTS = [
  { key: 'agent.promptGraduation' as const, icon: GraduationCap },
  { key: 'agent.promptTranscript' as const, icon: Sparkles },
  { key: 'agent.promptSemesterPlan' as const, icon: Sparkles },
  { key: 'agent.promptRequirements' as const, icon: Sparkles },
  { key: 'agent.promptCourse' as const, icon: Sparkles },
  { key: 'agent.promptSchedule' as const, icon: Sparkles },
] as const

export function AgentEmptyState({ onSelectPrompt }: { onSelectPrompt: (prompt: string) => void }) {
  const { t } = useTranslation()
  const motionEnabled = useAgentMotionEnabled()
  const Container = motionEnabled ? motion.div : 'div'
  const Item = motionEnabled ? motion.button : 'button'

  return (
    <div
      className="flex h-full flex-col items-center justify-center px-6 py-12 text-center"
      data-testid="agent-empty-state"
    >
      <Container
        {...(motionEnabled
          ? {
              initial: { opacity: 0, scale: 0.92 },
              animate: { opacity: 1, scale: 1 },
              transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
            }
          : {})}
        className="relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--color-primary)]/15 to-[var(--color-accent)]/10 text-[var(--color-primary)] shadow-[var(--shadow-soft)]"
      >
        <Sparkles className="h-8 w-8" />
        <span className="pointer-events-none absolute inset-0 rounded-2xl agent-shimmer opacity-40" />
      </Container>

      <Container
        {...(motionEnabled
          ? {
              initial: { opacity: 0, y: 10 },
              animate: { opacity: 1, y: 0 },
              transition: { delay: 0.08, duration: 0.35 },
            }
          : {})}
      >
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-text)]">
          {t('agent.emptyTitle')}
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-[var(--color-text-muted)]">
          {t('agent.emptySubtitle')}
        </p>
      </Container>

      <Container
        className="mt-10 grid w-full max-w-2xl gap-3 sm:grid-cols-2"
        {...(motionEnabled ? { variants: agentStaggerContainer, initial: 'hidden', animate: 'visible' } : {})}
      >
        {EMPTY_PROMPTS.map(({ key, icon: Icon }) => (
          <Item
            key={key}
            type="button"
            onClick={() => onSelectPrompt(t(key))}
            {...(motionEnabled ? { variants: agentFadeUp } : {})}
            className={cn(
              'group relative overflow-hidden rounded-2xl border border-[var(--color-border)]/90',
              'bg-white/90 px-4 py-4 text-start text-sm font-medium',
              'shadow-[var(--shadow-soft)] transition-all duration-200',
              'hover:-translate-y-0.5 hover:border-[var(--color-primary)]/25 hover:shadow-[var(--shadow-card)]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30',
            )}
          >
            <span className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-primary)]/8 text-[var(--color-primary)] transition group-hover:bg-[var(--color-primary)]/12">
              <Icon className="h-4 w-4" />
            </span>
            <span className="block leading-snug text-[var(--color-text)]">{t(key)}</span>
          </Item>
        ))}
      </Container>
    </div>
  )
}

function UserBubble({ content }: { content: string }) {
  const motionEnabled = useAgentMotionEnabled()
  const Wrapper = motionEnabled ? motion.div : 'div'

  return (
    <Wrapper
      {...(motionEnabled ? { variants: agentSlideInEnd, initial: 'hidden', animate: 'visible' } : {})}
      className="flex justify-end"
    >
      <div className="flex max-w-[min(85%,36rem)] items-end gap-2.5">
        <div className="rounded-[1.25rem] rounded-ee-md bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-primary-light)] px-4 py-3 text-sm leading-relaxed text-white shadow-md shadow-[var(--color-primary)]/15">
          <p className="whitespace-pre-wrap">{content}</p>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)] ring-2 ring-white">
          <User className="h-4 w-4" />
        </div>
      </div>
    </Wrapper>
  )
}

function AssistantGroup({
  content,
  blocks,
  liveTurn,
  suggestedPrompts,
  onSelectPrompt,
  onConfirmAction,
  onRejectAction,
  isConfirming,
  isStreaming,
}: {
  content: string
  blocks: AgentStructuredBlock[]
  liveTurn?: AgentLiveTurn | null
  suggestedPrompts: string[]
  onSelectPrompt: (prompt: string) => void
  onConfirmAction?: (actionId: string) => void
  onRejectAction?: (actionId: string) => void
  isConfirming?: boolean
  isStreaming?: boolean
}) {
  const motionEnabled = useAgentMotionEnabled()
  const Wrapper = motionEnabled ? motion.div : 'div'
  const steps = liveTurn?.steps ?? []
  const displayText = liveTurn?.text || content
  const displayBlocks = liveTurn?.blocks.length ? liveTurn.blocks : blocks
  const showCursor = isStreaming && displayText

  return (
    <Wrapper
      {...(motionEnabled ? { variants: agentSlideInStart, initial: 'hidden', animate: 'visible' } : {})}
      className="flex justify-start"
    >
      <div className="flex w-full max-w-3xl items-start gap-3">
        <div
          className={cn(
            'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
            'bg-white text-[var(--color-primary)] ring-1 ring-[var(--color-border)] shadow-sm',
            isStreaming && 'agent-avatar-live',
          )}
        >
          <Bot className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          {isStreaming ? <AgentActivitySteps steps={steps} /> : null}
          {displayText ? (
            <div className="rounded-[1.25rem] rounded-es-md border border-[var(--color-border)]/80 bg-white/95 px-4 py-3.5 text-sm leading-relaxed shadow-[var(--shadow-soft)] backdrop-blur-sm">
              <p className={cn('whitespace-pre-wrap text-[var(--color-text)]', showCursor && 'agent-stream-cursor')}>
                {displayText}
              </p>
            </div>
          ) : isStreaming ? (
            <div className="rounded-[1.25rem] rounded-es-md border border-[var(--color-border)]/80 bg-white/95 px-4 py-3.5 shadow-[var(--shadow-soft)]">
              <div className="flex gap-1.5 py-1">
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-primary)]/40 [animation-delay:0ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-primary)]/40 [animation-delay:150ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-primary)]/40 [animation-delay:300ms]" />
              </div>
            </div>
          ) : null}
          <div className="space-y-3">
            {displayBlocks.map((block, index) => (
              <AgentBlockRenderer
                key={`${block.type}-${index}`}
                block={block}
                index={index}
                onConfirmAction={onConfirmAction}
                onRejectAction={onRejectAction}
                isConfirming={isConfirming}
              />
            ))}
          </div>
          {liveTurn?.error ? (
            <p className="text-sm text-rose-700">{liveTurn.error}</p>
          ) : null}
          {!isStreaming ? (
            <SuggestedPromptChips
              prompts={suggestedPrompts}
              onSelect={onSelectPrompt}
              disabled={isStreaming}
            />
          ) : null}
        </div>
      </div>
    </Wrapper>
  )
}

type AgentMessageTimelineProps = {
  messages: AgentChatMessage[]
  liveTurn: AgentLiveTurn | null
  suggestedPrompts: string[]
  isStreaming: boolean
  onSelectPrompt: (prompt: string) => void
  onConfirmAction?: (actionId: string) => void
  onRejectAction?: (actionId: string) => void
  isConfirming?: boolean
}

export function AgentMessageTimeline({
  messages,
  liveTurn,
  suggestedPrompts,
  isStreaming,
  onSelectPrompt,
  onConfirmAction,
  onRejectAction,
  isConfirming,
}: AgentMessageTimelineProps) {
  const motionEnabled = useAgentMotionEnabled()
  const Container = motionEnabled ? motion.div : 'div'

  return (
    <Container
      className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8"
      data-testid="agent-message-timeline"
      {...(motionEnabled ? { variants: agentStaggerContainer, initial: 'hidden', animate: 'visible' } : {})}
    >
      {messages.map((message) =>
        message.kind === 'user' ? (
          <UserBubble key={message.id} content={message.content} />
        ) : (
          <AssistantGroup
            key={message.id}
            content={message.content}
            blocks={message.blocks}
            suggestedPrompts={[]}
            onSelectPrompt={onSelectPrompt}
            onConfirmAction={onConfirmAction}
            onRejectAction={onRejectAction}
            isConfirming={isConfirming}
          />
        ),
      )}

      {liveTurn ? (
        <AssistantGroup
          content=""
          blocks={[]}
          liveTurn={liveTurn}
          suggestedPrompts={suggestedPrompts}
          onSelectPrompt={onSelectPrompt}
          onConfirmAction={onConfirmAction}
          onRejectAction={onRejectAction}
          isConfirming={isConfirming}
          isStreaming={isStreaming}
        />
      ) : null}
    </Container>
  )
}

export function AgentChatHeader({
  profileLabel,
  profileWarning,
}: {
  profileLabel?: string | null
  profileWarning?: boolean
}) {
  const { t } = useTranslation()
  const motionEnabled = useAgentMotionEnabled()
  const Header = motionEnabled ? motion.header : 'header'

  return (
    <Header
      className="border-b border-[var(--color-border)]/80 agent-glass px-6 py-4"
      data-testid="agent-chat-header"
      {...(motionEnabled
        ? {
            initial: { opacity: 0, y: -8 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
          }
        : {})}
    >
      <div className="mx-auto flex max-w-3xl flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-[var(--color-text)]">{t('agent.title')}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('agent.headerSubtitle')}</p>
        </div>
        {profileLabel ? (
          <div
            className={cn(
              'rounded-full px-3 py-1 text-xs font-medium',
              profileWarning
                ? 'bg-amber-50 text-amber-900 ring-1 ring-amber-200/80'
                : 'bg-white/80 text-[var(--color-text-muted)] ring-1 ring-[var(--color-border)]',
            )}
          >
            {profileLabel}
          </div>
        ) : null}
      </div>
      {profileWarning ? (
        <p className="mx-auto mt-2 max-w-3xl text-xs text-amber-800">{t('agent.profileHeaderWarning')}</p>
      ) : null}
    </Header>
  )
}
