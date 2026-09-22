import { FormEvent, useState } from 'react'
import { discoverMcpTools } from '../../data/api/copiaApi'
import { McpDiscoveryResult } from '../../domain/models/mcp'

type McpConnectionState = 'idle' | 'connecting' | 'connected' | 'empty' | 'error'

const stateCopy: Record<McpConnectionState, string> = {
  idle: 'Не подключено',
  connecting: 'Подключение',
  connected: 'Подключено',
  empty: 'Подключено',
  error: 'Ошибка подключения',
}

function isPublicHttpsEndpoint(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      url.protocol === 'https:' && url.username === '' && url.password === '' && url.hash === ''
    )
  } catch {
    return false
  }
}

export function McpSettingsScreen() {
  const [endpoint, setEndpoint] = useState('')
  const [headerName, setHeaderName] = useState('')
  const [headerValue, setHeaderValue] = useState('')
  const [connectionState, setConnectionState] = useState<McpConnectionState>('idle')
  const [result, setResult] = useState<McpDiscoveryResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    const normalizedEndpoint = endpoint.trim()
    const normalizedHeaderName = headerName.trim()
    const normalizedHeaderValue = headerValue.trim()
    if (!isPublicHttpsEndpoint(normalizedEndpoint)) {
      setConnectionState('error')
      setResult(null)
      setError('Введите корректный публичный HTTPS endpoint без userinfo и fragment.')
      return
    }
    if ((normalizedHeaderName === '') !== (normalizedHeaderValue === '')) {
      setConnectionState('error')
      setResult(null)
      setError('Укажите одновременно Header name и Header value или оставьте оба поля пустыми.')
      return
    }

    setConnectionState('connecting')
    setResult(null)
    setError(null)
    try {
      const discovery = await discoverMcpTools(
        normalizedEndpoint,
        normalizedHeaderName || undefined,
        normalizedHeaderValue || undefined,
      )
      setResult(discovery)
      setConnectionState(discovery.tools.length > 0 ? 'connected' : 'empty')
    } catch (requestError) {
      setConnectionState('error')
      setError(
        requestError instanceof Error ? requestError.message : 'Не удалось подключиться к MCP.',
      )
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void connect()
  }

  function disconnect() {
    setEndpoint('')
    setHeaderName('')
    setHeaderValue('')
    setConnectionState('idle')
    setResult(null)
    setError(null)
  }

  const isConnecting = connectionState === 'connecting'
  const hasConnection =
    result !== null && (connectionState === 'connected' || connectionState === 'empty')

  return (
    <section className="mcp-settings-screen" aria-labelledby="mcp-settings-title">
      <header className="mcp-settings-header">
        <div>
          <p className="mcp-kicker">Настройки системы</p>
          <h1 id="mcp-settings-title">MCP connections</h1>
          <p>Подключите публичный MCP server и просмотрите доступные инструменты.</p>
        </div>
        <div className="mcp-header-status">
          <span className="mcp-active-status">
            <i aria-hidden="true" /> Интеграция активна
          </span>
          <span className="mcp-discovery-badge">Discovery only</span>
        </div>
      </header>

      <div className="mcp-settings-content">
        <article className="mcp-security-notice">
          <div className="mcp-security-icon" aria-hidden="true">
            ✓
          </div>
          <div>
            <strong>Только чтение</strong>
            <span className="mcp-security-required">HTTPS REQUIRED</span>
            <p>
              Мы выполняем только initialize и tools/list. Выполнение tools/call и передача tools в
              LLM отключены. Дополнительный header используется только для discovery и не
              сохраняется.
            </p>
          </div>
        </article>

        <article className="mcp-connection-card">
          <div className="mcp-card-heading">
            <div>
              <h2>Подключение к MCP</h2>
              <p>Укажите Streamable HTTP endpoint сервера.</p>
            </div>
            <span className={`mcp-state-pill mcp-state-${connectionState}`}>
              <i aria-hidden="true" /> {stateCopy[connectionState]}
            </span>
          </div>

          <form onSubmit={handleSubmit}>
            <label htmlFor="mcp-endpoint">Server endpoint</label>
            <div className="mcp-endpoint-row">
              <input
                id="mcp-endpoint"
                type="url"
                value={endpoint}
                onChange={(event) => setEndpoint(event.target.value)}
                placeholder="https://example.com/mcp"
                disabled={isConnecting}
                autoComplete="off"
                spellCheck={false}
              />
              <button type="submit" disabled={isConnecting || endpoint.trim() === ''}>
                {isConnecting ? 'Подключение…' : 'Подключиться и загрузить инструменты'}
              </button>
            </div>
            <div className="mcp-header-fields">
              <label>
                Header name
                <input
                  type="text"
                  value={headerName}
                  onChange={(event) => setHeaderName(event.target.value)}
                  placeholder="Authorization"
                  disabled={isConnecting}
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <label>
                Header value
                <input
                  type="password"
                  value={headerValue}
                  onChange={(event) => setHeaderValue(event.target.value)}
                  placeholder="Bearer token"
                  disabled={isConnecting}
                  autoComplete="new-password"
                  spellCheck={false}
                />
              </label>
            </div>
            <small>
              Поддерживаются только публичные HTTPS endpoints. Endpoint и headers не сохраняются.
            </small>
          </form>

          {isConnecting && (
            <div className="mcp-connection-steps" aria-live="polite">
              <span className="is-active">
                <i aria-hidden="true" /> DNS Resolve
              </span>
              <span>
                <i aria-hidden="true" /> Handshake
              </span>
              <span>
                <i aria-hidden="true" /> Read Tools
              </span>
            </div>
          )}

          {connectionState === 'error' && error && (
            <div className="mcp-error-state" role="alert">
              <div className="mcp-error-icon" aria-hidden="true">
                !
              </div>
              <div>
                <strong>Не удалось подключиться к MCP server</strong>
                <p>{error}</p>
                <button type="button" onClick={() => void connect()}>
                  Повторить попытку
                </button>
              </div>
            </div>
          )}
        </article>

        {hasConnection && result && (
          <>
            <article className="mcp-server-summary">
              <div className="mcp-server-icon" aria-hidden="true">
                ◇
              </div>
              <div className="mcp-server-details">
                <div className="mcp-server-title-row">
                  <div>
                    <span className="mcp-connected-label">
                      <i aria-hidden="true" /> Connected
                    </span>
                    <h2>{result.server.name ?? 'MCP server'}</h2>
                  </div>
                  <button type="button" className="mcp-disconnect-button" onClick={disconnect}>
                    Отключить server
                  </button>
                </div>
                <dl>
                  <div>
                    <dt>Version</dt>
                    <dd>{result.server.version ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Endpoint</dt>
                    <dd>{result.endpoint}</dd>
                  </div>
                </dl>
              </div>
            </article>

            <article className="mcp-tools-card">
              <div className="mcp-card-heading">
                <div>
                  <h2>Tools inventory</h2>
                  <p>Инструменты доступны только для просмотра.</p>
                </div>
                <span className="mcp-tool-count">{result.tools.length}</span>
              </div>
              {result.tools.length === 0 ? (
                <div className="mcp-empty-state">
                  <span aria-hidden="true">◇</span>
                  <strong>No tools available</strong>
                  <p>Сервер подключён, но не вернул доступных инструментов.</p>
                </div>
              ) : (
                <div className="mcp-tool-list">
                  {result.tools.map((tool) => (
                    <div className="mcp-tool-item" key={tool.name}>
                      <div className="mcp-tool-item-icon" aria-hidden="true">
                        ⌁
                      </div>
                      <div>
                        <h3>{tool.name}</h3>
                        <p>{tool.description ?? 'Описание отсутствует.'}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </article>
          </>
        )}
      </div>
    </section>
  )
}
