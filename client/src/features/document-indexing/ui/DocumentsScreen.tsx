import { useMemo, useState } from 'react'
import { useDocumentIndexing } from '../application/useDocumentIndexing'
import { EmbeddingSettings } from '../../../domain/models/documentIndexing'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return String(bytes) + ' Б'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ'
  return (bytes / (1024 * 1024)).toFixed(1) + ' МБ'
}

function stageLabel(stage: string): string {
  if (stage.startsWith('chunking:fixed-size')) return 'Разбиение: фиксированный размер'
  if (stage.startsWith('chunking:structure-aware')) return 'Разбиение: по структуре'
  if (stage.startsWith('embedding:fixed-size')) return 'Эмбеддинги: фиксированный размер'
  if (stage.startsWith('embedding:structure-aware')) return 'Эмбеддинги: по структуре'
  if (stage === 'scanning') return 'Чтение каталога'
  if (stage === 'saving') return 'Сохранение локального индекса'
  if (stage === 'queued') return 'Подготовка к запуску'
  return 'Индексация'
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}

export function DocumentsScreen() {
  const indexing = useDocumentIndexing()
  if (!indexing.settings) {
    return (
      <section className="documents-screen" aria-labelledby="documents-title">
        <h1 id="documents-title">Документы</h1>
        {indexing.loading ? <p>Загрузка библиотеки…</p> : null}
        {indexing.error ? <p role="alert">{indexing.error}</p> : null}
        {!indexing.loading && !indexing.error ? (
          <p>Настройки локальной библиотеки недоступны.</p>
        ) : null}
      </section>
    )
  }
  return (
    <DocumentsLibrary
      key={indexing.settings.provider + ':' + indexing.settings.model}
      indexing={indexing}
      settings={indexing.settings}
    />
  )
}

export function DocumentsLibrary({
  indexing,
  settings,
}: {
  indexing: ReturnType<typeof useDocumentIndexing>
  settings: EmbeddingSettings
}) {
  const [providerDraft, setProviderDraft] = useState(settings.provider)
  const [modelDraft, setModelDraft] = useState(settings.model)
  const [copied, setCopied] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [copyError, setCopyError] = useState<string | null>(null)

  const selectedProvider = useMemo(
    () => indexing.providers.find((provider) => provider.id === providerDraft),
    [indexing.providers, providerDraft],
  )
  const isRunning = indexing.run?.state === 'running' || indexing.starting
  const isDirty = settings.provider !== providerDraft || settings.model !== modelDraft
  const sourceReady = settings.source_file_count > 0
  const canIndex =
    sourceReady && selectedProvider?.configured === true && !isRunning && !indexing.loading
  const fixed = indexing.latest?.manifest.chunking['fixed-size']
  const structural = indexing.latest?.manifest.chunking['structure-aware']
  const artifactPath = indexing.latest?.artifact_path

  async function save() {
    setActionError(null)
    try {
      await indexing.saveSettings(providerDraft, modelDraft)
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Не удалось сохранить настройки')
    }
  }

  async function start() {
    setActionError(null)
    try {
      await indexing.start(providerDraft, modelDraft)
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Не удалось запустить индексацию')
    }
  }

  async function copyArtifactPath() {
    if (!indexing.latest) return
    setCopyError(null)
    try {
      await navigator.clipboard.writeText(indexing.latest.artifact_path)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopyError('Не удалось скопировать путь. Выделите и скопируйте его вручную.')
    }
  }

  return (
    <section className="documents-screen" aria-labelledby="documents-title">
      <header className="documents-heading">
        <div>
          <h1 id="documents-title">Документы</h1>
          <p>Локальная библиотека для подготовки индекса. Агенты пока его не используют.</p>
        </div>
        <button
          type="button"
          className="documents-secondary-button"
          disabled={indexing.loading}
          onClick={() => void indexing.refresh()}
        >
          Обновить каталог
        </button>
      </header>

      <article className="documents-card documents-source-card">
        <div className="documents-source-heading">
          <div>
            <span className="documents-eyebrow">Папка источников</span>
            <code title={settings.source_path}>{settings.source_path}</code>
          </div>
          <span className={'documents-status-pill ' + (sourceReady ? 'ready' : 'empty')}>
            {sourceReady ? 'Готово' : 'Пусто'}
          </span>
        </div>
        <div className="documents-source-stats">
          <div>
            <span>Текстовых файлов</span>
            <strong>{settings.source_file_count}</strong>
          </div>
          <div>
            <span>Размер текста</span>
            <strong>{formatBytes(settings.source_bytes)}</strong>
          </div>
        </div>
        <p className="documents-supported-formats">
          Поддерживаются TXT и Markdown. Файлы читаются рекурсивно.
        </p>
      </article>

      <article className="documents-card documents-embedding-card">
        <div className="documents-card-heading">
          <div>
            <h2>Настройки эмбеддингов</h2>
            <p>Настройки сохраняются локально и применяются к следующему запуску.</p>
          </div>
          <span className="documents-provider-mark" aria-hidden="true">
            ✦
          </span>
        </div>
        <div className="documents-settings-grid">
          <label>
            <span>Провайдер</span>
            <select
              value={providerDraft}
              disabled={indexing.providersLoading || isRunning}
              onChange={(event) => {
                const provider = indexing.providers.find((item) => item.id === event.target.value)
                setProviderDraft(event.target.value)
                if (provider && !provider.models.includes(modelDraft)) {
                  setModelDraft(provider.default_model)
                }
              }}
            >
              {indexing.providers.length === 0 ? (
                <option value={providerDraft}>
                  {indexing.providersLoading ? 'Загрузка провайдеров…' : providerDraft}
                </option>
              ) : (
                indexing.providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.display_name}
                  </option>
                ))
              )}
            </select>
          </label>
          <label>
            <span>Модель</span>
            <input
              list="embedding-model-options"
              value={modelDraft}
              onChange={(event) => setModelDraft(event.target.value)}
              placeholder="text-embedding-3-small"
            />
            <datalist id="embedding-model-options">
              {selectedProvider?.models.map((model) => (
                <option key={model} value={model} />
              ))}
              {selectedProvider?.default_model ? (
                <option value={selectedProvider.default_model} />
              ) : null}
            </datalist>
          </label>
        </div>
        <div className="documents-settings-footer">
          <p>
            Текст каждого чанка отправляется в {selectedProvider?.display_name ?? providerDraft} для
            расчёта эмбеддинга.
            {selectedProvider?.id === 'openai' ? ' Это может повлечь расходы OpenAI.' : ''}
          </p>
          <button
            type="button"
            className="documents-secondary-button"
            disabled={!isDirty || indexing.saving || isRunning || !modelDraft.trim()}
            onClick={() => void save()}
          >
            {indexing.saving ? 'Сохранение…' : 'Сохранить настройки'}
          </button>
        </div>
        {selectedProvider && !selectedProvider.configured ? (
          <p className="documents-inline-note">
            Провайдер не настроен. Добавьте его ключ в переменные окружения backend.
          </p>
        ) : null}
        {selectedProvider?.models_error ? (
          <p className="documents-inline-note">
            {selectedProvider.models_error}. ID модели можно ввести вручную.
          </p>
        ) : null}
        {indexing.providersError ? (
          <p className="documents-inline-note">
            {indexing.providersError}. Можно указать ID модели вручную.
          </p>
        ) : null}
      </article>

      <div className="documents-actions">
        <button
          type="button"
          className="documents-primary-button"
          disabled={!canIndex}
          onClick={() => void start()}
        >
          {indexing.starting ? 'Запуск…' : indexing.latest ? 'Переиндексировать' : 'Индексировать'}
        </button>
        {!sourceReady ? (
          <span>Положите статьи в папку источников, затем обновите каталог.</span>
        ) : null}
        {isDirty ? <span>Индексация сохранит и использует выбранные настройки.</span> : null}
      </div>

      {actionError || indexing.error ? (
        <p className="documents-error" role="alert">
          {actionError ?? indexing.error}
        </p>
      ) : null}
      {indexing.run?.state === 'running' ? (
        <article className="documents-card documents-progress" aria-live="polite">
          <div className="documents-progress-heading">
            <div>
              <h2>Индексация в процессе</h2>
              <p>{stageLabel(indexing.run.stage)}</p>
            </div>
            <strong>
              {indexing.run.processed_files} / {indexing.run.total_files} файлов
            </strong>
          </div>
          <progress
            max={Math.max(indexing.run.total_files, 1)}
            value={indexing.run.processed_files}
            aria-label="Обработано файлов"
          />
          <p>Строятся обе стратегии разбиения и записываются локальные артефакты.</p>
        </article>
      ) : null}
      {indexing.run?.state === 'failed' ? (
        <p className="documents-error" role="alert">
          Последняя попытка не завершилась: {indexing.run.error ?? 'ошибка индексации'}
        </p>
      ) : null}

      <section className="documents-comparison" aria-labelledby="chunking-title">
        <div className="documents-section-heading">
          <div>
            <h2 id="chunking-title">Сравнение стратегий разбиения</h2>
            <p>Оба результата сохраняются отдельно в JSONL вместе с метаданными и векторами.</p>
          </div>
          {indexing.latest ? (
            <span>Вектор: {indexing.latest.manifest.embedding_dimension} измерений</span>
          ) : null}
        </div>
        <div className="documents-comparison-grid">
          <ChunkingCard
            title="Фиксированный размер"
            detail="До 512 токенов · перекрытие 64"
            summary={fixed}
          />
          <ChunkingCard
            title="С учётом структуры"
            detail="Заголовки и абзацы · до 680 токенов"
            summary={structural}
          />
        </div>
        {indexing.latest ? (
          <div className="documents-latest">
            <div>
              <span>
                Последний успешный запуск · {formatDate(indexing.latest.manifest.created_at)}
              </span>
              <code title={artifactPath}>{artifactPath}</code>
              <small>
                {indexing.latest.manifest.text_volume.file_count} файлов ·{' '}
                {formatBytes(indexing.latest.manifest.text_volume.bytes)} ·{' '}
                {indexing.latest.manifest.text_volume.tokens.toLocaleString('ru-RU')} токенов текста
              </small>
            </div>
            <button
              type="button"
              className="documents-secondary-button"
              onClick={() => void copyArtifactPath()}
            >
              {copied ? 'Скопировано' : 'Копировать путь'}
            </button>
          </div>
        ) : (
          <div className="documents-latest documents-latest-empty">
            <span>Успешных запусков пока нет</span>
            <code>{settings.artifact_root}</code>
          </div>
        )}
        {copyError ? (
          <p role="alert" className="documents-inline-note">
            {copyError}
          </p>
        ) : null}
      </section>
    </section>
  )
}

function ChunkingCard({
  title,
  detail,
  summary,
}: {
  title: string
  detail: string
  summary?: {
    chunk_count: number
    average_chunk_tokens: number
    max_chunk_tokens: number
    configured_max_tokens: number
  }
}) {
  return (
    <article className="documents-card documents-chunk-card">
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
      {summary ? (
        <dl>
          <div>
            <dt>Чанков</dt>
            <dd>{summary.chunk_count.toLocaleString('ru-RU')}</dd>
          </div>
          <div>
            <dt>Средний размер</dt>
            <dd>{summary.average_chunk_tokens} токенов</dd>
          </div>
          <div>
            <dt>Максимум</dt>
            <dd>
              {summary.max_chunk_tokens} / {summary.configured_max_tokens}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="documents-no-comparison">Запустите индексацию, чтобы увидеть сравнение.</p>
      )}
    </article>
  )
}
