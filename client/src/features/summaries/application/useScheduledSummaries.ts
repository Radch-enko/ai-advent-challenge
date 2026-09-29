import { useEffect, useState } from 'react'
import { getLatestScheduledSummary, getScheduledJobStatuses } from '../../../data/api/summariesApi'
import { ScheduledJobStatus, ScheduledSummary } from '../../../domain/models/scheduled'

export function useScheduledSummaries() {
  const [summary, setSummary] = useState<ScheduledSummary | null>(null)
  const [jobs, setJobs] = useState<ScheduledJobStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(0)

  useEffect(() => {
    let active = true
    let refreshTimer: ReturnType<typeof setTimeout> | undefined
    const clockTimer = setInterval(() => setNow(Date.now()), 1000)

    async function refresh() {
      try {
        const [latest, statuses] = await Promise.all([
          getLatestScheduledSummary(),
          getScheduledJobStatuses(),
        ])
        if (active) {
          setSummary(latest)
          setJobs(statuses)
          setError(null)
        }
      } catch (reason) {
        if (active)
          setError(reason instanceof Error ? reason.message : 'Не удалось загрузить сводку')
      } finally {
        if (active) {
          setLoading(false)
          refreshTimer = setTimeout(() => void refresh(), 2000)
        }
      }
    }

    void refresh()
    return () => {
      active = false
      clearInterval(clockTimer)
      clearTimeout(refreshTimer)
    }
  }, [])

  return { summary, jobs, loading, error, now }
}
