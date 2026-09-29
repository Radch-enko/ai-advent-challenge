import { UserProfile, UserProfileInput, UserProfileUpdate } from '../../domain/models/userProfile'
import { LongTermMemoryItem } from '../../domain/models/memory'
import type { ChatSession } from '../../domain/models/session'
import { request } from './request'

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
