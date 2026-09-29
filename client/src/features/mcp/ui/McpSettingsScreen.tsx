import { McpConnectionState, useMcpSettings } from '../application/useMcpSettings'

const stateCopy: Record<McpConnectionState, string> = {
  idle: 'Не подключено',
  connecting: 'Подключение',
  connected: 'Подключено',
  empty: 'Подключено',
  error: 'Ошибка подключения',
}

export function McpSettingsScreen() {
  const {
    connectionId,
    setConnectionId,
    connectionName,
    setConnectionName,
    endpoint,
    setEndpoint,
    headerName,
    setHeaderName,
    headerValueEnv,
    setHeaderValueEnv,
    connections,
    connectionState,
    editingId,
    result,
    error,
    isConnecting,
    hasConnection,
    handleSubmit,
    connect,
    disconnect,
    editConnection,
    removeConnection,
    testConnection,
  } = useMcpSettings()

  return (
    <section className="mcp-settings-screen" aria-labelledby="mcp-settings-title">
      <header className="mcp-settings-header">
        <div>
          <p className="mcp-kicker">Настройки системы</p>
          <h1 id="mcp-settings-title">MCP connections</h1>
          <p>Подключите MCP server и просмотрите доступные инструменты.</p>
        </div>
        <div className="mcp-header-status">
          <span className="mcp-active-status">
            <i aria-hidden="true" /> Интеграция активна
          </span>
          <span className="mcp-discovery-badge">Discovery only</span>
        </div>
      </header>

      <div className="mcp-settings-content">
        {connections.length > 0 && (
          <article className="mcp-tools-card">
            <div className="mcp-card-heading">
              <div>
                <h2>Saved connections</h2>
                <p>Connections доступны для выбора в конфигурации агента.</p>
              </div>
              <span className="mcp-tool-count">{connections.length}</span>
            </div>
            <div className="mcp-tool-list">
              {connections.map((connection) => (
                <div className="mcp-tool-item" key={connection.id}>
                  <div className="mcp-tool-item-icon" aria-hidden="true">
                    ◇
                  </div>
                  <div>
                    <h3>{connection.name}</h3>
                    <p>
                      {connection.endpoint} · {connection.tools.length} tools
                    </p>
                    <div className="mcp-connection-actions">
                      <button
                        type="button"
                        className="mcp-action-button mcp-action-secondary"
                        onClick={() => editConnection(connection)}
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        className="mcp-action-button mcp-action-primary"
                        onClick={() => void testConnection(connection)}
                      >
                        Проверить
                      </button>
                      <button
                        type="button"
                        className="mcp-action-button mcp-action-danger"
                        onClick={() => void removeConnection(connection)}
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </article>
        )}
        <article className="mcp-security-notice">
          <div className="mcp-security-icon" aria-hidden="true">
            ✓
          </div>
          <div>
            <strong>Только чтение</strong>
            <span className="mcp-security-required">HTTPS / LOOPBACK</span>
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
            <div className="mcp-header-fields">
              <label>
                Connection ID
                <input
                  value={connectionId}
                  onChange={(event) => setConnectionId(event.target.value)}
                  placeholder="finances"
                  disabled={isConnecting || editingId !== null}
                  required
                />
              </label>
              <label>
                Название
                <input
                  value={connectionName}
                  onChange={(event) => setConnectionName(event.target.value)}
                  placeholder="Личные финансы"
                  disabled={isConnecting}
                  required
                />
              </label>
            </div>
            <label htmlFor="mcp-endpoint">Server endpoint</label>
            <div className="mcp-endpoint-row">
              <input
                id="mcp-endpoint"
                type="url"
                value={endpoint}
                onChange={(event) => setEndpoint(event.target.value)}
                placeholder="http://127.0.0.1:8001/mcp"
                disabled={isConnecting}
                autoComplete="off"
                spellCheck={false}
              />
              <button type="submit" disabled={isConnecting || endpoint.trim() === ''}>
                {isConnecting
                  ? 'Сохранение…'
                  : editingId
                    ? 'Сохранить connection'
                    : 'Добавить connection'}
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
                Secret env
                <input
                  type="text"
                  value={headerValueEnv}
                  onChange={(event) => setHeaderValueEnv(event.target.value)}
                  placeholder="COPIA_MCP_FINANCES_TOKEN"
                  disabled={isConnecting}
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            </div>
            <small>
              Для удалённых servers требуется HTTPS; HTTP разрешён только для localhost и loopback.
              Secret хранится только в environment, в registry сохраняется имя переменной.
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
