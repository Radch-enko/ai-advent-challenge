export type KnowledgeSource = {
  chunk_id: string
  source: string
  title: string
  section: string
  similarity_score?: number | null
  selected_for_context?: boolean | null
}
