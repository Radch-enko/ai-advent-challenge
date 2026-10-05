import { AgentConfig } from './agent'
import { FactsUpdateEvent, ProviderTrace, SummarizationEvent, TokenUsage } from './chat'
import { Provider } from './provider'
import { TaskState } from './task'
import { MemoryEvent, PendingMemorySuggestion, WorkingMemoryItem } from './memory'
import { KnowledgeSource } from './knowledgeSource'
import { RagSettings } from './ragSettings'

type ChatResponseData = {
  content: string
  provider: Provider
  model: string
  usage?: TokenUsage | null
  context_window?: number | null
  trace?: ProviderTrace | null
}

type SessionChatResponseData = Omit<ChatResponseData, 'trace'> & { trace?: null }

export type ChatResponse = {
  response: ChatResponseData
  summarization_events: SummarizationEvent[]
  facts_events: FactsUpdateEvent[]
  facts: Record<string, string>
  memory_events: MemoryEvent[]
  pending_memory: PendingMemorySuggestion[]
  working_memory: WorkingMemoryItem[]
}

export type SessionChatResponse = Omit<ChatResponse, 'response'> & {
  response: SessionChatResponseData
  duration_seconds: number
  sources: KnowledgeSource[]
  rag_enabled: boolean
  rewritten_query: string | null
}

export type StoredMessage = {
  role: 'user' | 'assistant'
  content: string
  created_at?: string | null
  usage?: TokenUsage | null
  context_window?: number | null
  provider?: Provider | null
  model?: string | null
  duration_seconds?: number | null
  execution_status?: 'completed' | 'failed' | null
  execution_error?: string | null
  task_id?: string | null
  task_step_id?: string | null
  sources?: KnowledgeSource[]
  rag_enabled?: boolean | null
  rewritten_query?: string | null
}

export type ChatSession = {
  id: string
  title: string | null
  profile_name: string | null
  user_profile_id: string | null
  long_term_memory_enabled: boolean
  task_mode_enabled: boolean
  rag_enabled: boolean
  rag_settings: RagSettings
  task: TaskState | null
  tasks: TaskState[]
  config: AgentConfig
  messages: StoredMessage[]
  context: {
    summary: string
    summarized_message_count: number
    events: SummarizationEvent[]
    facts_events: FactsUpdateEvent[]
  }
  created_at: string
  updated_at: string
}

export type ChatSessionSummary = Pick<ChatSession, 'id' | 'title' | 'profile_name' | 'updated_at'>
