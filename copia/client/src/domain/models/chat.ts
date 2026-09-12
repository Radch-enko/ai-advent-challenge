export type RequestLog = {
  provider: string
  model: string
  status: number
  duration: string
  request: object
  response: object
}

export type TokenUsage = {
  prompt_tokens?: number
  cached_prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
  timestamp: string
  log?: RequestLog
  usage?: TokenUsage | null
  contextWindow?: number | null
  transcriptIndex?: number
}

export type ProviderTrace = {
  status_code: number
  request_body: Record<string, unknown>
  response_body: Record<string, unknown>
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
