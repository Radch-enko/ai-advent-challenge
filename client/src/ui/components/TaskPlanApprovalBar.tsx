import { TaskState } from '../../domain/models/task'

type Props = {
  task: TaskState
  feedback: string
  submitting: boolean
  error?: string | null
  onFeedbackChange: (value: string) => void
  onApprove: () => void
  onRequestChanges: () => void
}

export function TaskPlanApprovalBar({
  task,
  feedback,
  submitting,
  error,
  onFeedbackChange,
  onApprove,
  onRequestChanges,
}: Props) {
  return (
    <section className="task-plan-approval" aria-label="Утверждение плана">
      <div className="task-plan-approval-copy">
        <b>План готов к проверке</b>
        <span>{task.plan?.steps.length ?? 0} последовательных шагов. Выберите действие:</span>
      </div>
      <div className="task-plan-approval-actions">
        <button
          type="button"
          className="task-plan-approve"
          onClick={onApprove}
          disabled={submitting}
        >
          Да, реализовать этот план
        </button>
        <div className="task-plan-feedback-row">
          <textarea
            value={feedback}
            onChange={(event) => onFeedbackChange(event.target.value)}
            placeholder="Что изменить в плане?"
            rows={2}
            disabled={submitting}
            aria-label="Замечания к плану"
          />
          <button
            type="button"
            className="task-plan-request-changes"
            onClick={onRequestChanges}
            disabled={submitting || !feedback.trim()}
          >
            Нет, указать правки
          </button>
        </div>
      </div>
      {error && <p className="task-plan-approval-error">{error}</p>}
    </section>
  )
}
