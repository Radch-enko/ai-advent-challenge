import { TaskState } from '../../domain/models/task'
import { request } from './request'

export function startTask(sessionId: string, instruction: string): Promise<TaskState> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/tasks`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  })
}

export function getTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}`)
}

export function approveTaskPlan(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/approve-plan`,
    { method: 'POST' },
  )
}

export function requestTaskPlanChanges(
  sessionId: string,
  taskId: string,
  feedback: string,
): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/request-plan-changes`,
    { method: 'POST', body: JSON.stringify({ feedback }) },
  )
}

export function pauseTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/pause`,
    { method: 'POST' },
  )
}

export function resumeTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/resume`,
    { method: 'POST' },
  )
}

export function retryTask(sessionId: string, taskId: string): Promise<TaskState> {
  return request(
    `/sessions/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/retry`,
    { method: 'POST' },
  )
}
