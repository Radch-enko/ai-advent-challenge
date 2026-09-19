import { AgentConfig, CompletionConfig } from '../../domain/models/agent'
import {
  AgentLogDetail,
  FactsUpdateEvent,
  ProviderTrace,
  SummarizationEvent,
  TokenUsage,
} from '../../domain/models/chat'
import { Provider, ProviderModel } from '../../domain/models/provider'
import { TaskState } from '../../domain/models/task'
import { UserProfile, UserProfileInput, UserProfileUpdate } from '../../domain/models/userProfile'
import {
  LongTermMemoryItem,
  MemoryEvent,
  PendingMemorySuggestion,
  WorkingMemoryItem,
} from '../../domain/models/memory'

export type { AgentConfig, CompletionConfig, Provider, ProviderModel }

type ChatResponseData = {
  content: string
  provider: Provider
  model: string
  usage?: TokenUsage | null
  context_window?: number | null
  trace?: ProviderTrace | null
}

type SessionChatResponseData = Omit<ChatResponseData, 'trace'> & { trace?: null }

export type ChatResponse = {
  response: ChatResponseData
  agent_log_id?: string
  summarization_events: SummarizationEvent[]
  facts_events: FactsUpdateEvent[]
  facts: Record<string, string>
  memory_events: MemoryEvent[]
  pending_memory: PendingMemorySuggestion[]
  working_memory: WorkingMemoryItem[]
}

export type SessionChatResponse = Omit<ChatResponse, 'response' | 'agent_log_id'> & {
  response: SessionChatResponseData
  agent_log_id: string
}

export type ApiResult<T> = { data: T; status: number }
export type MemoryMutationResponse = LongTermMemoryItem & { memory_events: MemoryEvent[] }

export type StoredMessage = {
  role: 'user' | 'assistant'
  content: string
  created_at?: string | null
  usage?: TokenUsage | null
  context_window?: number | null
  agent_log_id?: string | null
  task_id?: string | null
  task_step_id?: string | null
}
export type ChatSession = {
  id: string
  title: string | null
  profile_name: string | null
  user_profile_id: string | null
  long_term_memory_enabled: boolean
  task_mode_enabled: boolean
  task: TaskState | null
  tasks: TaskState[]
  config: AgentConfig
  messages: StoredMessage[]
  context: {
    summary: string
    summarized_message_count: number
    events: SummarizationEvent[]
    facts_events: FactsUpdateEvent[]
  }
  created_at: string
  updated_at: string
}
export type ChatSessionSummary = Pick<ChatSession, 'id' | 'title' | 'profile_name' | 'updated_at'>

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(apiErrorMessage(body, status))
  }

  get providerTrace(): ChatResponse['response']['trace'] {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    return typeof detail === 'object' && detail !== null && 'provider_trace' in detail
      ? (detail.provider_trace as ChatResponse['response']['trace'])
      : undefined
  }

  get errorCode(): string | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    return typeof detail === 'object' &&
      detail !== null &&
      'code' in detail &&
      typeof detail.code === 'string'
      ? detail.code
      : undefined
  }

  get agentLogId(): string | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    return typeof detail === 'object' &&
      detail !== null &&
      'agent_log_id' in detail &&
      typeof detail.agent_log_id === 'string'
      ? detail.agent_log_id
      : undefined
  }

  get summarizationEvent(): SummarizationEvent | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    if (typeof detail !== 'object' || detail === null || !('summarization_event' in detail)) {
      return undefined
    }
    return detail.summarization_event as SummarizationEvent
  }

  get factsEvent(): FactsUpdateEvent | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    if (typeof detail !== 'object' || detail === null || !('facts_event' in detail)) {
      return undefined
    }
    return detail.facts_event as FactsUpdateEvent
  }
}

function apiErrorMessage(body: unknown, status: number): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return `Request failed with status ${status}`
  }
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    return String(detail.message)
  }
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
  return {
    data: response.status === 204 ? (undefined as T) : ((await response.json()) as T),
    status: response.status,
  }
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

export function sendMessageWithMeta(
  agentId: string,
  content: string,
): Promise<ApiResult<ChatResponse>> {
  return requestWithMeta(`/agents/${agentId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export function complete(
  config: CompletionConfig,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
): Promise<ChatResponse> {
  return request('/completions', { method: 'POST', body: JSON.stringify({ config, messages }) })
}

export function completeWithMeta(
  config: CompletionConfig,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
): Promise<ApiResult<ChatResponse>> {
  return requestWithMeta('/completions', {
    method: 'POST',
    body: JSON.stringify({ config, messages }),
  })
}

export function getModels(provider: Provider): Promise<ProviderModel[]> {
  return request(`/providers/${provider}/models`)
}
export function getProfiles(): Promise<Record<string, AgentConfig>> {
  return request('/profiles')
}
export function getProfileMemory(profileName: string): Promise<LongTermMemoryItem[]> {
  return request(`/profiles/${encodeURIComponent(profileName)}/memory`)
}
export function createProfileMemory(
  profileName: string,
  value: Pick<LongTermMemoryItem, 'category' | 'key' | 'value'>,
): Promise<LongTermMemoryItem> {
  return request(`/profiles/${encodeURIComponent(profileName)}/memory`, {
    method: 'POST',
    body: JSON.stringify(value),
  })
}
export function updateProfileMemory(
  profileName: string,
  itemId: string,
  value: Pick<LongTermMemoryItem, 'category' | 'key' | 'value'>,
): Promise<LongTermMemoryItem> {
  return request(
    `/profiles/${encodeURIComponent(profileName)}/memory/${encodeURIComponent(itemId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(value),
    },
  )
}
export function deleteProfileMemory(profileName: string, itemId: string): Promise<void> {
  return fetch(
    `/api/profiles/${encodeURIComponent(profileName)}/memory/${encodeURIComponent(itemId)}`,
    {
      method: 'DELETE',
    },
  ).then((response) => {
    if (!response.ok) throw new Error(`Could not delete memory item: ${response.status}`)
  })
}
export async function createAgentFromProfile(profileName: string): Promise<string> {
  const result = await request<{ agent_id: string }>('/agents', {
    method: 'POST',
    body: JSON.stringify({ profile_name: profileName }),
  })
  return result.agent_id
}

export function getSessions(): Promise<ChatSessionSummary[]> {
  return request('/sessions')
}
export function getUserProfiles(): Promise<UserProfile[]> {
  return request('/user-profiles')
}
export function createUserProfile(input: UserProfileInput): Promise<UserProfile> {
  return request('/user-profiles', { method: 'POST', body: JSON.stringify(input) })
}
export function updateUserProfile(
  profileId: string,
  input: UserProfileUpdate,
): Promise<UserProfile> {
  return request(`/user-profiles/${encodeURIComponent(profileId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}
export function deleteUserProfile(profileId: string): Promise<void> {
  return request(`/user-profiles/${encodeURIComponent(profileId)}`, { method: 'DELETE' })
}
export function updateSessionUserProfile(
  sessionId: string,
  profileId: string | null,
): Promise<ChatSession> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/user-profile`, {
    method: 'PATCH',
    body: JSON.stringify({ user_profile_id: profileId }),
  })
}
export function getSession(sessionId: string): Promise<ChatSession> {
  return request(`/sessions/${sessionId}`)
}
export function getSessionFacts(sessionId: string): Promise<Record<string, string>> {
  return request(`/sessions/${sessionId}/facts`)
}
export function getAgentLog(sessionId: string, agentLogId: string): Promise<AgentLogDetail> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/agent-logs/${encodeURIComponent(agentLogId)}`,
  )
}
export function getWorkingMemory(sessionId: string): Promise<WorkingMemoryItem[]> {
  return request(`/sessions/${sessionId}/working-memory`)
}
export function deleteWorkingMemory(
  sessionId: string,
  itemId: string,
): Promise<{ working_memory: WorkingMemoryItem[]; memory_events: MemoryEvent[] }> {
  return request(`/sessions/${sessionId}/working-memory/${itemId}`, { method: 'DELETE' })
}
export function updateWorkingMemory(
  sessionId: string,
  itemId: string,
  value: Pick<WorkingMemoryItem, 'key' | 'value'>,
): Promise<WorkingMemoryItem & { memory_events: MemoryEvent[] }> {
  return request(`/sessions/${sessionId}/working-memory/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(value),
  })
}
export function clearWorkingMemory(sessionId: string): Promise<{ memory_events: MemoryEvent[] }> {
  return request(`/sessions/${sessionId}/working-memory`, { method: 'DELETE' })
}
export function undoWorkingMemory(
  sessionId: string,
): Promise<{ working_memory: WorkingMemoryItem[]; memory_events: MemoryEvent[] }> {
  return request(`/sessions/${sessionId}/working-memory/undo`, {
    method: 'POST',
  })
}
export function getPendingMemory(sessionId: string): Promise<PendingMemorySuggestion[]> {
  return request(`/sessions/${sessionId}/memory/pending`)
}
export function approveMemory(
  sessionId: string,
  candidateId: string,
): Promise<MemoryMutationResponse> {
  return request(`/sessions/${sessionId}/memory/pending/${candidateId}/approve`, { method: 'POST' })
}
export function rejectMemory(
  sessionId: string,
  candidateId: string,
): Promise<{ memory_events: MemoryEvent[] }> {
  return request(`/sessions/${sessionId}/memory/pending/${candidateId}/reject`, {
    method: 'POST',
  })
}
export function createSession(
  config: AgentConfig,
  userProfileId: string | null = null,
  taskModeEnabled = false,
): Promise<ChatSession> {
  return request('/sessions', {
    method: 'POST',
    body: JSON.stringify({
      config,
      user_profile_id: userProfileId,
      task_mode_enabled: taskModeEnabled,
    }),
  })
}
export function updateSessionTaskMode(sessionId: string, enabled: boolean): Promise<ChatSession> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/task-mode`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}
export function startTask(sessionId: string, instruction: string): Promise<TaskState> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/tasks`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  })
}
export function getTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}`)
}
export function pauseTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/pause`,
    { method: 'POST' },
  )
}
export function resumeTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/resume`,
    { method: 'POST' },
  )
}
export function retryTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/retry`,
    { method: 'POST' },
  )
}
export function createSessionFromProfile(profileName: string): Promise<ChatSession> {
  return request('/sessions', {
    method: 'POST',
    body: JSON.stringify({ profile_name: profileName }),
  })
}
export function updateSessionContextManagement(
  sessionId: string,
  value: Pick<AgentConfig['context_management'], 'enabled' | 'strategy' | 'recent_message_limit'>,
): Promise<ChatSession> {
  return request(`/sessions/${sessionId}/context-management`, {
    method: 'PATCH',
    body: JSON.stringify({
      enabled: value.enabled,
      strategy: value.strategy,
      recent_message_limit: value.recent_message_limit,
    }),
  })
}
export function updateSessionLongTermMemory(
  sessionId: string,
  enabled: boolean,
): Promise<ChatSession> {
  return request(`/sessions/${sessionId}/long-term-memory`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}
export function forkSession(sessionId: string, messageIndex: number): Promise<ChatSession> {
  return request(`/sessions/${sessionId}/fork`, {
    method: 'POST',
    body: JSON.stringify({ message_index: messageIndex }),
  })
}
export function deleteSession(sessionId: string): Promise<void> {
  return fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' }).then((response) => {
    if (!response.ok) throw new Error(`Could not delete session: ${response.status}`)
  })
}
export function sendSessionMessageWithMeta(
  sessionId: string,
  content: string,
  config?: AgentConfig,
): Promise<ApiResult<SessionChatResponse>> {
  return requestWithMeta(`/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, config }),
  })
}
export function retrySessionSummarizationWithMeta(
  sessionId: string,
): Promise<ApiResult<SessionChatResponse>> {
  return requestWithMeta(`/sessions/${sessionId}/summarization/retry`, { method: 'POST' })
}
