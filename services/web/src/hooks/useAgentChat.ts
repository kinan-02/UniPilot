import { useCallback, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentConversationsApi } from '../api/agentConversations'
import type {
  AgentChatMessage,
  AgentConversation,
  AgentLiveTurn,
  AgentMessage,
  AgentProposedAction,
  AgentStepState,
  AgentStreamEvent,
  AgentStructuredBlock,
} from '../types/agent'

function toAssistantMessage(message: AgentMessage): AgentChatMessage {
  const actions: AgentProposedAction[] = []
  const blocks = [...(message.structuredBlocks ?? [])]

  return {
    kind: 'assistant',
    id: message.id,
    content: message.content,
    blocks,
    actions,
    createdAt: message.createdAt,
    runId: message.runId,
  }
}

function toUserMessage(message: AgentMessage): AgentChatMessage {
  return {
    kind: 'user',
    id: message.id,
    content: message.content,
    createdAt: message.createdAt,
    attachments: message.attachments,
  }
}

function mapStoredMessages(messages: AgentMessage[]): AgentChatMessage[] {
  return messages.map((message) =>
    message.role === 'user' ? toUserMessage(message) : toAssistantMessage(message),
  )
}

function initialLiveTurn(): AgentLiveTurn {
  return {
    text: '',
    blocks: [],
    actions: [],
    steps: [],
    suggestedPrompts: [],
    warnings: [],
    status: 'streaming',
  }
}

function applyStreamEvent(turn: AgentLiveTurn, event: AgentStreamEvent): AgentLiveTurn {
  const next: AgentLiveTurn = {
    ...turn,
    steps: [...turn.steps],
    blocks: [...turn.blocks],
    actions: [...turn.actions],
    suggestedPrompts: [...turn.suggestedPrompts],
    warnings: [...turn.warnings],
  }

  if (event.runId) next.runId = event.runId

  if (event.type === 'agent.step.started' && event.label) {
    const existing = next.steps.find((step) => step.label === event.label)
    if (existing) {
      existing.status = 'running'
    } else {
      next.steps.push({ label: event.label, status: 'running' })
    }
  }

  if (event.type === 'agent.step.completed' && event.label) {
    const step = next.steps.find((item) => item.label === event.label)
    if (step) {
      step.status = 'completed'
    } else {
      next.steps.push({ label: event.label, status: 'completed' })
    }
  }

  if (event.type === 'agent.step.failed' && event.label) {
    const step = next.steps.find((item) => item.label === event.label)
    if (step) {
      step.status = 'failed'
    } else {
      next.steps.push({ label: event.label, status: 'failed' })
    }
  }

  if (event.type === 'structured_output' && event.block) {
    next.blocks.push(event.block)
  }

  if (event.type === 'action.proposed' && event.action) {
    next.actions.push(event.action)
  }

  if (event.type === 'message.delta' && event.text) {
    next.text += event.text
  }

  if (event.type === 'message.completed') {
    if (event.text) next.text = event.text
    next.status = 'completed'
    if (event.messageId) {
      next.runId = event.runId ?? next.runId
    }
  }

  if (event.type === 'run.failed') {
    next.status = 'failed'
    next.error = event.error ?? 'Agent run failed'
  }

  if (event.type === 'run.completed') {
    next.status = next.status === 'failed' ? 'failed' : 'completed'
  }

  return next
}

function extractSuggestedPrompts(blocks: AgentStructuredBlock[]): string[] {
  for (const block of blocks) {
    if (block.type === 'SourceSummaryBlock') {
      const prompts = block.data.suggestedPrompts
      if (Array.isArray(prompts)) {
        return prompts.filter((item): item is string => typeof item === 'string')
      }
    }
  }
  return []
}

export function useAgentChat(conversationId: string | null) {
  const queryClient = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)
  const [liveTurn, setLiveTurn] = useState<AgentLiveTurn | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)

  const conversationQuery = useQuery({
    queryKey: ['agent-conversation', conversationId],
    queryFn: async () => {
      if (!conversationId) return null
      return agentConversationsApi.get(conversationId)
    },
    enabled: Boolean(conversationId),
  })

  const messages = useMemo(
    () => mapStoredMessages(conversationQuery.data?.messages ?? []),
    [conversationQuery.data?.messages],
  )

  const invalidateConversationLists = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['agent-conversations'] })
    if (conversationId) {
      await queryClient.invalidateQueries({ queryKey: ['agent-conversation', conversationId] })
    }
  }, [conversationId, queryClient])

  const sendMessage = useCallback(
    async (content: string, attachments?: File[], targetConversationId?: string) => {
      const activeId = targetConversationId ?? conversationId
      if (!activeId) return
      setStreamError(null)
      setLiveTurn(initialLiveTurn())

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      try {
        if (attachments?.length) {
          const data = await agentConversationsApi.uploadTranscriptMessage(
            activeId,
            content,
            attachments[0],
          )
          data.events.forEach((event) => {
            setLiveTurn((current) => (current ? applyStreamEvent(current, event) : current))
          })
          if (!data.text) {
            setLiveTurn((current) =>
              current ? { ...current, text: data.text, status: 'completed' } : current,
            )
          }
        } else {
          await agentConversationsApi.streamMessage(activeId, content, {
            signal: controller.signal,
            onEvent: (event) => {
              setLiveTurn((current) => applyStreamEvent(current ?? initialLiveTurn(), event))
            },
          })
        }
        await invalidateConversationLists()
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          setLiveTurn((current) =>
            current
              ? {
                  ...current,
                  status: 'failed',
                  error: 'The agent run was stopped.',
                }
              : current,
          )
        } else {
          const message = error instanceof Error ? error.message : 'Failed to send message'
          setStreamError(message)
          setLiveTurn((current) =>
            current ? { ...current, status: 'failed', error: message } : current,
          )
        }
      } finally {
        setLiveTurn((current) => {
          if (current && current.status === 'streaming') {
            return { ...current, status: 'completed' }
          }
          return current
        })
        abortRef.current = null
      }
    },
    [conversationId, invalidateConversationLists],
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clearLiveTurn = useCallback(() => {
    setLiveTurn(null)
    setStreamError(null)
  }, [])

  const confirmAction = useMutation({
    mutationFn: async (actionId: string) => {
      if (!conversationId) throw new Error('No active conversation')
      return agentConversationsApi.confirmAction(conversationId, actionId)
    },
    onSuccess: async () => {
      await invalidateConversationLists()
      clearLiveTurn()
    },
  })

  const rejectAction = useMutation({
    mutationFn: async (actionId: string) => {
      if (!conversationId) throw new Error('No active conversation')
      return agentConversationsApi.rejectAction(conversationId, actionId)
    },
    onSuccess: async () => {
      await invalidateConversationLists()
    },
  })

  const activeSteps: AgentStepState[] = liveTurn?.steps ?? []
  const pendingActions: AgentProposedAction[] = liveTurn?.actions ?? []

  const latestBlocks = useMemo(() => {
    const fromLive = liveTurn?.blocks ?? []
    if (fromLive.length) return fromLive
    const lastAssistant = [...messages].reverse().find((item) => item.kind === 'assistant')
    return lastAssistant?.kind === 'assistant' ? lastAssistant.blocks : []
  }, [liveTurn?.blocks, messages])

  const suggestedPrompts = liveTurn?.suggestedPrompts.length
    ? liveTurn.suggestedPrompts
    : extractSuggestedPrompts(latestBlocks)

  return {
    conversation: conversationQuery.data?.conversation,
    messages,
    liveTurn,
    streamError,
    isLoading: conversationQuery.isLoading,
    isStreaming: liveTurn?.status === 'streaming',
    activeSteps,
    pendingActions,
    suggestedPrompts,
    sendMessage,
    stopStreaming,
    clearLiveTurn,
    confirmAction,
    rejectAction,
    refetch: conversationQuery.refetch,
  }
}

export function useAgentConversations() {
  const queryClient = useQueryClient()

  const listQuery = useQuery({
    queryKey: ['agent-conversations'],
    queryFn: () => agentConversationsApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: (title?: string) => agentConversationsApi.create(title),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agent-conversations'] })
    },
  })

  return {
    conversations: listQuery.data?.conversations ?? [],
    isLoading: listQuery.isLoading,
    createConversation: (title?: string) => createMutation.mutateAsync(title),
    isCreating: createMutation.isPending,
    refetch: listQuery.refetch,
  }
}

export type { AgentConversation }
