import { Dispatch, MutableRefObject, SetStateAction, useCallback, useState } from 'react'
import {
  approveTaskPlan,
  pauseTask,
  requestTaskPlanChanges,
  retryTask,
  resumeTask,
} from '../../../data/api/tasksApi'
import { ChatSession } from '../../../domain/models/session'
import { ChatMessage } from '../../../domain/models/chat'
import { TaskState } from '../../../domain/models/task'

type TaskActionsOptions = {
  session: ChatSession | null
  activeTask: TaskState | undefined
  activeSessionIdRef: MutableRefObject<string | null>
  setActiveSession: Dispatch<SetStateAction<ChatSession | null>>
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setExpandedTaskMessageKeys: Dispatch<SetStateAction<Record<string, boolean>>>
}

export function useTaskActions({
  session,
  activeTask,
  activeSessionIdRef,
  setActiveSession,
  setMessages,
  setExpandedTaskMessageKeys,
}: TaskActionsOptions) {
  const [retryingTaskId, setRetryingTaskId] = useState<string | null>(null)
  const [taskRetryError, setTaskRetryError] = useState<{ taskId: string; message: string } | null>(
    null,
  )
  const [planFeedback, setPlanFeedback] = useState('')
  const [planApprovalSubmitting, setPlanApprovalSubmitting] = useState(false)
  const [planApprovalError, setPlanApprovalError] = useState<string | null>(null)
  const resetForSession = useCallback(() => {
    setRetryingTaskId(null)
    setTaskRetryError(null)
  }, [])

  function applyTaskUpdate(updated: TaskState, sessionId: string) {
    if (activeSessionIdRef.current !== sessionId) return
    setActiveSession((current) =>
      current
        ? {
            ...current,
            task: updated,
            tasks: current.tasks.map((item) => (item.id === updated.id ? updated : item)),
          }
        : current,
    )
  }

  async function approvePlan() {
    if (!session || !activeTask || activeTask.status !== 'waiting_for_approval') return
    setPlanApprovalSubmitting(true)
    setPlanApprovalError(null)
    try {
      applyTaskUpdate(await approveTaskPlan(session.id, activeTask.id), session.id)
    } catch (error) {
      setPlanApprovalError(error instanceof Error ? error.message : 'Не удалось утвердить план')
    } finally {
      setPlanApprovalSubmitting(false)
    }
  }

  async function requestChanges() {
    const feedback = planFeedback.trim()
    if (!session || !activeTask || activeTask.status !== 'waiting_for_approval' || !feedback) return
    setPlanApprovalSubmitting(true)
    setPlanApprovalError(null)
    try {
      applyTaskUpdate(await requestTaskPlanChanges(session.id, activeTask.id, feedback), session.id)
    } catch (error) {
      setPlanApprovalError(error instanceof Error ? error.message : 'Не удалось отправить правки')
    } finally {
      setPlanApprovalSubmitting(false)
    }
  }

  async function pause() {
    if (!session || !activeTask || activeTask.status !== 'running') return
    applyTaskUpdate(await pauseTask(session.id, activeTask.id), session.id)
  }

  async function resume() {
    if (!session || !activeTask || activeTask.status !== 'paused') return
    applyTaskUpdate(await resumeTask(session.id, activeTask.id), session.id)
  }

  async function retry(task: TaskState) {
    if (!session || task.status !== 'failed' || task.stage !== 'validation') return
    setRetryingTaskId(task.id)
    setTaskRetryError(null)
    try {
      const updated = await retryTask(session.id, task.id)
      applyTaskUpdate(updated, session.id)
      setMessages((current) =>
        current.filter((entry) => !(entry.taskId === task.id && entry.taskStepId != null)),
      )
      setExpandedTaskMessageKeys((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([key]) => !key.startsWith(`${task.id}:`)),
        ),
      )
    } catch (error) {
      setTaskRetryError({
        taskId: task.id,
        message: error instanceof Error ? error.message : 'Не удалось повторить проверку',
      })
    } finally {
      setRetryingTaskId(null)
    }
  }

  return {
    retryingTaskId,
    taskRetryError,
    planFeedback,
    setPlanFeedback,
    planApprovalSubmitting,
    planApprovalError,
    setPlanApprovalError,
    resetForSession,
    approvePlan,
    requestChanges,
    pause,
    resume,
    retry,
  }
}
