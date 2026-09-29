import { AgentConfig } from '../../domain/models/agent'
import { request } from './request'
import type { ChatSession, ChatSessionSummary } from '../../domain/models/session'

export function getSessions(): Promise<ChatSessionSummary[]> {
  return request('/sessions')
}

export function getSession(sessionId: string): Promise<ChatSession> {
  return request(`/sessions/${sessionId}`)
}

export function getSessionFacts(sessionId: string): Promise<Record<string, string>> {
  return request(`/sessions/${sessionId}/facts`)
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
