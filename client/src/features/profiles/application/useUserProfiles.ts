import { useCallback, useEffect, useState } from 'react'
import { getUserProfiles } from '../../../data/api/profilesApi'
import { UserProfile } from '../../../domain/models/userProfile'

export function useUserProfiles() {
  const [profiles, setProfiles] = useState<UserProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (showError = true): Promise<boolean> => {
    setLoading(true)
    try {
      setProfiles(await getUserProfiles())
      setError(null)
      return true
    } catch (requestError) {
      if (showError) {
        setError(
          requestError instanceof Error ? requestError.message : 'Не удалось загрузить профили',
        )
      }
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => void refresh())
  }, [refresh])

  return { profiles, loading, error, refresh }
}
