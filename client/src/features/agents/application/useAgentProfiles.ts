import { useEffect, useState } from 'react'
import { getProfiles } from '../../../data/api/agentsApi'
import { AgentConfig } from '../../../domain/models/agent'

export function useAgentProfiles() {
  const [profiles, setProfiles] = useState<Record<string, AgentConfig>>({})

  useEffect(() => {
    queueMicrotask(() => {
      void getProfiles()
        .then(setProfiles)
        .catch(() => setProfiles({}))
    })
  }, [])

  return profiles
}
