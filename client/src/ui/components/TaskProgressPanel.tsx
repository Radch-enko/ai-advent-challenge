import { TaskLlmCall, TaskPlanStep, TaskState } from '../../domain/models/task'

const stages = [
  ['planning', 'Планирование'],
  ['plan_review', 'Согласование'],
  ['execution', 'Выполнение'],
  ['validation', 'Проверка'],
  ['done', 'Готово'],
] as const

type Props = {
  task: TaskState
  expanded: boolean
  onToggleExpanded: () => void
  onPause: () => void
  onResume: () => void
  onRetry: () => void
  retrying: boolean
  retryError?: string | null
  onOpenLogs: (agentLogId: string) => void
  onOpenAllLogs: () => void
}

export function TaskProgressPanel({
  task,
  expanded,
  onToggleExpanded,
  onPause,
  onResume,
  onRetry,
  retrying,
  retryError,
  onOpenLogs,
  onOpenAllLogs,
}: Props) {
  const completed = task.plan?.steps.filter((step) => step.status === 'completed').length ?? 0
  const total = task.plan?.steps.length ?? 0
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0
  const active = task.status === 'running' || task.status === 'pause_requested'
  const paused = task.status === 'paused'
  const currentStep =
    task.current_step != null && task.plan ? task.plan.steps[task.current_step] : undefined
  const validationFailed = task.stage === 'validation' && task.status === 'failed'
  const validationIssues = task.validation_result?.issues ?? []

  if (!expanded) {
    return (
      <section className="task-progress-panel collapsed" aria-label="Состояние задачи">
        <div className="task-progress-collapsed-row">
          <button type="button" className="task-progress-collapsed-main" onClick={onToggleExpanded}>
            <span className={`task-collapsed-dot ${task.status}`} aria-hidden="true" />
            <span>
              <b>{collapsedLabel(task, currentStep?.title)}</b>
              <small>{collapsedDetail(task, currentStep?.title)}</small>
            </span>
            <span className="task-progress-chevron" aria-hidden="true">
              ›
            </span>
          </button>
          {paused && (
            <button type="button" className="task-collapsed-resume" onClick={onResume}>
              Продолжить
            </button>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="task-progress-panel expanded" aria-label="Состояние задачи">
      {task.recovered && (
        <div className="task-recovery-banner" role="status">
          <span className="task-recovery-icon" aria-hidden="true">
            ↻
          </span>
          <span>
            <b>Задача восстановлена</b>
            <small>
              Продолжить с шага «{currentStep?.title ?? task.expected_action ?? task.stage}»?
            </small>
          </span>
          {paused && (
            <button type="button" className="task-link-button" onClick={onResume}>
              Продолжить
            </button>
          )}
        </div>
      )}
      <header className="task-progress-header">
        <div>
          <span className="task-eyebrow">Task mode</span>
          <h2>
            {task.stage === 'done'
              ? 'Задача завершена'
              : task.stage === 'plan_review'
                ? 'План готов'
                : validationFailed
                  ? 'Проверка не пройдена'
                  : 'План задачи'}
          </h2>
          <p>{task.expected_action ?? taskStatusLabel(task)}</p>
        </div>
        <div className={`task-status-badge ${task.status}`}>
          <i /> {taskStatusLabel(task)}
        </div>
        <button
          type="button"
          className="task-progress-collapse"
          onClick={onToggleExpanded}
          aria-label="Свернуть состояние задачи"
        >
          ‹
        </button>
      </header>
      <div className="task-stage-stepper" aria-label="Этапы задачи">
        {stages.map(([stage, label], index) => {
          const current = stageForStepper(task.stage)
          const stageIndex = stages.findIndex(([name]) => name === stage)
          const done = stageIndex < current
          return (
            <div
              className={`task-stage ${done ? 'done' : ''} ${stageIndex === current ? 'current' : ''}`}
              key={stage}
            >
              <span className="task-stage-dot">{done ? '✓' : index + 1}</span>
              <span>{label}</span>
            </div>
          )
        })}
      </div>
      {task.plan && (
        <div className="task-subtasks">
          {task.plan.steps.map((step) => (
            <TaskSubtask
              key={step.id}
              step={step}
              active={task.current_step != null && step.order === task.current_step + 1}
              call={task.llm_calls
                .slice()
                .reverse()
                .find((item) => item.step_id === step.id)}
              onOpenLogs={onOpenLogs}
            />
          ))}
        </div>
      )}
      {validationFailed && (
        <div className="task-validation-failure" role="alert">
          <div className="task-validation-failure-copy">
            <b>Почему проверка не пройдена</b>
            {validationIssues.length > 0 ? (
              <ul>
                {validationIssues.map((issue, index) => (
                  <li key={`${issue}-${index}`}>{issue}</li>
                ))}
              </ul>
            ) : (
              <p>
                {task.expected_action ??
                  'Валидатор не подтвердил выполнение всех критериев задачи.'}
              </p>
            )}
          </div>
          <button type="button" className="task-retry-button" onClick={onRetry} disabled={retrying}>
            {retrying ? 'Повторное выполнение…' : 'Повторить выполнение'}
          </button>
          {retryError && <p className="task-error-text">{retryError}</p>}
        </div>
      )}
      <div className="task-llm-call-list" aria-label="Task LLM calls">
        {task.llm_calls
          .filter((call) => call.step_id == null)
          .map((call) => (
            <div className="task-llm-call" key={call.agent_log_id}>
              <span>{callLabel(call.kind)}</span>
              <small>
                {call.provider} · {call.model} · {callStatusLabel(call.status)}
              </small>
              <b>
                {call.status === 'running' ? 'Выполняется…' : formatDuration(call.duration_seconds)}
              </b>
              <button
                type="button"
                className="task-api-link"
                onClick={() => onOpenLogs(call.agent_log_id)}
              >
                API logs
              </button>
            </div>
          ))}
      </div>
      <footer className="task-progress-footer">
        <span>{total ? `${completed} из ${total} подзадач` : 'План формируется…'}</span>
        <div className="task-progress-track">
          <i style={{ width: `${progress}%` }} />
        </div>
        <span>{progress}%</span>
        {active && (
          <button
            type="button"
            className="task-pause-button"
            onClick={onPause}
            disabled={task.status === 'pause_requested'}
          >
            <span aria-hidden="true">■</span> Приостановить
          </button>
        )}
        {paused && (
          <button type="button" className="task-pause-button resume" onClick={onResume}>
            ▶ Продолжить
          </button>
        )}
        <button type="button" className="task-api-logs-button" onClick={onOpenAllLogs}>
          API logs ({task.llm_calls.length})
        </button>
      </footer>
    </section>
  )
}

function TaskSubtask({
  step,
  active,
  call,
  onOpenLogs,
}: {
  step: TaskPlanStep
  active: boolean
  call?: TaskLlmCall
  onOpenLogs: (agentLogId: string) => void
}) {
  return (
    <article className={`task-subtask ${step.status} ${active ? 'active' : ''}`}>
      <span className="task-subtask-number">{step.order}</span>
      <div className="task-subtask-copy">
        <b>{step.title}</b>
        <small>{step.instruction}</small>
        {step.error && <p className="task-error-text">{step.error}</p>}
      </div>
      <span className="task-subtask-status">{stepStatusLabel(step.status)}</span>
      {call && (
        <>
          <span className="task-call-meta">
            {call.provider} · {call.model} · {callStatusLabel(call.status)} ·{' '}
            {call.status === 'running' ? '—' : formatDuration(call.duration_seconds)}
          </span>
          <button
            type="button"
            className="task-api-link"
            onClick={() => onOpenLogs(call.agent_log_id)}
          >
            API logs
          </button>
        </>
      )}
    </article>
  )
}

function stageForStepper(stage: TaskState['stage']) {
  if (stage === 'planning') return 0
  if (stage === 'plan_review') return 1
  if (stage === 'execution') return 2
  if (stage === 'validation' || stage === 'report') return 3
  return 4
}

function statusLabel(status: TaskState['status']) {
  return {
    running: 'Выполняется',
    pause_requested: 'Остановка…',
    paused: 'Пауза',
    waiting_for_approval: 'Ждёт утверждения',
    completed: 'Готово',
    failed: 'Ошибка',
  }[status]
}

function taskStatusLabel(task: TaskState) {
  return task.stage === 'validation' && task.status === 'failed'
    ? 'Проверка не пройдена'
    : statusLabel(task.status)
}

function collapsedLabel(task: TaskState, stepTitle?: string) {
  if (task.status === 'completed') return 'Задача завершена'
  if (task.stage === 'validation' && task.status === 'failed') return 'Проверка не пройдена'
  if (task.status === 'failed') return 'Задача завершилась с ошибкой'
  if (task.status === 'paused') return 'Задача приостановлена'
  if (task.status === 'waiting_for_approval') return 'Ожидает утверждения плана'
  if (task.status === 'pause_requested') return 'Остановка задачи…'
  return `Выполняется ${stepTitle ?? stageLabel(task.stage)}…`
}

function collapsedDetail(task: TaskState, stepTitle?: string) {
  if (task.status === 'completed') return 'Нажмите, чтобы открыть план и проверку'
  if (task.stage === 'validation' && task.status === 'failed')
    return (
      task.validation_result?.issues[0] ??
      task.expected_action ??
      'Откройте, чтобы повторить выполнение'
    )
  if (task.status === 'failed') return task.expected_action ?? 'Откройте, чтобы посмотреть ошибку'
  if (task.status === 'paused') return stepTitle ?? task.expected_action ?? 'Можно продолжить'
  if (task.status === 'waiting_for_approval') {
    return task.expected_action ?? 'Проверьте план перед выполнением'
  }
  return task.expected_action ?? stageLabel(task.stage)
}

function stageLabel(stage: TaskState['stage']) {
  return {
    planning: 'планирование',
    plan_review: 'утверждение плана',
    execution: 'текущий шаг',
    validation: 'проверка результата',
    report: 'подготовка отчёта',
    done: 'готово',
  }[stage]
}

function stepStatusLabel(status: TaskPlanStep['status']) {
  return {
    pending: 'Ожидает',
    running: 'Выполняется',
    completed: 'Выполнено',
    failed: 'Ошибка',
  }[status]
}

function callLabel(kind: string) {
  return (
    {
      task_planning: 'Planning LLM',
      task_validation: 'Validation LLM',
      task_report: 'Report LLM',
    }[kind] ?? kind
  )
}

function formatDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(1)}s`
}

function callStatusLabel(status: TaskLlmCall['status']) {
  return { running: 'Выполняется', completed: 'Готово', failed: 'Ошибка' }[status]
}
