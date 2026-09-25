import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getLatestScheduledSummary, getScheduledJobStatuses } from '../../data/api/copiaApi'
import { ScheduledJobStatus, ScheduledSummary } from '../../domain/models/scheduled'

type Props = {
  onOpenLogs: (jobId: string, scheduledAt: string) => Promise<void>
}

function timeRemaining(nextRunAt: string | null, now: number): string {
  if (!nextRunAt || now === 0) return '—'
  const seconds = Math.max(0, Math.ceil((Date.parse(nextRunAt) - now) / 1000))
  if (!Number.isFinite(seconds)) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`
}

export function SummariesScreen({ onOpenLogs }: Props) {
  const [summary, setSummary] = useState<ScheduledSummary | null>(null)
  const [jobs, setJobs] = useState<ScheduledJobStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(0)
  const [logsLoading, setLogsLoading] = useState(false)
  const [logsError, setLogsError] = useState<string | null>(null)

  async function openLogs(jobId: string, scheduledAt: string) {
    setLogsLoading(true)
    setLogsError(null)
    try {
      await onOpenLogs(jobId, scheduledAt)
    } catch (reason) {
      setLogsError(reason instanceof Error ? reason.message : 'Не удалось загрузить логи')
    } finally {
      setLogsLoading(false)
    }
  }

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
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Не удалось загрузить сводку')
        }
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

  const publishedRun = summary?.published_run
  const publishedLogId = publishedRun?.agent_log_id

  return (
    <section className="summaries-screen">
      <h1>Сводки</h1>
      <div className="scheduled-jobs" aria-label="Статусы фоновых задач">
        {jobs.map((job) => (
          <div className="scheduled-job" key={job.id}>
            <strong>{job.name}</strong>
            <span aria-hidden="true">·</span>
            <span>До следующего запуска: {timeRemaining(job.next_run_at, now)}</span>
            <span className={`scheduled-job-status ${job.status}`}>{job.status}</span>
          </div>
        ))}
      </div>
      {loading ? <p>Загрузка сводки…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && !summary?.published_run ? <p>Сводок пока нет.</p> : null}
      {publishedRun?.answer ? (
        <>
          <article className="summary-answer markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{publishedRun.answer}</ReactMarkdown>
          </article>
          {publishedLogId ? (
            <button
              type="button"
              className="summary-logs-button"
              disabled={logsLoading}
              onClick={() => void openLogs(publishedRun.job_id, publishedRun.scheduled_at)}
            >
              {logsLoading ? 'Загрузка логов…' : 'Logs'}
            </button>
          ) : null}
          {logsError ? <p role="alert">{logsError}</p> : null}
        </>
      ) : null}
      {summary?.latest_run?.status === 'failed' ? (
        <p role="alert">Последний запуск завершился ошибкой: {summary.latest_run.error}</p>
      ) : null}
    </section>
  )
}
