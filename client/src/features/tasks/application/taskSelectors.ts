import { ChatSession } from '../../../domain/models/session'
import { TaskPlanStep, TaskState } from '../../../domain/models/task'

export function tasksForSession(session: ChatSession | null): TaskState[] {
  if (!session) return []
  return session.tasks.length ? session.tasks : session.task ? [session.task] : []
}

export function isActiveTask(task: TaskState): boolean {
  return ['running', 'pause_requested', 'paused', 'waiting_for_approval'].includes(task.status)
}

export function currentTaskLoadingStep(task: TaskState): TaskPlanStep | undefined {
  if (
    task.stage !== 'execution' ||
    !['running', 'pause_requested'].includes(task.status) ||
    task.current_step == null ||
    task.plan == null
  )
    return undefined
  const step = task.plan.steps[task.current_step]
  return step && step.status !== 'completed' ? step : undefined
}
