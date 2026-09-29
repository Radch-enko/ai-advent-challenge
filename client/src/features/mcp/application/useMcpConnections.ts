import { useCallback, useEffect, useState } from 'react'
import { listMcpConnections } from '../../../data/api/mcpApi'
import { McpConnection } from '../../../domain/models/mcp'

export function useMcpConnections() {
  const [connections, setConnections] = useState<McpConnection[]>([])

  const refresh = useCallback(async () => {
    try {
      setConnections(await listMcpConnections())
    } catch {
      setConnections([])
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => void refresh())
  }, [refresh])

  return { connections, refresh }
}
