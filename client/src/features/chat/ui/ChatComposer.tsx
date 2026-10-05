import { FormEvent, ReactNode, useEffect, useRef } from 'react'
import {
  contextUsageLabel,
  handleComposerKeyDown,
  resizeTextArea,
} from '../application/conversationUtils'
import { ContextProgress } from './chatAppComponents'

type Props = {
  message: string
  usage?: {
    prompt_tokens?: number
    cached_prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
  } | null
  contextWindow?: number | null
  modelLabel: string
  sessionAvailable: boolean
  settingsOpen: boolean
  settingsContent: ReactNode
  planApprovalContent: ReactNode
  memoryPanelOpen: boolean
  isLoading: boolean
  settingsSaving: boolean
  summaryFailed: boolean
  taskIsActive: boolean
  canPauseTask: boolean
  onMessageChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onToggleSettings: () => void
  onToggleMemory: () => void
  onPauseTask: () => void
}

export function ChatComposer({
  message,
  usage,
  contextWindow,
  modelLabel,
  sessionAvailable,
  settingsOpen,
  settingsContent,
  planApprovalContent,
  memoryPanelOpen,
  isLoading,
  settingsSaving,
  summaryFailed,
  taskIsActive,
  canPauseTask,
  onMessageChange,
  onSubmit,
  onToggleSettings,
  onToggleMemory,
  onPauseTask,
}: Props) {
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const settingsRef = useRef<HTMLDivElement>(null)

  useEffect(() => resizeTextArea(composerRef.current), [message])
  useEffect(() => {
    if (!settingsOpen) return
    const closeIfOutside = (event: MouseEvent) => {
      if (event.target instanceof Node && !settingsRef.current?.contains(event.target))
        onToggleSettings()
    }
    document.addEventListener('mousedown', closeIfOutside)
    return () => document.removeEventListener('mousedown', closeIfOutside)
  }, [settingsOpen, onToggleSettings])

  return (
    <div className="composer-area">
      {settingsOpen && <div ref={settingsRef}>{settingsContent}</div>}
      {planApprovalContent}
      <form className="composer" ref={formRef} onSubmit={onSubmit}>
        <span className="model-indicator" title={contextUsageLabel(usage, contextWindow)}>
          <span className="model-chip">{modelLabel}</span>
          {usage && <ContextProgress usage={usage} contextWindow={contextWindow} />}
        </span>
        <span className="composer-divider" />
        <button
          type="button"
          className={`tune ${settingsOpen ? 'active' : ''}`}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={onToggleSettings}
          aria-label="Request settings"
          aria-expanded={settingsOpen}
        >
          ☷
        </button>
        {sessionAvailable && (
          <button
            type="button"
            className={`memory-toggle ${memoryPanelOpen ? 'active' : ''}`}
            aria-label="Открыть память"
            aria-expanded={memoryPanelOpen}
            onClick={onToggleMemory}
          >
            <span aria-hidden="true">◈</span>
            <span className="memory-toggle-label">Память</span>
          </button>
        )}
        <textarea
          ref={composerRef}
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          onKeyDown={(event) => handleComposerKeyDown(event, formRef.current)}
          placeholder={
            summaryFailed
              ? 'Повторите суммаризацию, чтобы продолжить…'
              : 'Напишите сообщение Copia…'
          }
          rows={1}
          disabled={isLoading || settingsSaving || summaryFailed || taskIsActive}
        />
        {taskIsActive ? (
          <button
            className="send task-stop-control"
            type="button"
            disabled={!canPauseTask}
            onClick={onPauseTask}
            aria-label="Приостановить"
            title="Приостановить"
          >
            ■
          </button>
        ) : (
          <button
            className="send"
            type="submit"
            disabled={isLoading || settingsSaving || summaryFailed || !message.trim()}
            aria-label="Send"
          >
            ↑
          </button>
        )}
      </form>
      <p className="hint">Copia может допускать ошибки. Проверяйте важную информацию.</p>
    </div>
  )
}
