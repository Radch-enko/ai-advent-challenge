import { McpConnection, McpConnectionInput, McpDiscoveryResult } from '../../domain/models/mcp'
import { request } from './request'

export function discoverMcpTools(
  endpoint: string,
  headerName?: string,
  headerValue?: string,
): Promise<McpDiscoveryResult> {
  return request('/mcp/discover', {
    method: 'POST',
    body: JSON.stringify({
      endpoint,
      header_name: headerName || null,
      header_value: headerValue || null,
    }),
  })
}

export function listMcpConnections(): Promise<McpConnection[]> {
  return request('/mcp/connections')
}

export function createMcpConnection(input: McpConnectionInput): Promise<McpConnection> {
  return request('/mcp/connections', { method: 'POST', body: JSON.stringify(input) })
}

export function updateMcpConnection(input: McpConnectionInput): Promise<McpConnection> {
  return request(`/mcp/connections/${encodeURIComponent(input.id)}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
}

export function deleteMcpConnection(connectionId: string): Promise<void> {
  return request(`/mcp/connections/${encodeURIComponent(connectionId)}`, { method: 'DELETE' })
}

export function testMcpConnection(connectionId: string): Promise<McpConnection> {
  return request(`/mcp/connections/${encodeURIComponent(connectionId)}/test`, { method: 'POST' })
}
