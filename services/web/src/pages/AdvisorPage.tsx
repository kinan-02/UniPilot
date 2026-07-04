import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, MessageSquarePlus, Send, Sparkles, Trash2 } from 'lucide-react'
import { advisorApi } from '../api/endpoints'
import { OpenInWhatIfLink } from '../components/simulations/OpenInWhatIfLink'
import { useAdvisorAsyncJob } from '../hooks/useAdvisorAsyncJob'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { useTranslation } from '../i18n'
import { detectSimulationIntent } from '../lib/simulationLinks'
import type { AdvisorAgentTrace, AdvisorConversation, AdvisorReply } from '../types/api'

type ChatMessage =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'assistant'; content: string; reply: AdvisorReply }

function confidenceTone(confidence: string): 'success' | 'warning' | 'neutral' {
  if (confidence === 'high') return 'success'
  if (confidence === 'low') return 'warning'
  return 'neutral'
}

function AgentTracePanel({ trace }: { trace: AdvisorAgentTrace }) {
  const { t } = useTranslation()
  const profileCount = trace.profileAgentInvocations?.length ?? 0
  const planningCount = trace.planningAgentInvocations?.length ?? 0
  const regulationCount = trace.regulationAgentInvocations?.length ?? 0
  const iterations = trace.retrievalAgent?.iterations

  return (
    <details className="rounded-xl border border-dashed border-[var(--color-border)] bg-white p-3 text-xs">
      <summary className="cursor-pointer font-medium text-[var(--color-text)]">
        {t('advisor.agentTraceTitle')}
      </summary>
      <p className="mt-2 text-[var(--color-text-muted)]">{t('advisor.agentTraceHint')}</p>
      <div className="mt-3 space-y-2 text-[var(--color-text-muted)]">
        {typeof iterations === 'number' ? (
          <p>{t('advisor.retrievalIterations', { count: iterations })}</p>
        ) : null}
        {profileCount > 0 ? <p>{t('advisor.profileAgentUsed')}</p> : null}
        {planningCount > 0 ? <p>{t('advisor.planningAgentUsed')}</p> : null}
        {regulationCount > 0 ? <p>{t('advisor.regulationAgentUsed')}</p> : null}
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--color-surface-muted)] p-2 text-[11px] leading-relaxed">
          {JSON.stringify(trace, null, 2)}
        </pre>
      </div>
    </details>
  )
}

function ConversationSummaryCard({ conversation }: { conversation: AdvisorConversation }) {
  const { t } = useTranslation()

  return (
    <div
      className="rounded-xl border border-[var(--color-border)] bg-white p-4 text-sm"
      data-testid="advisor-conversation-summary"
    >
      <p className="font-medium text-[var(--color-text)]">{t('advisor.conversationSummary')}</p>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('advisor.conversationSummaryHint')}</p>
      <p className="mt-3 whitespace-pre-wrap leading-relaxed text-[var(--color-text-muted)]">
        {conversation.summary}
      </p>
    </div>
  )
}

function mapConversation(raw: Record<string, unknown>): AdvisorConversation | null {
  const id = typeof raw.id === 'string' ? raw.id : null
  const summary = typeof raw.summary === 'string' ? raw.summary : null
  if (!id || !summary) return null

  return {
    id,
    title: typeof raw.title === 'string' ? raw.title : 'Advisor chat',
    summary,
    exchangeCount: typeof raw.exchangeCount === 'number' ? raw.exchangeCount : 0,
    lastConfidence: typeof raw.lastConfidence === 'string' ? raw.lastConfidence : null,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : null,
    updatedAt: typeof raw.updatedAt === 'string' ? raw.updatedAt : null,
  }
}

export function AdvisorPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [includeAgentTrace, setIncludeAgentTrace] = useState(false)
  const [preferInstantAnswer, setPreferInstantAnswer] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [sessionMessages, setSessionMessages] = useState<ChatMessage[]>([])
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [handledJobId, setHandledJobId] = useState<string | null>(null)
  const [autoOffloadReason, setAutoOffloadReason] = useState<string | null>(null)

  const asyncJob = useAdvisorAsyncJob(pendingJobId)

  const historyQuery = useQuery({
    queryKey: ['advisor-conversations'],
    queryFn: async () => {
      const data = await advisorApi.listConversations()
      return data.conversations
    },
  })

  const activeConversationQuery = useQuery({
    queryKey: ['advisor-conversation', activeConversationId],
    queryFn: async () => {
      if (!activeConversationId) return null
      const data = await advisorApi.getConversation(activeConversationId)
      return data.conversation
    },
    enabled: Boolean(activeConversationId),
  })

  const activeConversation = activeConversationQuery.data ?? null

  const suggestedPrompts = useMemo(
    () => [
      t('advisor.promptEligibility'),
      t('advisor.promptSyllabus'),
      t('advisor.promptRights'),
    ],
    [t],
  )

  const askMutation = useMutation({
    mutationFn: (question: string) =>
      advisorApi.ask(question, {
        includeAgentTrace,
        conversationId: activeConversationId,
        executionMode: preferInstantAnswer ? 'sync' : 'auto',
      }),
    onSuccess: (data) => {
      if (data.asyncAccepted) {
        setPendingJobId(data.job.id)
        setHandledJobId(null)
        setAutoOffloadReason(data.offloadReason ?? null)
        return
      }

      setAutoOffloadReason(null)
      if (data.conversation) {
        setActiveConversationId(data.conversation.id)
        void queryClient.invalidateQueries({ queryKey: ['advisor-conversations'] })
        void queryClient.setQueryData(
          ['advisor-conversation', data.conversation.id],
          data.conversation,
        )
      }

      setSessionMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.advisor.answer,
          reply: data.advisor,
        },
      ])
    },
  })

  useEffect(() => {
    if (!pendingJobId || !asyncJob.job || handledJobId === pendingJobId) {
      return
    }

    if (asyncJob.job.status === 'completed' && asyncJob.advisorReply) {
      const advisorReply = asyncJob.advisorReply
      const conversationRaw = asyncJob.conversation
      const conversation = conversationRaw ? mapConversation(conversationRaw) : null

      if (conversation) {
        setActiveConversationId(conversation.id)
        void queryClient.invalidateQueries({ queryKey: ['advisor-conversations'] })
        void queryClient.setQueryData(['advisor-conversation', conversation.id], conversation)
      }

      setSessionMessages((current) => [
        ...current,
        {
          id: `assistant-job-${pendingJobId}`,
          role: 'assistant',
          content: advisorReply.answer,
          reply: advisorReply,
        },
      ])
      setHandledJobId(pendingJobId)
      setPendingJobId(null)
      setAutoOffloadReason(null)
    }

    if (asyncJob.job.status === 'failed') {
      setHandledJobId(pendingJobId)
      setPendingJobId(null)
      setAutoOffloadReason(null)
    }
  }, [
    asyncJob.advisorReply,
    asyncJob.conversation,
    asyncJob.job,
    handledJobId,
    pendingJobId,
    queryClient,
  ])

  const deleteMutation = useMutation({
    mutationFn: (conversationId: string) => advisorApi.deleteConversation(conversationId),
    onSuccess: (_data, conversationId) => {
      void queryClient.invalidateQueries({ queryKey: ['advisor-conversations'] })
      if (activeConversationId === conversationId) {
        startNewChat()
      }
    },
  })

  const startNewChat = () => {
    setActiveConversationId(null)
    setSessionMessages([])
    setInput('')
    setPendingJobId(null)
    setHandledJobId(null)
    setAutoOffloadReason(null)
  }

  const openConversation = (conversationId: string) => {
    setActiveConversationId(conversationId)
    setSessionMessages([])
    setInput('')
    setPendingJobId(null)
    setHandledJobId(null)
    setAutoOffloadReason(null)
  }

  const isBusy = askMutation.isPending || asyncJob.isPolling

  const submitQuestion = (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || isBusy) return

    setSessionMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: 'user', content: trimmed },
    ])
    setInput('')
    askMutation.mutate(trimmed)
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    submitQuestion(input)
  }

  const history = historyQuery.data ?? []
  const showStoredSummary = Boolean(activeConversation?.summary)

  const showWhatIfHint = detectSimulationIntent(input)

  const jobStatusMessage =
    asyncJob.job?.status === 'pending'
      ? t('advisor.jobStatusPending')
      : asyncJob.job?.status === 'processing'
        ? t('advisor.jobStatusProcessing')
        : null

  const showJobError =
    asyncJob.isError ||
    (asyncJob.job?.status === 'failed' && handledJobId !== asyncJob.job.id)

  return (
    <div className="animate-fade-in space-y-6" data-testid="advisor-page">
      <PageHeader title={t('advisor.title')} description={t('advisor.subtitle')} />

      <div className="grid gap-6 lg:grid-cols-[minmax(240px,280px)_1fr]">
        <Card className="h-fit space-y-3 p-4" data-testid="advisor-history">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t('advisor.historyTitle')}</h2>
            <Button
              type="button"
              variant="secondary"
              className="h-8 px-2 text-xs"
              onClick={startNewChat}
              data-testid="advisor-new-chat"
            >
              <MessageSquarePlus className="h-4 w-4" aria-hidden />
              {t('advisor.newChat')}
            </Button>
          </div>

          {historyQuery.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <Spinner />
            </div>
          ) : history.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">{t('advisor.noHistory')}</p>
          ) : (
            <ul className="max-h-[28rem] space-y-2 overflow-y-auto">
              {history.map((item) => {
                const isActive = item.id === activeConversationId
                return (
                  <li key={item.id}>
                    <div
                      className={`rounded-xl border p-3 text-sm transition ${
                        isActive
                          ? 'border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5'
                          : 'border-[var(--color-border)] bg-white hover:bg-[var(--color-surface-muted)]'
                      }`}
                    >
                      <button
                        type="button"
                        className="w-full text-start"
                        onClick={() => openConversation(item.id)}
                        data-testid={`advisor-history-item-${item.id}`}
                      >
                        <p className="line-clamp-1 font-medium">{item.title}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-[var(--color-text-muted)]">
                          {item.summary}
                        </p>
                        <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                          {t('advisor.exchanges', { count: item.exchangeCount })}
                        </p>
                      </button>
                      <button
                        type="button"
                        className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--color-danger)]"
                        onClick={() => deleteMutation.mutate(item.id)}
                        aria-label={t('advisor.deleteChat')}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        {t('advisor.deleteChat')}
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>

        <Card className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl bg-[var(--color-primary)]/5 p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
              <Sparkles className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-medium">{t('advisor.groundedTitle')}</p>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('advisor.groundedHint')}</p>
            </div>
          </div>

          {showStoredSummary && activeConversation ? (
            <ConversationSummaryCard conversation={activeConversation} />
          ) : null}

          {sessionMessages.length === 0 && !activeConversationId ? (
            <div className="space-y-3">
              <p className="text-sm text-[var(--color-text-muted)]">{t('advisor.emptyState')}</p>
              <div className="flex flex-wrap gap-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => submitQuestion(prompt)}
                    className="rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-left text-sm transition hover:border-[var(--color-primary)]/30 hover:bg-[var(--color-surface-muted)]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-h-[32rem] space-y-4 overflow-y-auto pe-1">
              {sessionMessages.map((message) => (
                <div
                  key={message.id}
                  className={
                    message.role === 'user'
                      ? 'ms-8 rounded-2xl bg-[var(--color-primary)] px-4 py-3 text-sm text-white'
                      : 'me-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-4 py-3 text-sm'
                  }
                >
                  {message.role === 'assistant' ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Bot className="h-4 w-4 text-[var(--color-primary)]" aria-hidden />
                        <Badge tone={confidenceTone(message.reply.confidence)}>
                          {t(`advisor.confidence.${message.reply.confidence}`)}
                        </Badge>
                      </div>
                      <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                      {message.reply.courseIds.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {message.reply.courseIds.map((courseId) => (
                            <Link
                              key={courseId}
                              to={`/catalog?course=${courseId}`}
                              className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-primary)] ring-1 ring-[var(--color-primary)]/20"
                            >
                              {courseId}
                            </Link>
                          ))}
                        </div>
                      ) : null}
                      {message.reply.contacts.length > 0 ? (
                        <div className="text-xs text-[var(--color-text-muted)]">
                          <p className="font-medium text-[var(--color-text)]">{t('advisor.contacts')}</p>
                          <ul className="mt-1 list-disc ps-4">
                            {message.reply.contacts.map((contact) => (
                              <li key={contact}>{contact}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {message.reply.agentTrace ? (
                        <AgentTracePanel trace={message.reply.agentTrace} />
                      ) : null}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                      {detectSimulationIntent(message.content) ? (
                        <OpenInWhatIfLink
                          text={message.content}
                          testId={`advisor-what-if-${message.id}`}
                        />
                      ) : null}
                    </div>
                  )}
                </div>
              ))}
              {isBusy ? (
                <div
                  className="me-8 flex items-center gap-2 rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-3 text-sm text-[var(--color-text-muted)]"
                  data-testid="advisor-thinking"
                >
                  <Spinner />
                  {jobStatusMessage ??
                    (autoOffloadReason ? t('advisor.autoOffloadRunning') : t('advisor.thinking'))}
                </div>
              ) : null}
            </div>
          )}

          {showJobError || askMutation.isError ? (
            <p className="text-sm text-[var(--color-danger)]" data-testid="advisor-error">
              {asyncJob.job?.status === 'failed' && asyncJob.job.error
                ? asyncJob.job.error
                : ((askMutation.error ?? asyncJob.error) as Error | undefined)?.message ||
                  t('advisor.error')}
              {asyncJob.job?.status === 'failed' ? ` ${t('advisor.jobStatusFailed')}` : ''}
            </p>
          ) : null}

          <form onSubmit={handleSubmit} className="space-y-3 border-t border-[var(--color-border)] pt-4">
            <label className="flex items-start gap-2 text-sm text-[var(--color-text-muted)]">
              <input
                type="checkbox"
                checked={preferInstantAnswer}
                onChange={(event) => setPreferInstantAnswer(event.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-primary)]"
                data-testid="advisor-prefer-instant"
              />
              <span>
                {t('advisor.preferInstantAnswer')}
                <span className="mt-1 block text-xs">{t('advisor.preferInstantAnswerHint')}</span>
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <input
                type="checkbox"
                checked={includeAgentTrace}
                onChange={(event) => setIncludeAgentTrace(event.target.checked)}
                className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-primary)]"
                data-testid="advisor-show-trace"
              />
              {t('advisor.showAgentTrace')}
            </label>
            <div className="flex gap-2">
              <label className="sr-only" htmlFor="advisor-question">
                {t('advisor.inputLabel')}
              </label>
              <input
                id="advisor-question"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={t('advisor.inputPlaceholder')}
                className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
                disabled={isBusy}
                data-testid="advisor-input"
              />
              <Button
                type="submit"
                loading={isBusy}
                disabled={!input.trim()}
                data-testid="advisor-submit"
              >
                <Send className="h-4 w-4" />
                <span className="sr-only">{t('advisor.send')}</span>
              </Button>
            </div>
            {showWhatIfHint ? (
              <div
                className="rounded-xl border border-dashed border-[var(--color-primary)]/25 bg-[var(--color-primary)]/5 px-3 py-2"
                data-testid="advisor-what-if-hint"
              >
                <p className="text-xs text-[var(--color-text-muted)]">{t('advisor.openInWhatIfHint')}</p>
                <OpenInWhatIfLink text={input.trim()} testId="advisor-what-if-input" className="mt-1 text-sm" />
              </div>
            ) : null}
          </form>
        </Card>
      </div>
    </div>
  )
}
