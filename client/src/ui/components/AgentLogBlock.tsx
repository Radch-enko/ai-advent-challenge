import { useEffect, useState } from 'react'
import { getAgentLog } from '../../data/api/copiaApi'
import { AgentLogDetail, AgentLogExchange, TokenUsage } from '../../domain/models/chat'
import { MemoryEvent } from '../../domain/models/memory'

const clockIcon = new URL('../../assets/agent-log/clock.svg', import.meta.url).href
const chevronDownIcon = new URL('../../assets/agent-log/chevron-down.svg', import.meta.url).href
const chevronRightIcon = new URL('../../assets/agent-log/chevron-right.svg', import.meta.url).href
const databaseIcon = new URL('../../assets/agent-log/database.svg', import.meta.url).href
const editIcon = new URL('../../assets/agent-log/edit.svg', import.meta.url).href
const lineIcon = new URL('../../assets/agent-log/line.svg', import.meta.url).href
const providerIndicatorIcon = new URL(
  '../../assets/agent-log/provider-indicator.svg',
  import.meta.url,
).href
const longTermStatusIcon = new URL('../../assets/agent-log/status-long-term.svg', import.meta.url)
  .href
const workingStatusIcon = new URL('../../assets/agent-log/status-working.svg', import.meta.url).href

type Props = {
  sessionId?: string
  agentLogId?: string
  memoryEvents?: MemoryEvent[]
  onOpenLogs?: (exchange: AgentLogExchange) => void
}

export function AgentLogBlock({ sessionId, agentLogId, memoryEvents = [], onOpenLogs }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<AgentLogDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!sessionId || !agentLogId) return
    let cancelled = false
    void getAgentLog(sessionId, agentLogId).then(
      (loadedDetail) => {
        if (cancelled) return
        setDetail(loadedDetail)
        setLoading(false)
      },
      () => {
        if (cancelled) return
        setUnavailable(true)
        setLoading(false)
      },
    )
    return () => {
      cancelled = true
    }
  }, [agentLogId, sessionId, attempt])

  function toggleExpanded() {
    const next = !expanded
    setExpanded(next)
  }

  function openLogs(exchange: AgentLogExchange) {
    setExpanded(true)
    onOpenLogs?.(exchange)
  }

  const duration = detail ? formatDuration(detail.duration_seconds) : undefined
  const title = duration ? `Выполнено за ${duration}` : 'Выполняется...'
  const hasMemorySummaryEvents = memoryEvents.some(
    (event) => event.scope === 'working' || event.scope === 'long_term',
  )

  if (!sessionId || !agentLogId) return null

  return (
    <section className="agent-log-block" aria-label="Agent log">
      <button
        type="button"
        className="agent-log-toggle"
        aria-expanded={expanded}
        onClick={toggleExpanded}
      >
        <span className="agent-log-header-content">
          <span className="agent-log-icon" aria-hidden="true">
            <img src={clockIcon} alt="" />
          </span>
          <span>{title}</span>
        </span>
        <span className="agent-log-chevron" aria-hidden="true">
          <img src={expanded ? chevronDownIcon : chevronRightIcon} alt="" />
        </span>
      </button>
      {expanded && (
        <div className="agent-log-details">
          {loading && <p className="agent-log-status">Загружаем детали…</p>}
          {unavailable && (
            <p className="agent-log-status" role="alert">
              Не удалось загрузить лог.{' '}
              <button
                type="button"
                onClick={() => {
                  setUnavailable(false)
                  setLoading(true)
                  setAttempt((value) => value + 1)
                }}
              >
                Повторить
              </button>
            </p>
          )}
          {detail && (
            <div className="agent-log-details-card">
              {detail.usage && <TokenUsageDetails usage={detail.usage} />}
              <AgentLogDivider />
              <ModelInfo detail={detail} />
              <ProfileOperations operations={detail.operations} />
              <AgentLogDivider />
              <HttpCalls exchanges={detail.exchanges} onOpenLogs={openLogs} />
              {hasMemorySummaryEvents && (
                <>
                  <AgentLogDivider />
                  <MemorySummary events={memoryEvents} />
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function ProfileOperations({ operations }: { operations: AgentLogDetail['operations'] }) {
  const operation = operations.find((item) => item.operation === 'user_profile_load')
  if (!operation) return null
  const status =
    operation.status === 'completed'
      ? 'Loaded'
      : operation.status === 'skipped'
        ? 'Skipped'
        : 'Error'
  return (
    <section className="agent-log-operations" aria-label="Контекст">
      <h3>Контекст</h3>
      <p>
        <strong>User profile</strong> · {status} · {operation.profile_name ?? 'Без профиля'} ·{' '}
        {formatExchangeDuration(operation.duration_seconds)}
      </p>
      {operation.message && <p>{operation.message}</p>}
    </section>
  )
}

function TokenUsageDetails({ usage }: { usage: TokenUsage }) {
  return (
    <section className="agent-log-token-stats" aria-label="Статистика токенов">
      <h3>Статистика токенов</h3>
      <dl>
        <div>
          <dt>Input</dt>
          <dd>{formatTokens(usage.prompt_tokens)}</dd>
        </div>
        <div>
          <dt>Cached</dt>
          <dd>{formatTokens(usage.cached_prompt_tokens)}</dd>
        </div>
        <div>
          <dt>Output</dt>
          <dd>{formatTokens(usage.completion_tokens)}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>{formatTokens(usage.total_tokens)}</dd>
        </div>
      </dl>
    </section>
  )
}

function ModelInfo({ detail }: { detail: AgentLogDetail }) {
  return (
    <div className="agent-log-model-info">
      <div className="agent-log-provider">
        <span className="agent-log-provider-icon" aria-hidden="true">
          <img src={providerIndicatorIcon} alt="" />
        </span>
        <span>Провайдер:</span>
        <strong>{detail.provider ?? '—'}</strong>
        <span className={`agent-log-run-status ${detail.status}`}>
          {formatStatus(detail.status)}
        </span>
      </div>
      <div className="agent-log-model">
        <span>Модель:</span>
        <code>{detail.model ?? '—'}</code>
      </div>
    </div>
  )
}

function HttpCalls({
  exchanges,
  onOpenLogs,
}: {
  exchanges: AgentLogExchange[]
  onOpenLogs: (exchange: AgentLogExchange) => void
}) {
  return (
    <section className="agent-log-http-calls" aria-label="HTTP-вызовы">
      <header>
        <h3>HTTP-вызовы</h3>
        <span>{exchanges.length}</span>
      </header>
      <div className="agent-log-http-list">
        {exchanges.length > 0 ? (
          exchanges.map((exchange) => (
            <article className="agent-log-http-row" key={exchange.id}>
              <span className={`agent-log-method method-${exchange.method.toLowerCase()}`}>
                {exchange.method}
              </span>
              <code className="agent-log-endpoint" title={exchange.operation}>
                {formatEndpoint(exchange.url)}
              </code>
              <span className={`agent-log-http-status ${statusTone(exchange.status_code)}`}>
                {exchange.status_code ?? 'error'}
              </span>
              <span className="agent-log-http-duration">
                {formatExchangeDuration(exchange.duration_seconds)}
              </span>
              <button type="button" onClick={() => onOpenLogs(exchange)}>
                Logs
              </button>
            </article>
          ))
        ) : (
          <p className="agent-log-empty">HTTP-вызовов нет</p>
        )}
      </div>
    </section>
  )
}

function MemorySummary({ events }: { events: MemoryEvent[] }) {
  const workingEvents = events.filter((event) => event.scope === 'working')
  const longTermEvents = events.filter((event) => event.scope === 'long_term')

  return (
    <section className="agent-log-memory" aria-label="Память">
      <h3>Память</h3>
      <div className="agent-log-memory-list">
        {workingEvents.length > 0 && (
          <MemoryCard
            icon={editIcon}
            statusIcon={workingStatusIcon}
            title="Working memory"
            summary={summarizeMemoryEvents(workingEvents, 'working')}
          />
        )}
        {longTermEvents.length > 0 && (
          <MemoryCard
            icon={databaseIcon}
            statusIcon={longTermStatusIcon}
            title="Long-term memory"
            summary={summarizeMemoryEvents(longTermEvents, 'long_term')}
          />
        )}
      </div>
    </section>
  )
}

function MemoryCard({
  icon,
  statusIcon,
  title,
  summary,
}: {
  icon: string
  statusIcon: string
  title: string
  summary: string
}) {
  return (
    <article className="agent-log-memory-card">
      <span className="agent-log-memory-status" aria-hidden="true">
        <img src={statusIcon} alt="" />
      </span>
      <span className="agent-log-memory-icon" aria-hidden="true">
        <img src={icon} alt="" />
      </span>
      <div>
        <h4>{title}</h4>
        <p>{summary}</p>
      </div>
    </article>
  )
}

function AgentLogDivider() {
  return <img className="agent-log-divider" src={lineIcon} alt="" aria-hidden="true" />
}

function summarizeMemoryEvents(events: MemoryEvent[], scope: 'working' | 'long_term') {
  const action = events[events.length - 1]?.action
  const count = events.length
  const key = events.find((event) => event.key)?.key
  const suffix = key ? `: ${key}` : ''

  if (scope === 'working') {
    if (action === 'cleared') return 'Очищено'
    if (action === 'deleted') return `Удалено${suffix}`
    if (action === 'error') {
      const message = events[events.length - 1]?.message?.trim()
      return message && message !== 'Memory candidate requires clarification'
        ? message
        : 'Требуется уточнение'
    }
    return `Обновлено${key ? suffix : `: ${count} ${pluralize(count, 'запись', 'записи', 'записей')}`}`
  }

  if (action === 'approved')
    return `Записано: ${count} ${pluralize(count, 'изменение', 'изменения', 'изменений')}`
  if (action === 'rejected')
    return `Отклонено: ${count} ${pluralize(count, 'предложение', 'предложения', 'предложений')}`
  if (action === 'error') return 'Сохранение не выполнено'
  return `Предложено: ${count} ${pluralize(count, 'новый факт', 'новых факта', 'новых фактов')}`
}

function pluralize(value: number, one: string, few: string, many: string) {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

function formatStatus(status: AgentLogDetail['status']) {
  if (status === 'completed') return 'Успешно'
  if (status === 'running') return 'Выполняется'
  return 'Ошибка'
}

function statusTone(status?: number | null) {
  if (status == null || status < 200 || status >= 400) return 'error'
  return 'success'
}

function formatEndpoint(url: string) {
  try {
    const parsed = new URL(url)
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return url
  }
}

function formatExchangeDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(1)}s`
}

function formatDuration(seconds: number) {
  return `${seconds.toFixed(2)}s`
}

function formatTokens(value?: number) {
  return value == null ? '—' : new Intl.NumberFormat('ru-RU').format(value)
}
