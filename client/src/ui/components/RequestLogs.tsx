import { AgentLogBody, AgentLogExchange } from '../../domain/models/chat'

type Props = {
  log: AgentLogExchange
  tab: 'request' | 'response'
  onTab: (tab: 'request' | 'response') => void
  onClose: () => void
}

export function RequestLogs({ log, tab, onTab, onClose }: Props) {
  const isRequest = tab === 'request'
  const body = isRequest ? log.request_body : log.response_body
  const headers = isRequest ? log.request_headers : log.response_headers

  return (
    <aside className="logs-panel" aria-label="HTTP logs">
      <header>
        <div>
          <b>HTTP Logs</b>
          <span>{log.operation}</span>
        </div>
        <button type="button" aria-label="Закрыть логи" onClick={onClose}>
          ×
        </button>
      </header>
      <div className="log-meta">
        <span>
          Provider <b>{log.provider ?? '—'}</b>
        </span>
        <span>
          Model <b>{log.model ?? '—'}</b>
        </span>
        <span className={statusTone(log.status_code)}>
          Status <b>{log.status_code ?? 'error'}</b>
        </span>
        <span>
          Duration <b>{formatExchangeDuration(log.duration_seconds)}</b>
        </span>
      </div>
      <div className="log-endpoint">
        <code>
          {log.method} {log.url}
        </code>
      </div>
      <div className="log-tabs" role="tablist" aria-label="HTTP log payload">
        <button
          type="button"
          role="tab"
          aria-selected={isRequest}
          className={isRequest ? 'active' : ''}
          onClick={() => onTab('request')}
        >
          Request
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!isRequest}
          className={!isRequest ? 'active' : ''}
          onClick={() => onTab('response')}
        >
          Response
        </button>
      </div>
      <div className="log-payload-meta">
        <b>{isRequest ? 'Headers' : `Headers · ${log.status_code ?? 'No response'}`}</b>
        <pre>{JSON.stringify(headers, null, 2)}</pre>
      </div>
      <pre className="log-payload-body">{formatBody(body)}</pre>
    </aside>
  )
}

function statusTone(status?: number | null) {
  return status != null && status >= 200 && status < 400 ? 'success' : 'error'
}

function formatExchangeDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(1)}s`
}

function formatBody(body: AgentLogBody | null | undefined) {
  if (!body) return 'No body'
  if (body.encoding === 'base64')
    return `[base64${body.truncated ? ', truncated' : ''}]\n${body.content}`
  try {
    return JSON.stringify(JSON.parse(body.content), null, 2)
  } catch {
    return `${body.content}${body.truncated ? '\n… [truncated]' : ''}`
  }
}
