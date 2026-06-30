import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Bot, Send, Sparkles } from 'lucide-react'
import { advisorApi } from '../api/endpoints'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { useTranslation } from '../i18n'
import type { AdvisorReply } from '../types/api'

type ChatMessage =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'assistant'; content: string; reply: AdvisorReply }

function confidenceTone(confidence: string): 'success' | 'warning' | 'neutral' {
  if (confidence === 'high') return 'success'
  if (confidence === 'low') return 'warning'
  return 'neutral'
}

export function AdvisorPage() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])

  const suggestedPrompts = useMemo(
    () => [
      t('advisor.promptEligibility'),
      t('advisor.promptSyllabus'),
      t('advisor.promptRights'),
    ],
    [t],
  )

  const askMutation = useMutation({
    mutationFn: (question: string) => advisorApi.ask(question),
    onSuccess: (data, question) => {
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.advisor.answer,
          reply: data.advisor,
        },
      ])
      void question
    },
  })

  const submitQuestion = (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || askMutation.isPending) return

    setMessages((current) => [
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

  return (
    <div className="animate-fade-in space-y-6" data-testid="advisor-page">
      <PageHeader
        title={t('advisor.title')}
        description={t('advisor.subtitle')}
      />

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

        {messages.length === 0 ? (
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
            {messages.map((message) => (
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
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                )}
              </div>
            ))}
            {askMutation.isPending ? (
              <div className="me-8 flex items-center gap-2 rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-3 text-sm text-[var(--color-text-muted)]">
                <Spinner />
                {t('advisor.thinking')}
              </div>
            ) : null}
          </div>
        )}

        {askMutation.isError ? (
          <p className="text-sm text-[var(--color-danger)]" data-testid="advisor-error">
            {(askMutation.error as Error).message || t('advisor.error')}
          </p>
        ) : null}

        <form onSubmit={handleSubmit} className="flex gap-2 border-t border-[var(--color-border)] pt-4">
          <label className="sr-only" htmlFor="advisor-question">
            {t('advisor.inputLabel')}
          </label>
          <input
            id="advisor-question"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t('advisor.inputPlaceholder')}
            className="min-w-0 flex-1 rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
            disabled={askMutation.isPending}
            data-testid="advisor-input"
          />
          <Button
            type="submit"
            loading={askMutation.isPending}
            disabled={!input.trim()}
            data-testid="advisor-submit"
          >
            <Send className="h-4 w-4" />
            <span className="sr-only">{t('advisor.send')}</span>
          </Button>
        </form>
      </Card>
    </div>
  )
}
