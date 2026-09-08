import { AgentConfig, CompletionConfig } from '../../domain/models/agent'
import { Provider, ProviderModel } from '../../domain/models/provider'

export type { AgentConfig, CompletionConfig, Provider, ProviderModel }

export type ChatResponse = {
  response: {
    content: string
    provider: Provider
    model: string
    trace?: {
      status_code: number
      request_body: Record<string, unknown>
      response_body: Record<string, unknown>
    }
  }
}

export type ApiResult<T> = { data: T; status: number }

export class ApiRequestError extends Error {
  constructor(public readonly status: number, public readonly body: unknown) {
    super(apiErrorMessage(body, status))
  }

  get providerTrace(): ChatResponse['response']['trace'] {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) return undefined
    const detail = this.body.detail
    return typeof detail === 'object' && detail !== null && 'provider_trace' in detail
      ? detail.provider_trace as ChatResponse['response']['trace']
      : undefined
  }
}

function apiErrorMessage(body: unknown, status: number): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return `Request failed with status ${status}`
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null && 'message' in detail) return String(detail.message)
  return `Request failed with status ${status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestWithMeta<T>(path, init)).data
}

async function requestWithMeta<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiRequestError(response.status, body)
  }
  return { data: await response.json() as T, status: response.status }
}

export async function createAgent(config: AgentConfig): Promise<string> {
  const result = await request<{ agent_id: string }>('/agents', {
    method: 'POST',
    body: JSON.stringify({ config }),
  })
  return result.agent_id
}

export function deleteAgent(agentId: string): Promise<unknown> {
  return fetch(`/api/agents/${agentId}`, { method: 'DELETE' }).then((response) => {
    if (!response.ok && response.status !== 404) {
      throw new Error(`Could not delete agent: ${response.status}`)
    }
  })
}

export function sendMessage(agentId: string, content: string): Promise<ChatResponse> {
  return request(`/agents/${agentId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export function sendMessageWithMeta(agentId: string, content: string): Promise<ApiResult<ChatResponse>> {
  return requestWithMeta(`/agents/${agentId}/messages`, { method: 'POST', body: JSON.stringify({ content }) })
}

export function complete(config: CompletionConfig, messages: Array<{ role: 'user' | 'assistant'; content: string }>): Promise<ChatResponse> {
  return request('/completions', { method: 'POST', body: JSON.stringify({ config, messages }) })
}

export function completeWithMeta(config: CompletionConfig, messages: Array<{ role: 'user' | 'assistant'; content: string }>): Promise<ApiResult<ChatResponse>> {
  return requestWithMeta('/completions', { method: 'POST', body: JSON.stringify({ config, messages }) })
}

export function getModels(provider: Provider): Promise<ProviderModel[]> { return request(`/providers/${provider}/models`) }
export function getProfiles(): Promise<Record<string, AgentConfig>> { return request('/profiles') }
export async function createAgentFromProfile(profileName: string): Promise<string> {
  const result = await request<{ agent_id: string }>('/agents', { method: 'POST', body: JSON.stringify({ profile_name: profileName }) })
  return result.agent_id
}
