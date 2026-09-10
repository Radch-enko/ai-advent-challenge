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
}
