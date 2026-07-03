import { Paperclip, Send, Sparkles, Square, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useRef, useState } from 'react'
import { Button } from '../ui/Button'
import { cn } from '../../lib/utils'
import { useTranslation } from '../../i18n'
import { useAgentMotionEnabled } from './agentMotion'

type AgentComposerProps = {
  onSend: (content: string, attachments?: File[]) => void
  onStop?: () => void
  disabled?: boolean
  isStreaming?: boolean
  initialValue?: string
}

export function AgentComposer({
  onSend,
  onStop,
  disabled,
  isStreaming,
  initialValue = '',
}: AgentComposerProps) {
  const { t } = useTranslation()
  const motionEnabled = useAgentMotionEnabled()
  const [value, setValue] = useState(initialValue)
  const [attachment, setAttachment] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSend = Boolean(value.trim() || attachment) && !disabled && !isStreaming

  const handleSend = () => {
    const content = value.trim() || (attachment ? t('agent.importTranscriptDefault') : '')
    if (!content && !attachment) return
    onSend(content, attachment ? [attachment] : undefined)
    setValue('')
    setAttachment(null)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSend) handleSend()
    }
  }

  const Wrapper = motionEnabled ? motion.div : 'div'

  return (
    <Wrapper
      className="mx-auto max-w-3xl"
      data-testid="agent-composer"
      {...(motionEnabled
        ? {
            initial: { opacity: 0, y: 16 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1], delay: 0.05 },
          }
        : {})}
    >
      <AnimatePresence>
        {attachment ? (
          <motion.div
            key="attachment"
            initial={{ opacity: 0, height: 0, marginBottom: 0 }}
            animate={{ opacity: 1, height: 'auto', marginBottom: 8 }}
            exit={{ opacity: 0, height: 0, marginBottom: 0 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white/90 px-3 py-2 text-sm shadow-sm">
              <Paperclip className="h-4 w-4 shrink-0 text-[var(--color-primary)]" />
              <span className="min-w-0 flex-1 truncate">{attachment.name}</span>
              <button
                type="button"
                onClick={() => setAttachment(null)}
                className="rounded-lg p-1.5 transition hover:bg-[var(--color-surface-muted)]"
                aria-label={t('agent.removeAttachment')}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div
        className={cn(
          'agent-composer-shell flex items-end gap-1 rounded-[1.35rem] border border-[var(--color-border)]/80',
          'bg-white/95 px-2 py-2 backdrop-blur-md transition-shadow duration-300',
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) setAttachment(file)
            event.target.value = ''
          }}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="shrink-0 rounded-xl px-2.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || isStreaming}
          aria-label={t('agent.attachFile')}
        >
          <Paperclip className="h-4 w-4" />
        </Button>

        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={t('agent.composerPlaceholder')}
          className={cn(
            'max-h-40 min-h-[48px] flex-1 resize-none bg-transparent py-3 text-sm leading-relaxed outline-none',
            'placeholder:text-[var(--color-text-muted)]/80',
          )}
          data-testid="agent-composer-input"
        />

        {isStreaming ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0 rounded-xl px-2.5"
            onClick={onStop}
            aria-label={t('agent.stop')}
          >
            <Square className="h-4 w-4 fill-current text-rose-600" />
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            className={cn(
              'shrink-0 rounded-xl px-3 shadow-sm transition-all',
              canSend && 'shadow-md shadow-[var(--color-primary)]/20',
            )}
            disabled={!canSend}
            onClick={handleSend}
            data-testid="agent-composer-send"
          >
            {canSend ? <Send className="h-4 w-4" /> : <Sparkles className="h-4 w-4 opacity-50" />}
          </Button>
        )}
      </div>
      <p className="mt-2.5 text-center text-[0.7rem] text-[var(--color-text-muted)]">{t('agent.composerHint')}</p>
    </Wrapper>
  )
}
