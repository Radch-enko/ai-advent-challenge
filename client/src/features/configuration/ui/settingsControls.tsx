import { useState } from 'react'
import { useOutsideClose } from '../../chat/application/conversationUtils'
import { ContextStrategy } from '../../../domain/models/agent'
import { Provider, ProviderModel } from '../../../domain/models/provider'
import { RagSettings } from '../../../domain/models/ragSettings'

export function TaskModeToggle({
  enabled,
  disabled,
  onChange,
}: {
  enabled: boolean
  disabled: boolean
  onChange: (enabled: boolean) => void
}) {
  return (
    <label className="toggle-row task-mode-toggle">
      <span>
        <b>Task mode</b>
        <small>
          Планирует задачу, выполняет подзадачи по очереди и проверяет итоговый результат.
        </small>
      </span>
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  )
}

export function RagModeToggle({
  enabled,
  disabled,
  onChange,
}: {
  enabled: boolean
  disabled: boolean
  onChange: (enabled: boolean) => void
}) {
  return (
    <label className="toggle-row rag-mode-toggle">
      <span>
        <b>RAG enabled</b>
        <small>
          Ищет релевантные фрагменты в проиндексированных документах и добавляет их к запросу.
        </small>
      </span>
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  )
}

export function RagSettingsControls({
  value,
  disabled,
  onChange,
  onSave,
}: {
  value: RagSettings
  disabled: boolean
  onChange: (settings: RagSettings) => void
  onSave: (settings: RagSettings) => void
}) {
  function update(next: Partial<RagSettings>) {
    onChange({ ...value, ...next })
  }

  return (
    <section className="rag-settings" aria-label="Настройки поиска RAG">
      <div className="settings-grid">
        <label>
          Top-K до фильтрации
          <input
            type="number"
            min="1"
            max="100"
            step="1"
            value={value.top_k_before}
            disabled={disabled}
            onChange={(event) => {
              const entered = event.currentTarget.valueAsNumber
              if (!Number.isFinite(entered)) return
              const next = Math.max(1, Math.min(100, Math.trunc(entered)))
              update({ top_k_before: next, top_k_after: Math.min(value.top_k_after, next) })
            }}
            onBlur={() => onSave(value)}
          />
        </label>
        <label>
          Top-K после фильтрации
          <input
            type="number"
            min="1"
            max={value.top_k_before}
            step="1"
            value={value.top_k_after}
            disabled={disabled}
            onChange={(event) => {
              const entered = event.currentTarget.valueAsNumber
              if (!Number.isFinite(entered)) return
              const next = Math.max(1, Math.min(value.top_k_before, Math.trunc(entered)))
              update({ top_k_after: next })
            }}
            onBlur={() => onSave(value)}
          />
        </label>
      </div>
      <label>
        Порог similarity ({value.similarity_threshold.toFixed(2)})
        <input
          type="range"
          min="-1"
          max="1"
          step="0.01"
          value={value.similarity_threshold}
          disabled={disabled}
          onChange={(event) => update({ similarity_threshold: Number(event.currentTarget.value) })}
          onBlur={() => onSave(value)}
        />
      </label>
      <label className="toggle-row">
        <span>
          <b>Query rewrite</b>
          <small>Уточняет поисковый запрос по контексту диалога.</small>
        </span>
        <input
          type="checkbox"
          checked={value.query_rewrite_enabled}
          disabled={disabled}
          onChange={(event) => {
            const next = { ...value, query_rewrite_enabled: event.currentTarget.checked }
            onChange(next)
            onSave(next)
          }}
        />
      </label>
      <label className="toggle-row">
        <span>
          <b>Reranker</b>
          <small>Выбирает один лучший чанк из прошедших фильтр.</small>
        </span>
        <input
          type="checkbox"
          checked={value.reranker_enabled}
          disabled={disabled}
          onChange={(event) => {
            const next = { ...value, reranker_enabled: event.currentTarget.checked }
            onChange(next)
            onSave(next)
          }}
        />
      </label>
    </section>
  )
}

export function MemoryLayerStatus({
  longTermState,
}: {
  longTermState: 'enabled' | 'disabled' | 'unavailable'
}) {
  const workingActive = true
  return (
    <section className="memory-layer-status" aria-label="Статус слоёв памяти">
      <span>Short-term dialogue · active</span>
      <span>Working context · {workingActive ? 'active' : 'inactive'}</span>
      <span>Long-term memory · {longTermState}</span>
    </section>
  )
}

export function ModelsSelect({
  value,
  models,
  loading,
  onChange,
}: {
  value: string
  models: ProviderModel[]
  loading: boolean
  onChange: (value: string) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useOutsideClose(isOpen, () => setIsOpen(false))
  return (
    <div className="react-select" ref={ref}>
      <button
        type="button"
        className="select-trigger"
        disabled={loading}
        onClick={() => setIsOpen(!isOpen)}
      >
        {loading ? 'Загрузка моделей…' : value}
        <span>⌄</span>
      </button>
      {isOpen && (
        <div className="select-menu">
          {models.length ? (
            models.map((model) => (
              <button
                type="button"
                key={model.id}
                onClick={() => {
                  onChange(model.id)
                  setIsOpen(false)
                }}
              >
                {model.id}
              </button>
            ))
          ) : (
            <span>Не удалось загрузить модели</span>
          )}
        </div>
      )}
    </div>
  )
}

export function ProviderSelect({
  value,
  onChange,
}: {
  value: Provider
  onChange: (provider: Provider) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useOutsideClose(isOpen, () => setIsOpen(false))
  const labels: Record<Provider, string> = {
    openai: 'OpenAI',
    gigachat: 'GigaChat',
    ollama: 'Ollama',
  }
  return (
    <div className="react-select" ref={ref}>
      <button
        type="button"
        className="select-trigger"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        {labels[value]}
        <span>⌄</span>
      </button>
      {isOpen && (
        <div className="select-menu">
          {(Object.keys(labels) as Provider[]).map((option) => (
            <button
              type="button"
              key={option}
              className={option === value ? 'selected' : ''}
              onClick={() => {
                onChange(option)
                setIsOpen(false)
              }}
            >
              {labels[option]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function StrategySelect({
  value,
  disabled,
  onChange,
}: {
  value: ContextStrategy
  disabled: boolean
  onChange: (value: ContextStrategy) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useOutsideClose(isOpen, () => setIsOpen(false))
  const labels: Record<ContextStrategy, string> = {
    sliding_window: 'Sliding Window',
    sticky_facts: 'Sticky Facts',
    branching: 'Branching',
    summary: 'Summary',
  }
  return (
    <div className="react-select" ref={ref}>
      <button
        type="button"
        className="select-trigger"
        disabled={disabled}
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        {labels[value]}
        <span>⌄</span>
      </button>
      {isOpen && (
        <div className="select-menu">
          {(Object.keys(labels) as ContextStrategy[]).map((option) => (
            <button
              type="button"
              key={option}
              className={option === value ? 'selected' : ''}
              onClick={() => {
                onChange(option)
                setIsOpen(false)
              }}
            >
              {labels[option]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
