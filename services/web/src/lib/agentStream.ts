import { getApiBaseUrl } from './api'
import type { AgentStreamEvent } from '../types/agent'

function parseSseChunk(buffer: string): { events: AgentStreamEvent[]; remainder: string } {
  const events: AgentStreamEvent[] = []
  const parts = buffer.split('\n\n')
  const remainder = parts.pop() ?? ''

  for (const part of parts) {
    for (const line of part.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (!payload || payload === '[DONE]') continue
      try {
        events.push(JSON.parse(payload) as AgentStreamEvent)
      } catch {
        // ignore malformed chunks
      }
    }
  }

  return { events, remainder }
}

export async function streamAgentMessage(
  conversationId: string,
  content: string,
  {
    onEvent,
    signal,
    attachments,
  }: {
    onEvent: (event: AgentStreamEvent) => void
    signal?: AbortSignal
    attachments?: File[]
  },
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
  }

  let body: BodyInit
  if (attachments?.length) {
    const form = new FormData()
    form.set('content', content)
    attachments.forEach((file) => form.append('file', file))
    body = form
  } else {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify({ content })
  }

  const response = await fetch(
    `${getApiBaseUrl()}/agent/conversations/${conversationId}/messages?stream=true`,
    {
      method: 'POST',
      headers,
      body,
      signal,
      credentials: 'include',
    },
  )

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const payload = (await response.json()) as { error?: string }
      if (payload.error) message = payload.error
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Streaming is not supported in this browser')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.remainder
    parsed.events.forEach(onEvent)
  }

  if (buffer.trim()) {
    parseSseChunk(`${buffer}\n\n`).events.forEach(onEvent)
  }
}
