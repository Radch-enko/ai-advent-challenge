import {
  MemoryEvent,
  MemoryMutationResponse,
  PendingMemorySuggestion,
  WorkingMemoryItem,
} from '../../domain/models/memory'
import { request } from './request'

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
