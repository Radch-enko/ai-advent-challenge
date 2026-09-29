import { ScheduledJobStatus, ScheduledSummary } from '../../domain/models/scheduled'
import { request } from './request'

export function getLatestScheduledSummary(): Promise<ScheduledSummary> {
  return request('/scheduled-summaries/latest')
}

export function getScheduledJobStatuses(): Promise<ScheduledJobStatus[]> {
  return request('/scheduled-jobs/status')
}
