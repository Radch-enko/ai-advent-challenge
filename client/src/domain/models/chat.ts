export type AgentLogBody = {
  content: string
  encoding: 'utf-8' | 'base64'
  size_bytes: number
  truncated: boolean
}

export type AgentLogExchange = {
  id: string
  agent_turn_id: string
  operation: string
  provider?: string | null
  model?: string | null
  method: string
  url: string
  request_headers: Record<string, string>
  request_body?: AgentLogBody | null
  status_code?: number | null
  response_headers: Record<string, string>
  response_body?: AgentLogBody | null
  duration_seconds: number
  error?: string | null
  created_at: string
}

export type AgentLogDetail = {
  agent_log_id: string
  agent_turn_id: string
  session_id: string
  status: 'running' | 'completed' | 'failed'
  provider?: string | null
  model?: string | null
  usage?: TokenUsage | null
  started_at: string
  completed_at?: string | null
  duration_seconds: number
  error?: string | null
  operations: AgentLogOperation[]
  exchanges: AgentLogExchange[]
}

export type AgentLogOperation = {
  id: string
  agent_turn_id: string
  session_id: string
  operation: 'user_profile_load'
  status: 'completed' | 'failed' | 'skipped'
  profile_id?: string | null
  profile_name?: string | null
  preference_count: number
  applied: boolean
  duration_seconds: number
  error_code?: string | null
  message?: string | null
  created_at: string
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
  agentLogId?: string
  usage?: TokenUsage | null
  contextWindow?: number | null
  transcriptIndex?: number
  taskId?: string
  taskStepId?: string
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
