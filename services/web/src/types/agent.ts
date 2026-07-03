export type AgentConversation = {
  id: string
  userId: string
  title?: string | null
  status?: string
  entities?: Record<string, unknown>
  lastMessagePreview?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export type AgentStructuredBlock = {
  type: string
  data: Record<string, unknown>
}

export type AgentMessage = {
  id: string
  conversationId: string
  userId?: string
  role: 'user' | 'assistant' | 'system'
  content: string
  structuredBlocks?: AgentStructuredBlock[]
  attachments?: Array<Record<string, unknown>>
  runId?: string | null
  createdAt?: string | null
}

export type AgentProposedAction = {
  id: string
  actionType?: string
  action_type?: string
  label: string
  description?: string | null
  payload?: Record<string, unknown>
  status?: string
}

export type AgentStreamEvent = {
  type: string
  label?: string
  text?: string
  block?: AgentStructuredBlock
  action?: AgentProposedAction
  runId?: string
  messageId?: string
  error?: string
}

export type AgentStepState = {
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
}

export type AgentLiveTurn = {
  runId?: string
  text: string
  blocks: AgentStructuredBlock[]
  actions: AgentProposedAction[]
  steps: AgentStepState[]
  suggestedPrompts: string[]
  warnings: string[]
  status: 'streaming' | 'completed' | 'failed'
  error?: string
}

export type AgentChatMessage =
  | {
      kind: 'user'
      id: string
      content: string
      createdAt?: string | null
      attachments?: Array<Record<string, unknown>>
    }
  | {
      kind: 'assistant'
      id: string
      content: string
      blocks: AgentStructuredBlock[]
      actions: AgentProposedAction[]
      suggestedPrompts?: string[]
      createdAt?: string | null
      runId?: string | null
    }
