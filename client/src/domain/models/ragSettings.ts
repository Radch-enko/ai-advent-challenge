export type RagSettings = {
  top_k_before: number
  similarity_threshold: number
  top_k_after: number
  query_rewrite_enabled: boolean
  reranker_enabled: boolean
}

export const defaultRagSettings: RagSettings = {
  top_k_before: 10,
  similarity_threshold: 0.35,
  top_k_after: 3,
  query_rewrite_enabled: false,
  reranker_enabled: false,
}
