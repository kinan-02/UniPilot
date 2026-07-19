import { useMemo, useState, useRef, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Bot, Send, Sparkles, MessageSquare, BookOpen, ChevronDown, CheckCircle2, AlertCircle, Info } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { advisorApi } from '../api/endpoints'
import { SourcesPanel, countSources, sourceGroups } from '../components/advisor/SourcesPanel'
import { PageHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { useTranslation } from '../i18n'
import type { AdvisorReply } from '../types/api'

type ChatMessage =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'assistant'; content: string; reply?: AdvisorReply }

/* ── Helpers ── */

/** Strip JSON envelope if the LLM returned {"answer_text": "..."} instead of plain text */
function stripJsonEnvelope(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return raw
  try {
    const parsed = JSON.parse(trimmed)
    if (typeof parsed === 'object' && parsed !== null && typeof parsed.answer_text === 'string') {
      return parsed.answer_text
    }
  } catch {
    // Not valid JSON yet (still streaming) — try a best-effort extraction
    const match = trimmed.match(/"answer_text"\s*:\s*"([\s\S]*)/)
    if (match) {
      // Unescape the partial JSON string
      let extracted = match[1]
      // Remove trailing incomplete JSON: "}\n or just trailing "
      extracted = extracted.replace(/"\s*,?\s*\}?\s*$/, '')
      // Unescape common JSON escapes
      extracted = extracted.replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
      if (extracted.length > 0) return extracted
    }
  }
  return raw
}

function confidenceConfig(confidence: string): { icon: typeof CheckCircle2; label: string; color: string; bg: string } {
  switch (confidence) {
    case 'high':
      return { icon: CheckCircle2, label: 'High confidence', color: 'text-emerald-600', bg: 'bg-emerald-50' }
    case 'medium':
      return { icon: Info, label: 'Medium confidence', color: 'text-amber-600', bg: 'bg-amber-50' }
    case 'low':
      return { icon: AlertCircle, label: 'Low confidence', color: 'text-red-500', bg: 'bg-red-50' }
    default:
      return { icon: Info, label: 'Confidence unknown', color: 'text-gray-500', bg: 'bg-gray-50' }
  }
}


/* ── Confidence badge ── */
function ConfidenceBadge({ confidence }: { confidence: string }) {
  const config = confidenceConfig(confidence)
  const Icon = config.icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.color} ${config.bg}`}>
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  )
}

/* ── Citation footer ──
 * A citation line, not a data dump. Inlining every reference put 46 course chips
 * under one live answer -- a wall nobody reads. At INLINE_SOURCE_LIMIT or fewer
 * the references sit inline, where naming them is genuinely useful (asking about
 * one course should show that course). Above it, the footer collapses to a single
 * control that opens the full list in a side panel. */
const INLINE_SOURCE_LIMIT = 3

function MessageMetadata({ reply }: { reply: AdvisorReply }) {
  const [isPanelOpen, setPanelOpen] = useState(false)
  const groups = useMemo(() => sourceGroups(reply), [reply])
  const total = countSources(groups)

  if (total === 0) return null

  const isInline = total <= INLINE_SOURCE_LIMIT

  return (
    <div className="mt-3 pt-3 border-t border-[rgba(79,70,229,0.08)]">
      {isInline ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-[var(--color-text-muted)]">
            <BookOpen className="mb-0.5 me-1 inline h-3.5 w-3.5" />
            Based on
          </span>
          {groups.courses.map((course) => (
            <Link
              key={course.id}
              to={`/catalog?course=${course.id}`}
              dir="auto"
              title={course.id}
              className="rounded-lg bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-primary)] ring-1 ring-[var(--color-primary)]/15 hover:ring-[var(--color-primary)]/30 hover:bg-[var(--color-primary)]/5 transition-all"
            >
              {course.name}
            </Link>
          ))}
          {groups.sources.map((source) => (
            <span
              key={source}
              dir="auto"
              className="rounded-lg bg-[var(--color-primary)]/5 px-2.5 py-1 text-xs text-[var(--color-text-muted)]"
            >
              {source.replace(/^search: /, '')}
            </span>
          ))}
          {groups.contacts.map((contact) => (
            <span key={contact} dir="auto" className="text-xs text-[var(--color-text-muted)]">
              {contact}
            </span>
          ))}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          data-testid="advisor-sources-toggle"
          aria-haspopup="dialog"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 -mx-2 text-xs font-medium text-[var(--color-primary)] hover:bg-[var(--color-primary)]/5 transition-colors"
        >
          <BookOpen className="h-3.5 w-3.5" />
          Based on {total} sources
          <ChevronDown className="h-3.5 w-3.5 -rotate-90 rtl:rotate-90" />
        </button>
      )}

      <SourcesPanel groups={groups} isOpen={isPanelOpen} onClose={() => setPanelOpen(false)} />
    </div>
  )
}

/* ── Assistant message component ── */
function AssistantMessage({
  message,
  isCurrentlyStreaming,
  progress,
}: {
  message: ChatMessage & { role: 'assistant' }
  isCurrentlyStreaming: boolean
  progress?: string | null
}) {
  const displayContent = useMemo(() => stripJsonEnvelope(message.content), [message.content])
  const isThinking = isCurrentlyStreaming && !displayContent

  return (
    <div className="flex items-start gap-3 advisor-msg-in">
      <div className={`advisor-avatar ${isCurrentlyStreaming ? 'agent-avatar-live' : ''}`}>
        <Bot />
      </div>
      <div className="advisor-bubble-assistant rounded-2xl rounded-tl-md px-5 py-4 max-w-[85%] min-w-0">
        {isThinking ? (
          <div className="flex items-center gap-3">
            <div className="advisor-thinking-dots flex gap-1.5">
              <span />
              <span />
              <span />
            </div>
            <span dir="auto" className="text-sm text-[var(--color-text-muted)]" data-testid="advisor-progress">
              {progress ?? 'Analyzing your question…'}
            </span>
          </div>
        ) : (
          <div className="space-y-3">
            {/* No `advisor-stream-cursor` here: the answer is composed after the
                loop concludes and arrives in one `chunk`, so content goes empty ->
                whole in a single setState. The typing cursor was never on screen
                for a frame -- it read as a working feature and was not one. */}
            <div dir="auto" className="advisor-prose text-sm text-[var(--color-text)]">
              <ReactMarkdown>{displayContent}</ReactMarkdown>
            </div>

            {/* Show metadata only after streaming is done */}
            {!isCurrentlyStreaming && message.reply && (
              <div className="space-y-3 animate-fade-in">
                <div className="flex items-center gap-2">
                  <ConfidenceBadge confidence={message.reply.confidence} />
                </div>
                <MessageMetadata reply={message.reply} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Main page component ── */
export function AdvisorPage() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeStreamId, setActiveStreamId] = useState<string | null>(null)
  // Latest `progress` event. The answer arrives in one piece at the end, so for
  // a question that takes three minutes this is the only thing that changes on
  // screen the whole time.
  const [progress, setProgress] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  const submitQuestion = useCallback(async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || isStreaming) return

    const userMessageId = `user-${Date.now()}`
    const assistantMessageId = `assistant-${Date.now()}`

    setMessages((current) => [
      ...current,
      { id: userMessageId, role: 'user', content: trimmed },
      { id: assistantMessageId, role: 'assistant', content: '' },
    ])
    setInput('')
    setIsStreaming(true)
    setActiveStreamId(assistantMessageId)

    try {
      const response = await advisorApi.askStream(trimmed)
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`)
      }
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      const handleEvent = (event: string) => {
        if (!event.trim() || !event.startsWith('data: ')) return
        try {
          const data = JSON.parse(event.slice(6))
          if (data.type === 'progress') {
            setProgress(data.text)
          } else if (data.type === 'chunk') {
            setMessages((current) =>
              current.map(m => m.id === assistantMessageId
                ? { ...m, content: m.content + data.text }
                : m
              )
            )
          } else if (data.type === 'final') {
            const advisor = data.data?.advisor
            setMessages((current) =>
              current.map(m => m.id === assistantMessageId
                ? {
                    ...m,
                    reply: advisor,
                    content: m.content || advisor?.answer || '',
                  }
                : m
              )
            )
          } else if (data.type === 'error') {
            console.error('SSE error event:', data.error)
            setMessages((current) =>
              current.map(m => m.id === assistantMessageId
                ? { ...m, content: m.content || 'Something went wrong. Please try again.' }
                : m
              )
            )
          }
        } catch (err) {
          console.error('Failed to parse SSE JSON:', err)
        }
      }

      // An SSE event can straddle a read boundary, and without carrying the
      // trailing partial across reads BOTH halves are lost: the first fails
      // JSON.parse, the second no longer starts with `data: ` and is skipped in
      // silence. `final` carries the whole advisor payload, so losing it stripped
      // the confidence badge and source list off an answer whose text -- already
      // delivered by `chunk` -- still looked perfectly fine.
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''
        events.forEach(handleEvent)
      }
      // Normally empty -- the server terminates every event with a blank line.
      handleEvent(buffer)
    } catch (err) {
      console.error('Stream error:', err)
      setMessages((current) =>
        current.map(m => m.id === assistantMessageId
          ? { ...m, content: m.content || 'Connection error. Please try again.' }
          : m
        )
      )
    } finally {
      setIsStreaming(false)
      setActiveStreamId(null)
      setProgress(null)
    }
  }, [isStreaming])

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    submitQuestion(input)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] relative animate-fade-in" data-testid="advisor-page">
      <div className="shrink-0 mb-4">
        <PageHeader
          title={t('advisor.title')}
          description={t('advisor.subtitle')}
        />
      </div>

      <div className="flex-1 overflow-y-auto pb-32 pe-2">
        {messages.length === 0 ? (
          /* ── Empty state ── */
          <div className="flex flex-col items-center justify-center h-full text-center space-y-8 animate-fade-in">
            <div className="relative">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--color-primary)] to-purple-600 text-white shadow-lg shadow-indigo-500/20">
                <Sparkles className="h-10 w-10" aria-hidden />
              </div>
              <div className="absolute -bottom-1 -right-1 h-5 w-5 rounded-full bg-emerald-400 border-2 border-white shadow-sm" />
            </div>
            <div className="max-w-md space-y-2">
              <h2 className="text-2xl font-bold text-[var(--color-text)]">
                {t('advisor.groundedTitle')}
              </h2>
              <p className="text-[var(--color-text-muted)] leading-relaxed">
                {t('advisor.groundedHint')}
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2.5 max-w-2xl">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submitQuestion(prompt)}
                  className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm text-[var(--color-text)] shadow-sm transition-all hover:border-[var(--color-primary)]/30 hover:shadow-md hover:-translate-y-0.5 active:translate-y-0"
                >
                  <MessageSquare className="h-4 w-4 text-[var(--color-primary)]/60" />
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── Chat messages ── */
          <div className="space-y-5 py-2">
            {messages.map((message) => {
              if (message.role === 'user') {
                return (
                  <div key={message.id} className="flex justify-end advisor-msg-in">
                    <div className="advisor-bubble-user rounded-2xl rounded-tr-md px-5 py-3.5 max-w-[85%]">
                      {/* dir="auto": <html> is dir="rtl" for the Hebrew UI, so an
                          English message inherits RTL and bidi throws its final
                          punctuation to the visual left ("?How many credits..."). */}
                      <p dir="auto" className="whitespace-pre-wrap leading-relaxed text-sm">{message.content}</p>
                    </div>
                  </div>
                )
              }
              return (
                <AssistantMessage
                  key={message.id}
                  message={message as ChatMessage & { role: 'assistant' }}
                  isCurrentlyStreaming={isStreaming && message.id === activeStreamId}
                  progress={message.id === activeStreamId ? progress : null}
                />
              )
            })}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* ── Input area ── */}
      <div className="absolute bottom-0 left-0 right-0 pt-6 pb-2 bg-gradient-to-t from-[var(--color-surface)] via-[var(--color-surface)] to-transparent">
        {askMutation.isError && (
          <div className="mb-3 text-center text-sm text-[var(--color-danger)] bg-white/80 backdrop-blur-sm rounded-xl py-2.5 px-4 border border-[var(--color-danger)]/15 shadow-sm">
            {(askMutation.error as Error).message || t('advisor.error')}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="agent-composer-shell flex items-center gap-2 rounded-2xl p-2 relative"
        >
          <label className="sr-only" htmlFor="advisor-question">
            {t('advisor.inputLabel')}
          </label>
          <input
            id="advisor-question"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={isStreaming ? 'Waiting for response…' : t('advisor.inputPlaceholder')}
            className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm outline-none text-[var(--color-text)] placeholder:text-[var(--color-text-muted)]/60 disabled:opacity-40"
            disabled={isStreaming}
            data-testid="advisor-input"
          />
          <Button
            type="submit"
            loading={isStreaming}
            disabled={!input.trim() || isStreaming}
            className="rounded-xl px-4 shadow-sm"
            data-testid="advisor-submit"
          >
            <Send className="h-4 w-4" />
            <span className="sr-only">{t('advisor.send')}</span>
          </Button>
        </form>
      </div>
    </div>
  )
}
