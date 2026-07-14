import { useMemo, useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Bot, Send, Sparkles, MessageSquare } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { advisorApi } from '../api/endpoints'
import { Badge, PageHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { useTranslation } from '../i18n'
import type { AdvisorReply } from '../types/api'

type ChatMessage =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'assistant'; content: string; reply?: AdvisorReply }

function confidenceTone(confidence: string): 'success' | 'warning' | 'neutral' {
  if (confidence === 'high') return 'success'
  if (confidence === 'low') return 'warning'
  return 'neutral'
}

export function AdvisorPage() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
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

  const submitQuestion = async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || isStreaming) return

    const userMessageId = `user-${Date.now()}`
    const assistantMessageId = `assistant-${Date.now()}`

    setMessages((current) => [
      ...current,
      { id: userMessageId, role: 'user', content: trimmed },
      { id: assistantMessageId, role: 'assistant', content: '' }, // placeholder for streaming
    ])
    setInput('')
    setIsStreaming(true)

    try {
      const response = await advisorApi.askStream(trimmed)
      if (!response.body) throw new Error('No response body')
      
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value, { stream: true })
        const events = chunk.split('\n\n')
        
        for (const event of events) {
          if (!event.trim()) continue
          if (event.startsWith('data: ')) {
            const dataStr = event.slice(6)
            try {
              const data = JSON.parse(dataStr)
              if (data.type === 'chunk') {
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
                        // Backfill content from the final answer if no text
                        // chunks were streamed (e.g. out-of-scope, boundary,
                        // or clarification responses).
                        content: m.content || advisor?.answer || '',
                      } 
                    : m
                  )
                )
              }
            } catch (err) {
              console.error('Failed to parse SSE JSON:', err)
            }
          }
        }
      }
    } catch (err) {
      console.error('Stream error:', err)
      // fallback handling...
    } finally {
      setIsStreaming(false)
    }
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    submitQuestion(input)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] relative animate-fade-in" data-testid="advisor-page">
      <div className="shrink-0 mb-6">
        <PageHeader
          title={t('advisor.title')}
          description={t('advisor.subtitle')}
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-6 pb-32 pe-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-6 animate-slide-in-up">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-primary)]/10 text-[var(--color-primary)] ring-8 ring-[var(--color-primary)]/5">
              <Sparkles className="h-8 w-8" aria-hidden />
            </div>
            <div className="max-w-md">
              <h2 className="text-xl font-semibold text-[var(--color-text)]">
                {t('advisor.groundedTitle')}
              </h2>
              <p className="mt-2 text-[var(--color-text-muted)]">
                {t('advisor.groundedHint')}
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 max-w-2xl mt-4">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submitQuestion(prompt)}
                  className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white px-4 py-2 text-sm text-[var(--color-text)] shadow-sm transition hover:border-[var(--color-primary)]/40 hover:shadow-md"
                >
                  <MessageSquare className="h-4 w-4 text-[var(--color-primary)]/70" />
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex animate-slide-in-up ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-5 py-4 shadow-soft ${
                    message.role === 'user'
                      ? 'bg-[var(--color-primary)] text-white rounded-tr-sm'
                      : 'bg-white border border-[var(--color-border)] text-[var(--color-text)] rounded-tl-sm'
                  }`}
                >
                  {message.role === 'assistant' ? (
                    <div className="space-y-4">
                      {message.reply && (
                        <div className="flex items-center gap-2 border-b border-[var(--color-border)]/50 pb-2">
                          <Bot className="h-4 w-4 text-[var(--color-primary)]" aria-hidden />
                          <Badge tone={confidenceTone(message.reply.confidence)}>
                            {t(`advisor.confidence.${message.reply.confidence}`)}
                          </Badge>
                        </div>
                      )}
                      
                      <div className="prose prose-sm prose-slate max-w-none prose-a:text-[var(--color-primary)] prose-a:no-underline hover:prose-a:underline">
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                        {!message.reply && isStreaming && (
                          <span className="inline-block w-1.5 h-4 ml-1 bg-[var(--color-primary)]/70 animate-pulse" />
                        )}
                      </div>

                      {message.reply && (message.reply.courseIds.length > 0 || message.reply.contacts.length > 0 || (message.reply.sources && message.reply.sources.length > 0)) && (
                        <div className="mt-4 flex flex-col gap-3 pt-3 border-t border-[var(--color-border)]/50">
                          {message.reply.courseIds.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {message.reply.courseIds.map((courseId) => (
                                <Link
                                  key={courseId}
                                  to={`/catalog?course=${courseId}`}
                                  className="rounded-full bg-[var(--color-primary)]/5 px-2.5 py-1 text-xs font-medium text-[var(--color-primary)] ring-1 ring-[var(--color-primary)]/20 hover:bg-[var(--color-primary)]/10 transition"
                                >
                                  {courseId}
                                </Link>
                              ))}
                            </div>
                          )}
                          {message.reply.contacts.length > 0 && (
                            <div className="text-xs text-[var(--color-text-muted)]">
                              <p className="font-medium text-[var(--color-text)] mb-1">{t('advisor.contacts')}</p>
                              <ul className="list-disc ps-4 space-y-0.5">
                                {message.reply.contacts.map((contact) => (
                                  <li key={contact}>{contact}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {message.reply.sources && message.reply.sources.length > 0 && (
                            <details className="text-xs text-[var(--color-text-muted)] group">
                              <summary className="font-medium text-[var(--color-primary)] cursor-pointer hover:underline mb-1 flex items-center">
                                Sources Used ({message.reply.sources.length})
                              </summary>
                              <ul className="list-disc ps-4 space-y-0.5 mt-2">
                                {message.reply.sources.map((source: string) => (
                                  <li key={source} className="break-all">{source}</li>
                                ))}
                              </ul>
                            </details>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                  )}
                </div>
              </div>
            ))}
            
            {isStreaming && messages[messages.length - 1]?.role !== 'assistant' && (
              <div className="flex justify-start animate-slide-in-up">
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-white border border-[var(--color-border)] shadow-soft px-5 py-4">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 rounded-full bg-[var(--color-primary)]/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 rounded-full bg-[var(--color-primary)]/60 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 rounded-full bg-[var(--color-primary)]/60 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="absolute bottom-0 left-0 right-0 pt-4 pb-2 bg-gradient-to-t from-[var(--color-surface)] via-[var(--color-surface)] to-transparent">
        {askMutation.isError && (
          <div className="mb-2 text-center text-sm text-[var(--color-danger)] bg-white/80 backdrop-blur rounded-lg py-2 border border-[var(--color-danger)]/20">
            {(askMutation.error as Error).message || t('advisor.error')}
          </div>
        )}
        
        <form 
          onSubmit={handleSubmit} 
          className="agent-composer-shell flex gap-2 rounded-2xl p-2 relative shadow-card"
        >
          <label className="sr-only" htmlFor="advisor-question">
            {t('advisor.inputLabel')}
          </label>
          <input
            id="advisor-question"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t('advisor.inputPlaceholder')}
            className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm outline-none text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] disabled:opacity-50"
            disabled={isStreaming}
            data-testid="advisor-input"
          />
          <Button
            type="submit"
            loading={isStreaming}
            disabled={!input.trim()}
            className="rounded-xl px-4"
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
