import {
  EmbeddingProviders,
  EmbeddingSettings,
  IndexingRunStatus,
  LatestIndex,
} from '../../domain/models/documentIndexing'
import { request } from './request'

export function getEmbeddingSettings(): Promise<EmbeddingSettings> {
  return request('/document-indexing/settings')
}

export function saveEmbeddingSettings(
  settings: Pick<EmbeddingSettings, 'provider' | 'model'>,
): Promise<EmbeddingSettings> {
  return request('/document-indexing/settings', {
    method: 'PUT',
    body: JSON.stringify(settings),
  })
}

export function getEmbeddingProviders(): Promise<EmbeddingProviders> {
  return request('/document-indexing/embedding-providers')
}

export function startDocumentIndexing(): Promise<IndexingRunStatus> {
  return request('/document-indexing/runs', { method: 'POST' })
}

export function getCurrentDocumentIndexingRun(): Promise<IndexingRunStatus> {
  return request('/document-indexing/runs/current')
}

export function getDocumentIndexingRun(runId: string): Promise<IndexingRunStatus> {
  return request('/document-indexing/runs/' + encodeURIComponent(runId))
}

export function getLatestDocumentIndex(): Promise<LatestIndex | null> {
  return request('/document-indexing/latest')
}
