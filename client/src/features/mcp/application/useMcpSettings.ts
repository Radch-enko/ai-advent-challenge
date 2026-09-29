import { FormEvent, useCallback, useEffect, useState } from 'react'
import {
  createMcpConnection,
  deleteMcpConnection,
  listMcpConnections,
  testMcpConnection,
  updateMcpConnection,
} from '../../../data/api/mcpApi'
import { McpConnection, McpDiscoveryResult } from '../../../domain/models/mcp'

export type McpConnectionState = 'idle' | 'connecting' | 'connected' | 'empty' | 'error'

function isSupportedMcpEndpoint(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      url.username === '' &&
      url.password === '' &&
      url.hash === ''
    )
  } catch {
    return false
  }
}

export function useMcpSettings() {
  const [connectionId, setConnectionId] = useState('')
  const [connectionName, setConnectionName] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [headerName, setHeaderName] = useState('')
  const [headerValueEnv, setHeaderValueEnv] = useState('')
  const [connections, setConnections] = useState<McpConnection[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [connectionState, setConnectionState] = useState<McpConnectionState>('idle')
  const [result, setResult] = useState<McpDiscoveryResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshConnections = useCallback(async () => {
    try {
      setConnections(await listMcpConnections())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить connections')
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => void refreshConnections())
  }, [refreshConnections])

  async function connect() {
    const normalizedEndpoint = endpoint.trim()
    const normalizedHeaderName = headerName.trim()
    const normalizedHeaderValueEnv = headerValueEnv.trim()
    if (!isSupportedMcpEndpoint(normalizedEndpoint)) {
      setConnectionState('error')
      setResult(null)
      setError('Введите корректный HTTP(S) endpoint без userinfo и fragment.')
      return
    }
    if ((normalizedHeaderName === '') !== (normalizedHeaderValueEnv === '')) {
      setConnectionState('error')
      setResult(null)
      setError('Укажите одновременно Header name и secret env или оставьте оба поля пустыми.')
      return
    }
    if (!connectionId.trim() || !connectionName.trim()) {
      setConnectionState('error')
      setError('Укажите ID и название connection.')
      return
    }

    setConnectionState('connecting')
    setResult(null)
    setError(null)
    try {
      const input = {
        id: connectionId.trim(),
        name: connectionName.trim(),
        endpoint: normalizedEndpoint,
        header_name: normalizedHeaderName || null,
        header_value_env: normalizedHeaderValueEnv || null,
      }
      const saved = await (editingId ? updateMcpConnection(input) : createMcpConnection(input))
      setResult({
        server: saved.server ?? { name: null, version: null },
        endpoint: saved.endpoint,
        tools: saved.tools,
      })
      setConnectionState(saved.tools.length > 0 ? 'connected' : 'empty')
      setEditingId(saved.id)
      await refreshConnections()
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
    setHeaderValueEnv('')
    setConnectionId('')
    setConnectionName('')
    setEditingId(null)
    setConnectionState('idle')
    setResult(null)
    setError(null)
  }

  function editConnection(connection: McpConnection) {
    setConnectionId(connection.id)
    setConnectionName(connection.name)
    setEndpoint(connection.endpoint)
    setHeaderName(connection.header_name ?? '')
    setHeaderValueEnv(connection.header_value_env ?? '')
    setEditingId(connection.id)
    setResult(
      connection.server
        ? { server: connection.server, endpoint: connection.endpoint, tools: connection.tools }
        : null,
    )
    setConnectionState('idle')
    setError(null)
  }

  async function removeConnection(connection: McpConnection) {
    try {
      await deleteMcpConnection(connection.id)
      if (editingId === connection.id) disconnect()
      await refreshConnections()
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : 'Не удалось удалить connection')
      setConnectionState('error')
    }
  }

  async function testConnection(connection: McpConnection) {
    setConnectionState('connecting')
    setError(null)
    try {
      const updated = await testMcpConnection(connection.id)
      setResult({
        server: updated.server ?? { name: null, version: null },
        endpoint: updated.endpoint,
        tools: updated.tools,
      })
      setConnectionState(updated.tools.length ? 'connected' : 'empty')
      await refreshConnections()
    } catch (testError) {
      setConnectionState('error')
      setError(testError instanceof Error ? testError.message : 'Проверка connection не удалась')
    }
  }

  return {
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
    isConnecting: connectionState === 'connecting',
    hasConnection: result !== null && ['connected', 'empty'].includes(connectionState),
    handleSubmit,
    connect,
    disconnect,
    editConnection,
    removeConnection,
    testConnection,
  }
}
