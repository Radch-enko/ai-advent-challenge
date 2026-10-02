import { Fragment } from 'react'
import { ContextManagementConfig } from '../../../domain/models/agent'
import { ChatMessage, FactsUpdateEvent, SummarizationEvent } from '../../../domain/models/chat'
import { ChatSession } from '../../../domain/models/session'
import { McpApproval } from '../../../domain/models/mcp'
import { TaskState } from '../../../domain/models/task'
import { ExecutionSummary } from './ExecutionSummary'
import { Markdown } from './chatAppComponents'
import {
  FactsUpdateIndicator,
  SummarizationIndicator,
} from '../../configuration/ui/settingsComponents'
import { currentTaskLoadingStep } from '../../tasks/application/taskSelectors'
import { TaskSubtaskLoadingMessage } from '../../tasks/ui/taskLoadingComponents'
import { TaskProgressPanel } from '../../tasks/ui/TaskProgressPanel'

type Props = {
  messages: ChatMessage[]
  activeSession: ChatSession | null
  sessionTasks: TaskState[]
  tasksById: Map<string, TaskState>
  activeTask: TaskState | undefined
  lastTaskSubtaskMessageIndexes: Map<string, number>
  expandedTaskIds: Record<string, boolean>
  expandedTaskMessageKeys: Record<string, boolean>
  taskModeEnabled: boolean
  taskRetryingId: string | null
  taskRetryError: { taskId: string; message: string } | null
  contextWindowStart: number | null
  contextManagement: ContextManagementConfig
  summarizationEvents: SummarizationEvent[]
  factsEvents: FactsUpdateEvent[]
  isLoading: boolean
  isSummarizing: boolean
  failedSummarization: SummarizationEvent | undefined
  forkError: string | null
  forkingMessageIndex: number | null
  mcpApproval: McpApproval | null
  runningMcpTool: string | null
  onToggleTaskMessage: (key: string) => void
  onToggleTask: (taskId: string) => void
  onPauseTask: () => void
  onResumeTask: () => void
  onRetryTask: (task: TaskState) => void
  onForkMessage: (messageIndex: number) => void
  onRetrySummarization: () => void
  onRespondToMcpApproval: (approval: McpApproval, decision: 'approve' | 'reject') => void
}

export function ChatTranscript({
  messages,
  activeSession,
  sessionTasks,
  tasksById,
  activeTask,
  lastTaskSubtaskMessageIndexes,
  expandedTaskIds,
  expandedTaskMessageKeys,
  taskModeEnabled,
  taskRetryingId,
  taskRetryError,
  contextWindowStart,
  contextManagement,
  summarizationEvents,
  factsEvents,
  isLoading,
  isSummarizing,
  failedSummarization,
  forkError,
  forkingMessageIndex,
  mcpApproval,
  runningMcpTool,
  onToggleTaskMessage,
  onToggleTask,
  onPauseTask,
  onResumeTask,
  onRetryTask,
  onForkMessage,
  onRetrySummarization,
  onRespondToMcpApproval,
}: Props) {
  const pendingApproval = mcpApproval ?? activeTask?.mcp_approval
  const activeTool = runningMcpTool ?? activeTask?.mcp_running_tool

  return (
    <div className="messages-scroll" aria-live="polite">
      <div className="message-list">
        {messages.map((entry, index) => {
          const task = entry.taskId
            ? tasksById.get(entry.taskId)
            : entry.role === 'user'
              ? sessionTasks.find((item) => item.original_instruction === entry.content)
              : undefined
          const step = task?.plan?.steps.find((item) => item.id === entry.taskStepId)
          const taskExpanded = task ? expandedTaskIds[task.id] === true : false
          const isCompletionReport = task?.completion_report === entry.content
          const isSubtaskMessage =
            entry.role === 'assistant' && task != null && step != null && entry.taskStepId != null
          const subtaskMessageKey = isSubtaskMessage ? `${task.id}:${step.id}` : null
          const subtaskExpanded =
            subtaskMessageKey != null && expandedTaskMessageKeys[subtaskMessageKey] === true
          const isTaskPanelAnchor =
            task != null &&
            (lastTaskSubtaskMessageIndexes.has(task.id)
              ? entry.taskId === task.id &&
                entry.taskStepId != null &&
                lastTaskSubtaskMessageIndexes.get(task.id) === index
              : entry.role === 'user' && (entry.taskId === task.id || entry.taskId == null))
          const loadingStep = task && isTaskPanelAnchor ? currentTaskLoadingStep(task) : undefined
          const loadingMessageKey = loadingStep && task ? `${task.id}:${loadingStep.id}` : null
          const loadingExpanded =
            loadingMessageKey != null && expandedTaskMessageKeys[loadingMessageKey] === true
          const loadingStepHasMessage =
            loadingStep != null &&
            task != null &&
            messages.some((item) => item.taskId === task.id && item.taskStepId === loadingStep.id)
          const contextSources = entry.sources?.filter(
            (source) => source.selected_for_context !== false,
          )

          return (
            <Fragment key={entry.id}>
              {contextWindowStart != null &&
                entry.transcriptIndex === contextWindowStart &&
                contextWindowStart > 0 && (
                  <div className="context-window-boundary">
                    <span>
                      {contextManagement.strategy === 'sticky_facts'
                        ? 'Sticky Facts'
                        : 'Sliding Window'}{' '}
                      · последние {contextManagement.recent_message_limit} сообщений
                    </span>
                  </div>
                )}
              <article className={`message ${entry.role}`}>
                {entry.role !== 'user' && (
                  <span className="avatar">
                    {entry.role === 'error' ? (
                      '!'
                    ) : activeSession?.config.avatar_path ? (
                      <img src={activeSession.config.avatar_path} alt={activeSession.config.name} />
                    ) : (
                      '◇'
                    )}
                  </span>
                )}
                <div className="message-body">
                  {isSubtaskMessage && !subtaskExpanded ? (
                    <button
                      type="button"
                      className="task-subtask-message-collapsed"
                      aria-expanded={false}
                      onClick={() => onToggleTaskMessage(subtaskMessageKey!)}
                    >
                      <span className="task-subtask-message-dot completed" aria-hidden="true">
                        ✓
                      </span>
                      <span>
                        <b>{step.title}</b>
                        <small>Подзадача {step.order} · Выполнено</small>
                      </span>
                      <span className="task-subtask-message-chevron" aria-hidden="true">
                        ›
                      </span>
                    </button>
                  ) : (
                    <div
                      className={
                        isCompletionReport ? 'markdown completion-report-card' : 'markdown'
                      }
                    >
                      {isSubtaskMessage && (
                        <button
                          type="button"
                          className="task-subtask-message-expanded-toggle"
                          aria-expanded={true}
                          onClick={() => onToggleTaskMessage(subtaskMessageKey!)}
                        >
                          <span>
                            Подзадача {step.order}: {step.title}
                          </span>
                          <span aria-hidden="true">⌄</span>
                        </button>
                      )}
                      <Markdown content={entry.content} />
                    </div>
                  )}
                  {entry.role !== 'user' && contextSources && contextSources.length > 0 && (
                    <section className="retrieved-sources" aria-label="Источники RAG">
                      <b>Источники</b>
                      <ul>
                        {contextSources.map((source) => (
                          <li key={source.chunk_id}>
                            <span>{source.title}</span>
                            {source.section && <small>{source.section}</small>}
                            <small>{source.source}</small>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {entry.role !== 'user' && (
                    <ExecutionSummary
                      key={`${activeSession?.id ?? 'session'}-${entry.id}`}
                      provider={entry.provider}
                      model={entry.model}
                      durationSeconds={entry.durationSeconds}
                      executionStatus={entry.executionStatus}
                      executionError={entry.executionError}
                      usage={entry.usage}
                      memoryEvents={entry.memoryEvents}
                      sources={contextSources}
                    />
                  )}
                  {(entry.timestamp ||
                    (contextManagement.strategy === 'branching' &&
                      activeSession &&
                      entry.transcriptIndex != null)) && (
                    <footer>
                      {entry.timestamp && <span>{entry.timestamp}</span>}
                      {contextManagement.strategy === 'branching' &&
                        activeSession &&
                        entry.transcriptIndex != null && (
                          <button
                            type="button"
                            className="fork-message"
                            aria-label="Создать ветку с этого сообщения"
                            title="Создать ветку с этого сообщения"
                            disabled={isLoading || forkingMessageIndex != null}
                            onClick={() => onForkMessage(entry.transcriptIndex!)}
                          >
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                              <path d="M6 3v7a4 4 0 0 0 4 4h4m0 0-3-3m3 3-3 3M6 10h5a4 4 0 0 0 4-4V3m0 0-3 3m3-3 3 3" />
                            </svg>
                          </button>
                        )}
                    </footer>
                  )}
                </div>
              </article>
              {isTaskPanelAnchor && task && taskModeEnabled && (
                <>
                  {loadingStep && !loadingStepHasMessage && (
                    <TaskSubtaskLoadingMessage
                      step={loadingStep}
                      expanded={loadingExpanded}
                      onToggle={() => onToggleTaskMessage(loadingMessageKey!)}
                    />
                  )}
                  <TaskProgressPanel
                    task={task}
                    expanded={taskExpanded}
                    onToggleExpanded={() => onToggleTask(task.id)}
                    onPause={onPauseTask}
                    onResume={onResumeTask}
                    onRetry={() => onRetryTask(task)}
                    retrying={taskRetryingId === task.id}
                    retryError={taskRetryError?.taskId === task.id ? taskRetryError.message : null}
                  />
                </>
              )}
              {entry.transcriptIndex != null &&
                summarizationEvents
                  .filter((event) => event.after_message_index === entry.transcriptIndex)
                  .map((event) => (
                    <SummarizationIndicator
                      key={event.id}
                      event={event}
                      retrying={isLoading && event.status === 'failed'}
                      onRetry={onRetrySummarization}
                    />
                  ))}
              {entry.transcriptIndex != null &&
                factsEvents
                  .filter((event) => event.after_message_index === entry.transcriptIndex)
                  .map((event) => <FactsUpdateIndicator key={event.id} event={event} />)}
            </Fragment>
          )
        })}
        {forkError && <div className="fork-error">{forkError}</div>}
        {isSummarizing && !failedSummarization && (
          <div className="summarization-event in-progress">
            <span className="summary-event-icon">↻</span>
            <div>
              <b>Сжимаем контекст…</b>
              <span>Основной ответ продолжится автоматически</span>
            </div>
          </div>
        )}
        {pendingApproval && (
          <article className="message assistant mcp-approval-card">
            <span className="avatar">◇</span>
            <div className="message-body">
              <strong>Подтвердите {pendingApproval.tool_name}</strong>
              <p>Server: {pendingApproval.connection_name}</p>
              <pre>{JSON.stringify(pendingApproval.arguments, null, 2)}</pre>
              <div className="mcp-approval-actions">
                <button
                  type="button"
                  className="mcp-action-button mcp-action-primary"
                  onClick={() => onRespondToMcpApproval(pendingApproval, 'approve')}
                >
                  Разрешить
                </button>
                <button
                  type="button"
                  className="mcp-action-button mcp-action-danger"
                  onClick={() => onRespondToMcpApproval(pendingApproval, 'reject')}
                >
                  Отклонить
                </button>
              </div>
            </div>
          </article>
        )}
        {activeTool && (
          <article className="message assistant loading">
            <span className="avatar">◇</span>
            <div className="message-body">
              <p>Выполняю {activeTool}</p>
            </div>
          </article>
        )}
        {isLoading && !isSummarizing && !pendingApproval && !activeTool && (
          <article className="message assistant loading">
            <span className="avatar">
              {activeSession?.config.avatar_path ? (
                <img src={activeSession.config.avatar_path} alt={activeSession.config.name} />
              ) : (
                '◇'
              )}
            </span>
            <div className="message-body">
              <p>
                <i />
                <i />
                <i />
              </p>
              <footer>Loading…</footer>
            </div>
          </article>
        )}
      </div>
    </div>
  )
}
