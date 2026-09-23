export type McpToolSummary = {
  name: string
  description: string | null
  input_schema: Record<string, unknown>
}

export type McpConnection = {
  id: string
  name: string
  endpoint: string
  header_name: string | null
  header_value_env: string | null
  server: McpServerSummary | null
  tools: McpToolSummary[]
  updated_at: string
}

export type McpConnectionInput = Pick<
  McpConnection,
  'id' | 'name' | 'endpoint' | 'header_name' | 'header_value_env'
>

export type McpApproval = {
  id: string
  connection_id: string
  connection_name: string
  tool_name: string
  arguments: Record<string, unknown>
  decision: 'pending' | 'approved' | 'rejected'
}

export type McpServerSummary = {
  name: string | null
  version: string | null
}

export type McpDiscoveryResult = {
  server: McpServerSummary
  endpoint: string
  tools: McpToolSummary[]
}
