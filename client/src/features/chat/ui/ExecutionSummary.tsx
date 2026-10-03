import { ChatMessage } from '../../../domain/models/chat'
import type { MemoryEvent } from '../../../domain/models/memory'
import type { KnowledgeSource } from '../../../domain/models/knowledgeSource'

type Props = Pick<
  ChatMessage,
  'provider' | 'model' | 'durationSeconds' | 'executionStatus' | 'executionError' | 'usage'
> & { memoryEvents?: MemoryEvent[]; sources?: KnowledgeSource[] }

export function ExecutionSummary({
  provider,
  model,
  durationSeconds,
  executionStatus,
  executionError,
  usage,
  memoryEvents,
  sources,
}: Props) {
  if (
    !provider &&
    !model &&
    durationSeconds == null &&
    !usage &&
    !executionError &&
    !executionStatus &&
    !memoryEvents?.length &&
    !sources?.length
  )
    return null
  const summaryLabel =
    durationSeconds == null
      ? 'Сведения о выполнении'
      : `${executionStatus === 'failed' ? 'Завершилось с ошибкой' : 'Выполнено'} за ${formatDuration(durationSeconds)}`

  return (
    <details className="execution-summary">
      <summary>
        <span className="execution-summary-clock" aria-hidden="true" />
        {summaryLabel}
      </summary>
      <div className="execution-summary-details" aria-label="Сводка выполнения">
        {usage && (
          <section className="execution-summary-tokens">
            <h3>Статистика токенов</h3>
            <dl className="execution-summary-token-grid">
              <TokenStat label="Input" value={usage.prompt_tokens} />
              <TokenStat label="Cached" value={usage.cached_prompt_tokens} />
              <TokenStat label="Output" value={usage.completion_tokens} />
              <TokenStat label="Total" value={usage.total_tokens} />
            </dl>
          </section>
        )}
        {sources && sources.length > 0 && (
          <section className="execution-summary-sources">
            <h3>Чанки в контексте LLM</h3>
            <ul>
              {sources.map((source, index) => (
                <li key={`${source.chunk_id}-${index}`}>
                  <code>{source.chunk_id}</code>
                  <span>
                    {' '}
                    · {source.title} · {source.section || source.source}
                  </span>
                  {source.similarity_score != null && (
                    <span> · similarity {source.similarity_score.toFixed(3)}</span>
                  )}
                  {source.quote && <q>{source.quote}</q>}
                </li>
              ))}
            </ul>
          </section>
        )}
        {(provider || model) && (
          <div className="execution-summary-model-row">
            <span className="execution-summary-provider">
              <span aria-hidden="true" />
              Провайдер: <strong>{provider ?? '—'}</strong>
            </span>
            <span className="execution-summary-model">
              Модель: <code>{model ?? '—'}</code>
            </span>
          </div>
        )}
        {executionStatus && (
          <p className={`execution-summary-status ${executionStatus}`}>
            Статус запроса: {executionStatus === 'failed' ? 'Ошибка' : 'Выполнено'}
          </p>
        )}
        {executionError && <p role="alert">{executionError}</p>}
        {memoryEvents && memoryEvents.length > 0 && <MemoryEvents events={memoryEvents} />}
      </div>
    </details>
  )
}

function TokenStat({ label, value }: { label: string; value?: number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value == null ? '—' : value.toLocaleString('en-US')}</dd>
    </div>
  )
}

function MemoryEvents({ events }: { events: MemoryEvent[] }) {
  return (
    <section className="execution-summary-memory">
      <h3>Память</h3>
      <div>
        {events.map((event) => (
          <article className={`execution-summary-memory-event ${event.scope}`} key={event.id}>
            <span className="execution-summary-memory-icon" aria-hidden="true">
              {event.scope === 'long_term' ? '▤' : '↗'}
            </span>
            <span>
              <strong>{memoryScopeLabel(event.scope)}</strong>
              <span>{memoryEventDescription(event)}</span>
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}

function memoryScopeLabel(scope: MemoryEvent['scope']) {
  if (scope === 'working') return 'Working Memory'
  if (scope === 'long_term') return 'Long-term Memory'
  return 'Краткосрочная память'
}

function memoryEventDescription(event: MemoryEvent) {
  if (event.message) return event.message
  const action =
    event.action === 'saved' || event.action === 'created' || event.action === 'approved'
      ? 'Записано'
      : event.action === 'updated'
        ? 'Обновлено'
        : event.action === 'deleted' || event.action === 'cleared' || event.action === 'rejected'
          ? 'Удалено'
          : event.action === 'proposed'
            ? 'Предложено'
            : 'Ошибка записи'
  return [action, event.key, event.value].filter(Boolean).join(': ')
}

function formatDuration(seconds: number) {
  return seconds < 1 ? `${Math.round(seconds * 1000)} мс` : `${seconds.toFixed(2)} с`
}
