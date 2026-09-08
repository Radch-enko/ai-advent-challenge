export type RequestLog = {
  provider: string
  model: string
  status: number
  duration: string
  request: object
  response: object
}

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
  timestamp: string
  log?: RequestLog
}
