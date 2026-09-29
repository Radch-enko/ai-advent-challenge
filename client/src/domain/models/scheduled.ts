import { TokenUsage } from './chat'

export type ScheduledRun = {
  job_id: string
  kind: string
  scheduled_at: string
  period_from: string
  period_to: string
  status: 'running' | 'completed' | 'failed'
  answer: string | null
  error: string | null
  started_at: string
  finished_at: string | null
  provider: string | null
  model: string | null
  usage: TokenUsage | null
}

export type ScheduledSummary = {
  job_id: string | null
  latest_run: ScheduledRun | null
  published_run: ScheduledRun | null
}

export type ScheduledJobStatus = {
  id: string
  name: string
  status: 'wait' | 'progress' | 'completed'
  next_run_at: string | null
}
