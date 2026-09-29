import { useCallback, useState } from 'react'
import { getSessions } from '../../../data/api/sessionsApi'
import { ChatSessionSummary } from '../../../domain/models/session'

export function useSavedSessions() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      setSessions(await getSessions())
      setError(null)
      return true
    } catch {
      setError('Не удалось обновить список сессий.')
      return false
    }
  }, [])

  return { sessions, error, refresh }
}
