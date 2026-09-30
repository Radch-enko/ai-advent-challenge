export type EmbeddingSettings = {
  provider: string
  model: string
  source_path: string
  artifact_root: string
  source_file_count: number
  source_bytes: number
}

export type EmbeddingProviderOption = {
  id: string
  display_name: string
  default_model: string
  configured: boolean
  models: string[]
  models_error: string | null
}

export type EmbeddingProviders = { providers: EmbeddingProviderOption[] }

export type IndexingRunStatus = {
  run_id: string | null
  state: 'idle' | 'running' | 'completed' | 'failed'
  stage: string
  processed_files: number
  total_files: number
  error: string | null
  artifact_path: string | null
  started_at: string | null
  completed_at: string | null
}

export type ChunkingSummary = {
  chunk_count: number
  total_chunk_tokens: number
  average_chunk_tokens: number
  max_chunk_tokens: number
  configured_max_tokens: number
}

export type LatestIndex = {
  manifest: {
    run_id: string
    created_at: string
    provider: string
    model: string
    embedding_dimension: number
    text_volume: {
      file_count: number
      bytes: number
      characters: number
      tokens: number
    }
    chunking: Record<string, ChunkingSummary>
  }
  artifact_path: string
  comparison: string
}
