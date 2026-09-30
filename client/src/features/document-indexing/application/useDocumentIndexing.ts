import { useCallback, useEffect, useState } from 'react'
import {
  getDocumentIndexingRun,
  getCurrentDocumentIndexingRun,
  getEmbeddingProviders,
  getEmbeddingSettings,
  getLatestDocumentIndex,
  saveEmbeddingSettings,
  startDocumentIndexing,
} from '../../../data/api/documentIndexingApi'
import {
  EmbeddingProviderOption,
  EmbeddingSettings,
  IndexingRunStatus,
  LatestIndex,
} from '../../../domain/models/documentIndexing'

async function loadLibrarySnapshot() {
  const [settings, latest, run] = await Promise.all([
    getEmbeddingSettings(),
    getLatestDocumentIndex(),
    getCurrentDocumentIndexingRun(),
  ])
  return { settings, latest, run }
}

export function useDocumentIndexing() {
  const [settings, setSettings] = useState<EmbeddingSettings | null>(null)
  const [providers, setProviders] = useState<EmbeddingProviderOption[]>([])
  const [latest, setLatest] = useState<LatestIndex | null>(null)
  const [run, setRun] = useState<IndexingRunStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [providersLoading, setProvidersLoading] = useState(true)
  const [providersError, setProvidersError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const applySnapshot = useCallback((snapshot: Awaited<ReturnType<typeof loadLibrarySnapshot>>) => {
    setSettings(snapshot.settings)
    setLatest(snapshot.latest)
    setRun(snapshot.run.state === 'idle' ? null : snapshot.run)
  }, [])

  const loadProviders = useCallback(async () => {
    setProvidersLoading(true)
    try {
      const catalog = await getEmbeddingProviders()
      setProviders(catalog.providers)
      setProvidersError(null)
    } catch (reason) {
      setProvidersError(
        reason instanceof Error ? reason.message : 'Не удалось загрузить список провайдеров',
      )
    } finally {
      setProvidersLoading(false)
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const snapshot = await loadLibrarySnapshot()
      applySnapshot(snapshot)
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить библиотеку')
    } finally {
      setLoading(false)
    }
    void loadProviders()
  }, [applySnapshot, loadProviders])

  useEffect(() => {
    let active = true
    async function loadInitialSnapshot() {
      try {
        const snapshot = await loadLibrarySnapshot()
        if (active) {
          applySnapshot(snapshot)
          setError(null)
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Не удалось загрузить библиотеку')
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    async function loadInitialProviders() {
      try {
        const catalog = await getEmbeddingProviders()
        if (active) {
          setProviders(catalog.providers)
          setProvidersError(null)
        }
      } catch (reason) {
        if (active) {
          setProvidersError(
            reason instanceof Error ? reason.message : 'Не удалось загрузить список провайдеров',
          )
        }
      } finally {
        if (active) setProvidersLoading(false)
      }
    }
    void loadInitialSnapshot()
    void loadInitialProviders()
    return () => {
      active = false
    }
  }, [applySnapshot])

  useEffect(() => {
    const runId = run?.run_id
    if (typeof runId !== 'string' || run?.state !== 'running') return
    const activeRunId = runId
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const nextRun = await getDocumentIndexingRun(activeRunId)
        if (!active) return
        setRun(nextRun)
        if (nextRun.state === 'completed' || nextRun.state === 'failed') {
          const nextLatest = await getLatestDocumentIndex()
          if (active) setLatest(nextLatest)
          return
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Не удалось получить статус запуска')
        }
      }
      if (active) timer = setTimeout(() => void poll(), 1000)
    }

    timer = setTimeout(() => void poll(), 500)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [run?.run_id, run?.state])

  const saveSettings = useCallback(async (provider: string, model: string) => {
    setSaving(true)
    try {
      const nextSettings = await saveEmbeddingSettings({ provider, model })
      setSettings(nextSettings)
      setError(null)
      return nextSettings
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Не удалось сохранить настройки'
      setError(message)
      throw reason
    } finally {
      setSaving(false)
    }
  }, [])

  const start = useCallback(
    async (provider: string, model: string) => {
      setStarting(true)
      try {
        const saved = await saveSettings(provider, model)
        const nextRun = await startDocumentIndexing()
        setRun(nextRun)
        setSettings(saved)
        setError(null)
        return nextRun
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : 'Не удалось запустить индексацию'
        setError(message)
        throw reason
      } finally {
        setStarting(false)
      }
    },
    [saveSettings],
  )

  return {
    settings,
    providers,
    latest,
    run,
    loading,
    providersLoading,
    providersError,
    saving,
    starting,
    error,
    refresh,
    saveSettings,
    start,
  }
}
