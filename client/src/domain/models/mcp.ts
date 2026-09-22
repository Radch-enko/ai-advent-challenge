export type McpToolSummary = {
  name: string
  description: string | null
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
