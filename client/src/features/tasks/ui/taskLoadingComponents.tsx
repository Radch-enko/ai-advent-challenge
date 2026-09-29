import { TaskPlanStep } from '../../../domain/models/task'

export function TaskSubtaskLoadingMessage({
  step,
  expanded,
  onToggle,
}: {
  step: TaskPlanStep
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <article className="message assistant task-subtask-loading-message">
      <span className="avatar">◇</span>
      <div className="message-body">
        {expanded ? (
          <div className="task-subtask-message-loading-expanded">
            <button
              type="button"
              className="task-subtask-message-expanded-toggle"
              aria-expanded={true}
              onClick={onToggle}
            >
              <span>
                Подзадача {step.order}: {step.title}
              </span>
              <span aria-hidden="true">⌄</span>
            </button>
            <p>Выполняется подзадача…</p>
            <small>Ответ появится после завершения шага.</small>
          </div>
        ) : (
          <button
            type="button"
            className="task-subtask-message-collapsed loading"
            aria-expanded={false}
            onClick={onToggle}
          >
            <span className="task-subtask-message-dot loading" aria-hidden="true" />
            <span>
              <b>Выполняется {step.title}</b>
              <small>Нажмите, чтобы открыть</small>
            </span>
            <span className="task-subtask-message-chevron" aria-hidden="true">
              ›
            </span>
          </button>
        )}
      </div>
    </article>
  )
}
