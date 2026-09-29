import { AgentConfig } from '../../domain/models/agent'
import { request } from './request'

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

export async function createAgentFromProfile(profileName: string): Promise<string> {
  const result = await request<{ agent_id: string }>('/agents', {
    method: 'POST',
    body: JSON.stringify({ profile_name: profileName }),
  })
  return result.agent_id
}

export function getProfiles(): Promise<Record<string, AgentConfig>> {
  return request('/profiles')
}
