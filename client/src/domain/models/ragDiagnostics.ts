import type { KnowledgeSource } from './knowledgeSource'

export type RagDiagnostics = {
  reason: 'below_threshold' | 'citation_validation_failed'
  similarity_threshold: number
  query_fallback_used: boolean
  candidates: { source: KnowledgeSource; text_preview: string }[]
}
