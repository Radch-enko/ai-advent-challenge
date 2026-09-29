import { Dispatch, MutableRefObject, SetStateAction, useEffect, useState } from 'react'
import {
  approveMemory,
  clearWorkingMemory,
  deleteWorkingMemory,
  getPendingMemory,
  getWorkingMemory,
  rejectMemory,
  undoWorkingMemory,
  updateWorkingMemory,
} from '../../../data/api/memoryApi'
import {
  createProfileMemory,
  deleteProfileMemory,
  getProfileMemory,
  updateProfileMemory,
} from '../../../data/api/profilesApi'
import { getSessionFacts } from '../../../data/api/sessionsApi'
import { ChatSession } from '../../../domain/models/session'
import {
  LongTermMemoryItem,
  MemoryEvent,
  PendingMemorySuggestion,
  WorkingMemoryItem,
} from '../../../domain/models/memory'

type SessionMemoryOptions = {
  session: ChatSession | null
  activeSessionIdRef: MutableRefObject<string | null>
  setSettingsError: Dispatch<SetStateAction<string | null>>
}

type MemoryValue = Pick<LongTermMemoryItem, 'category' | 'key' | 'value'>

export function useSessionMemory({
  session,
  activeSessionIdRef,
  setSettingsError,
}: SessionMemoryOptions) {
  const [facts, setFacts] = useState<Record<string, string>>({})
  const [longTermMemory, setLongTermMemory] = useState<LongTermMemoryItem[]>([])
  const [memoryEvents, setMemoryEvents] = useState<MemoryEvent[]>([])
  const [pendingMemory, setPendingMemory] = useState<PendingMemorySuggestion[]>([])
  const [workingMemory, setWorkingMemory] = useState<WorkingMemoryItem[]>([])

  useEffect(() => {
    let active = true
    const sessionId = session?.id
    queueMicrotask(() => {
      if (!active) return
      if (!sessionId) {
        setFacts({})
        setLongTermMemory([])
        setMemoryEvents([])
        setPendingMemory([])
        setWorkingMemory([])
        return
      }

      const isCurrentSession = () => active && activeSessionIdRef.current === sessionId
      setFacts({})
      setLongTermMemory([])
      setMemoryEvents([])
      setPendingMemory([])
      setWorkingMemory([])

      void getSessionFacts(sessionId)
        .then((items) => {
          if (isCurrentSession()) setFacts(items)
        })
        .catch(() => {})
      void getWorkingMemory(sessionId)
        .then((items) => {
          if (isCurrentSession()) setWorkingMemory(items)
        })
        .catch(() => {
          if (isCurrentSession()) setWorkingMemory([])
        })
      void getPendingMemory(sessionId)
        .then((items) => {
          if (isCurrentSession()) setPendingMemory(items)
        })
        .catch(() => {
          if (isCurrentSession()) setPendingMemory([])
        })
      if (session.profile_name) {
        void getProfileMemory(session.profile_name)
          .then((items) => {
            if (isCurrentSession()) setLongTermMemory(items)
          })
          .catch(() => {
            if (isCurrentSession()) setLongTermMemory([])
          })
      }
    })

    return () => {
      active = false
    }
  }, [session?.id, session?.profile_name, activeSessionIdRef])

  async function refreshWorking(sessionId: string) {
    try {
      const items = await getWorkingMemory(sessionId)
      if (activeSessionIdRef.current === sessionId) setWorkingMemory(items)
    } catch {
      if (activeSessionIdRef.current === sessionId) setWorkingMemory([])
    }
  }

  async function editWorking(sessionId: string, item: WorkingMemoryItem) {
    const value = window.prompt(`Value for ${item.key}`, item.value)
    if (value == null || !value.trim()) return
    const result = await updateWorkingMemory(sessionId, item.id, {
      key: item.key,
      value: value.trim(),
    })
    if (activeSessionIdRef.current !== sessionId) return
    setMemoryEvents((events) => [...events, ...result.memory_events])
    await refreshWorking(sessionId)
  }

  async function clearWorking(sessionId: string) {
    const result = await clearWorkingMemory(sessionId)
    if (activeSessionIdRef.current !== sessionId) return
    setMemoryEvents((events) => [...events, ...result.memory_events])
    await refreshWorking(sessionId)
  }

  async function undoWorking(sessionId: string) {
    const result = await undoWorkingMemory(sessionId)
    if (activeSessionIdRef.current !== sessionId) return
    setMemoryEvents((events) => [...events, ...result.memory_events])
    await refreshWorking(sessionId)
  }

  async function removeWorking(sessionId: string, item: WorkingMemoryItem) {
    try {
      const result = await deleteWorkingMemory(sessionId, item.id)
      if (activeSessionIdRef.current !== sessionId) return
      setMemoryEvents((events) => [...events, ...result.memory_events])
      await refreshWorking(sessionId)
    } catch (error) {
      appendMemoryError(sessionId, error, 'Could not delete working memory')
    }
  }

  async function approvePending(sessionId: string, suggestion: PendingMemorySuggestion) {
    if (!session?.profile_name || activeSessionIdRef.current !== sessionId) return
    try {
      const item = await approveMemory(sessionId, suggestion.id)
      if (activeSessionIdRef.current !== sessionId) return
      setLongTermMemory((items) => {
        if (suggestion.candidate.action === 'create') return [...items, item]
        if (suggestion.candidate.action === 'delete')
          return items.filter((current) => current.id !== item.id)
        return items.map((current) => (current.id === item.id ? item : current))
      })
      setMemoryEvents((events) => [...events, ...item.memory_events])
      setPendingMemory((items) => items.filter((current) => current.id !== suggestion.id))
    } catch (error) {
      appendMemoryError(sessionId, error, 'Could not approve memory')
    }
  }

  async function rejectPending(sessionId: string, suggestion: PendingMemorySuggestion) {
    try {
      const result = await rejectMemory(sessionId, suggestion.id)
      if (activeSessionIdRef.current !== sessionId) return
      setPendingMemory((items) => items.filter((current) => current.id !== suggestion.id))
      setMemoryEvents((events) => [...events, ...result.memory_events])
    } catch (error) {
      appendMemoryError(sessionId, error, 'Could not reject memory')
    }
  }

  async function addLongTermMemory(sessionId: string, profileName: string, value: MemoryValue) {
    if (activeSessionIdRef.current !== sessionId) return
    setSettingsError(null)
    try {
      const created = await createProfileMemory(profileName, value)
      if (activeSessionIdRef.current === sessionId)
        setLongTermMemory((current) => [...current, created])
    } catch (error) {
      if (activeSessionIdRef.current === sessionId)
        setSettingsError(error instanceof Error ? error.message : 'Не удалось сохранить память')
    }
  }

  async function editLongTermMemory(
    sessionId: string,
    profileName: string,
    itemId: string,
    value: MemoryValue,
  ) {
    if (activeSessionIdRef.current !== sessionId) return
    setSettingsError(null)
    try {
      const updated = await updateProfileMemory(profileName, itemId, value)
      if (activeSessionIdRef.current === sessionId)
        setLongTermMemory((current) => current.map((item) => (item.id === itemId ? updated : item)))
    } catch (error) {
      if (activeSessionIdRef.current === sessionId)
        setSettingsError(error instanceof Error ? error.message : 'Не удалось обновить память')
    }
  }

  async function removeLongTermMemory(sessionId: string, profileName: string, itemId: string) {
    if (activeSessionIdRef.current !== sessionId) return
    setSettingsError(null)
    try {
      await deleteProfileMemory(profileName, itemId)
      if (activeSessionIdRef.current === sessionId)
        setLongTermMemory((current) => current.filter((item) => item.id !== itemId))
    } catch (error) {
      if (activeSessionIdRef.current === sessionId)
        setSettingsError(error instanceof Error ? error.message : 'Не удалось удалить память')
    }
  }

  function appendMemoryError(sessionId: string, error: unknown, fallback: string) {
    if (activeSessionIdRef.current !== sessionId) return
    setMemoryEvents((events) => [
      ...events,
      {
        id: String(Date.now()),
        scope: 'long_term',
        action: 'error',
        message: error instanceof Error ? error.message : fallback,
      },
    ])
  }

  return {
    facts,
    setFacts,
    longTermMemory,
    setLongTermMemory,
    memoryEvents,
    setMemoryEvents,
    pendingMemory,
    setPendingMemory,
    workingMemory,
    setWorkingMemory,
    editWorking,
    clearWorking,
    undoWorking,
    removeWorking,
    approvePending,
    rejectPending,
    addLongTermMemory,
    editLongTermMemory,
    removeLongTermMemory,
  }
}
