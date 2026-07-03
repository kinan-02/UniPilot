import { apiRequest, apiUpload } from '../lib/api'
import { streamAgentMessage } from '../lib/agentStream'
import type {
  AgentConversation,
  AgentMessage,
  AgentStreamEvent,
} from '../types/agent'

export const agentConversationsApi = {
  list: () =>
    apiRequest<{ conversations: AgentConversation[] }>('/agent/conversations'),

  create: (title?: string) =>
    apiRequest<{ conversation: AgentConversation }>('/agent/conversations', {
      method: 'POST',
      body: title ? { title } : {},
    }),

  get: (conversationId: string) =>
    apiRequest<{ conversation: AgentConversation; messages: AgentMessage[] }>(
      `/agent/conversations/${conversationId}`,
    ),

  sendMessageJson: (conversationId: string, content: string) =>
    apiRequest<{
      text: string
      messageId: string
      runId: string
      events: AgentStreamEvent[]
    }>(`/agent/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: { content },
    }),

  streamMessage: streamAgentMessage,

  uploadTranscriptMessage: (
    conversationId: string,
    content: string,
    file: File,
  ) =>
    apiUpload<{
      text: string
      messageId: string
      runId: string
      events: AgentStreamEvent[]
    }>(`/agent/conversations/${conversationId}/messages`, (() => {
      const form = new FormData()
      form.set('content', content)
      form.append('file', file)
      return form
    })()),

  confirmAction: (conversationId: string, actionId: string) =>
    apiRequest<Record<string, unknown>>(
      `/agent/conversations/${conversationId}/actions/${actionId}/confirm`,
      { method: 'POST' },
    ),

  rejectAction: (conversationId: string, actionId: string) =>
    apiRequest<{ proposal: Record<string, unknown> }>(
      `/agent/conversations/${conversationId}/actions/${actionId}/reject`,
      { method: 'POST' },
    ),
}
