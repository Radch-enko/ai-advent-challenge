import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { useDocumentIndexing } from '../src/features/document-indexing/application/useDocumentIndexing'
import { DocumentsLibrary } from '../src/features/document-indexing/ui/DocumentsScreen'
import {
  EmbeddingSettings,
  IndexingRunStatus,
  LatestIndex,
} from '../src/domain/models/documentIndexing'

const settings: EmbeddingSettings = {
  provider: 'openai',
  model: 'text-embedding-3-small',
  source_path: '/tmp/copia-documents',
  artifact_root: '/tmp/copia-data/document-index',
  source_file_count: 3,
  source_bytes: 4096,
}

const provider = {
  id: 'openai',
  display_name: 'OpenAI',
  default_model: 'text-embedding-3-small',
  configured: true,
  models: ['text-embedding-3-small', 'text-embedding-3-large'],
  models_error: null,
}

function createIndexingState(
  overrides: Partial<ReturnType<typeof useDocumentIndexing>> = {},
): ReturnType<typeof useDocumentIndexing> {
  return {
    settings,
    providers: [provider],
    latest: null,
    run: null,
    loading: false,
    providersLoading: false,
    providersError: null,
    saving: false,
    starting: false,
    error: null,
    refresh: async () => undefined,
    saveSettings: async () => settings,
    start: async () => ({
      run_id: 'run-started',
      state: 'running',
      stage: 'queued',
      processed_files: 0,
      total_files: 0,
      error: null,
      artifact_path: null,
      started_at: null,
      completed_at: null,
    }),
    ...overrides,
  }
}

function renderLibrary(
  indexing: ReturnType<typeof useDocumentIndexing>,
  currentSettings: EmbeddingSettings = settings,
): string {
  return renderToStaticMarkup(
    createElement(DocumentsLibrary, { indexing, settings: currentSettings }),
  )
}

const latestIndex: LatestIndex = {
  manifest: {
    run_id: 'run-123',
    created_at: '2026-09-30T10:00:00+00:00',
    provider: 'openai',
    model: 'text-embedding-3-small',
    embedding_dimension: 1536,
    text_volume: { file_count: 3, bytes: 4096, characters: 3900, tokens: 1200 },
    chunking: {
      'structure-aware': {
        chunk_count: 6,
        total_chunk_tokens: 3300,
        average_chunk_tokens: 550,
        max_chunk_tokens: 680,
        configured_max_tokens: 680,
      },
    },
    sources: [
      {
        source: 'CopiaKnowledgeBase/goals/year.md',
        title: 'year',
        size_bytes: 1200,
        characters: 1100,
      },
      {
        source: 'CopiaKnowledgeBase/notes.md',
        title: 'notes',
        size_bytes: 1800,
        characters: 1700,
      },
      {
        source: 'overview.md',
        title: 'overview',
        size_bytes: 1096,
        characters: 1100,
      },
    ],
  },
  artifact_path: '/tmp/copia-data/document-index/runs/run-123',
  comparison: '# Chunking comparison',
}

describe('DocumentsLibrary', () => {
  it('shows the source folder, embedding controls, empty index summary and cost notice', () => {
    const html = renderLibrary(createIndexingState())

    expect(html).toContain('/tmp/copia-documents')
    expect(html).toContain('text-embedding-3-small')
    expect(html).toContain('Текст каждого чанка отправляется в OpenAI')
    expect(html).toContain('Успешных запусков пока нет')
    expect(html).toContain('Запустите индексацию, чтобы увидеть статистику.')
    expect(html).toContain('Markdown-файлов')
  })

  it('shows stage, processed file progress and previous successful result during a run', () => {
    const running: IndexingRunStatus = {
      run_id: 'run-456',
      state: 'running',
      stage: 'embedding:structure-aware',
      processed_files: 2,
      total_files: 3,
      error: null,
      artifact_path: null,
      started_at: '2026-09-30T10:01:00+00:00',
      completed_at: null,
    }
    const html = renderLibrary(createIndexingState({ latest: latestIndex, run: running }))

    expect(html).toContain('Индексация в процессе')
    expect(html).toContain('Эмбеддинги: по структуре')
    expect(html).toContain('2 / 3 файлов')
    expect(html).toContain('/tmp/copia-data/document-index/runs/run-123')
    expect(html).toContain('Копировать путь')
  })

  it('shows one structural summary and indexed source tree after a failed run', () => {
    const failed: IndexingRunStatus = {
      run_id: 'run-789',
      state: 'failed',
      stage: 'failed',
      processed_files: 1,
      total_files: 3,
      error: 'Embedding provider request failed',
      artifact_path: '/tmp/copia-data/document-index/runs/run-789',
      started_at: '2026-09-30T10:02:00+00:00',
      completed_at: '2026-09-30T10:02:10+00:00',
    }
    const html = renderLibrary(createIndexingState({ latest: latestIndex, run: failed }))

    expect(html).toContain('Последняя попытка не завершилась')
    expect(html).toContain('Embedding provider request failed')
    expect(html).not.toContain('Фиксированный размер')
    expect(html).toContain('Средний размер')
    expect(html).toContain('Структура Markdown')
    expect(html).toContain('550 токенов')
    expect(html).toContain('Файлы последней успешной индексации · 3')
    expect(html).toContain('CopiaKnowledgeBase')
    expect(html).toContain('year.md')
    expect(html).toContain('overview.md')
    expect(html).toContain('/tmp/copia-data/document-index/runs/run-123')
  })
})
