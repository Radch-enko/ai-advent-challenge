import { useState } from 'react'
import { AgentLogBody, AgentLogExchange } from '../../domain/models/chat'

type Props = {
  log: AgentLogExchange
  logs?: AgentLogExchange[]
  tab: 'request' | 'response'
  onTab: (tab: 'request' | 'response') => void
  onClose: () => void
}

export function RequestLogs({ log, logs = [], tab, onTab, onClose }: Props) {
  const [selectedId, setSelectedId] = useState(log.id)
  const selectedLog = logs.find((item) => item.id === selectedId) ?? log
  const isRequest = tab === 'request'
  const body = isRequest ? selectedLog.request_body : selectedLog.response_body
  const headers = isRequest ? selectedLog.request_headers : selectedLog.response_headers

  return (
    <aside className="logs-panel" aria-label="HTTP logs">
      <header>
        <div>
          <b>HTTP Logs</b>
          <span>{logs.length > 1 ? `${logs.length} HTTP calls` : selectedLog.operation}</span>
        </div>
        <button type="button" aria-label="Закрыть логи" onClick={onClose}>
          ×
        </button>
      </header>
      {logs.length > 1 && (
        <div className="logs-call-list" aria-label="HTTP calls">
          {logs.map((item) => (
            <button
              type="button"
              className={item.id === selectedLog.id ? 'active' : ''}
              key={item.id}
              onClick={() => setSelectedId(item.id)}
            >
              <span>{item.operation}</span>
              <b>{item.status_code ?? '…'}</b>
            </button>
          ))}
        </div>
      )}
      <div className="log-meta">
        <span>
          Provider <b>{selectedLog.provider ?? '—'}</b>
        </span>
        <span>
          Model <b>{selectedLog.model ?? '—'}</b>
        </span>
        <span className={statusTone(selectedLog.status_code)}>
          Status <b>{selectedLog.status_code ?? 'error'}</b>
        </span>
        <span>
          Duration <b>{formatExchangeDuration(selectedLog.duration_seconds)}</b>
        </span>
      </div>
      <div className="log-endpoint">
        <code>
          {selectedLog.method} {selectedLog.url}
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
        <b>{isRequest ? 'Headers' : `Headers · ${selectedLog.status_code ?? 'No response'}`}</b>
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
