import type { MemoryEvent } from './memory'
import type { KnowledgeSource } from './knowledgeSource'

export type TokenUsage = {
  prompt_tokens?: number
  cached_prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export type ProviderTrace = {
  status_code: number
  request_body: Record<string, unknown>
  response_body: Record<string, unknown>
}

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
  timestamp: string
  usage?: TokenUsage | null
  provider?: string | null
  model?: string | null
  durationSeconds?: number | null
  executionStatus?: 'completed' | 'failed'
  executionError?: string | null
  memoryEvents?: MemoryEvent[]
  contextWindow?: number | null
  transcriptIndex?: number
  taskId?: string
  taskStepId?: string
  sources?: KnowledgeSource[]
}

export type SummarizationEvent = {
  id: string
  status: 'completed' | 'failed'
  after_message_index: number
  start_message_index: number
  message_count: number
  provider: string
  model: string
  duration_seconds: number
  usage?: TokenUsage | null
  trace?: ProviderTrace | null
  error?: string | null
  created_at: string
  updated_at: string
}

export type FactsUpdateEvent = {
  id: string
  status: 'completed' | 'failed'
  after_message_index: number
  updates: Record<string, string>
  deletions: string[]
  provider: string
  model: string
  duration_seconds: number
  usage?: TokenUsage | null
  trace?: ProviderTrace | null
  error?: string | null
  created_at: string
  updated_at: string
}
