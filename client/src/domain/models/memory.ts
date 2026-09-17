export type LongTermMemoryCategory = 'decision' | 'profile' | 'knowledge'

export type LongTermMemoryItem = {
  id: string
  category: LongTermMemoryCategory
  key: string
  value: string
  created_at: string
  updated_at: string
}

export type WorkingMemoryItem = LongTermMemoryItem & { scope: 'working' }
export type MemoryEvent = {
  id: string
  scope: 'short_term' | 'working' | 'long_term'
  action:
    | 'saved'
    | 'created'
    | 'updated'
    | 'deleted'
    | 'cleared'
    | 'proposed'
    | 'approved'
    | 'rejected'
    | 'error'
  key?: string | null
  value?: string | null
  candidate_id?: string | null
  message?: string | null
  provider?: string | null
  model?: string | null
  duration_seconds?: number | null
  trace?: ProviderTrace | null
}
export type PendingMemorySuggestion = {
  id: string
  candidate: {
    scope: 'long_term'
    action: 'create' | 'update' | 'delete'
    category: LongTermMemoryCategory
    key: string
    value?: string | null
    confidence: number
    reason: string
  }
  created_at: string
}
import { ProviderTrace } from './chat'
