import { TokenUsageSummary } from '../../chat/ui/chatAppComponents'
import { resizeTextArea, useOutsideClose } from '../../chat/application/conversationUtils'
import { providerModels } from '../application/configDefaults'
import { ReactNode, useState } from 'react'
import { ContextManagementConfig, ContextStrategy } from '../../../domain/models/agent'
import { Provider, ProviderModel } from '../../../domain/models/provider'
import { FactsUpdateEvent, SummarizationEvent } from '../../../domain/models/chat'

export function ProfileSessionSettings({
  profileControl,
  value,
  facts,
  provider,
  longTermMemoryEnabled,
  saving,
  error,
  onChange,
  onLongTermMemoryEnabled,
  taskModeEnabled,
  taskModeDisabled,
  onTaskMode,
}: {
  profileControl: ReactNode
  value: ContextManagementConfig
  facts: Record<string, string>
  provider: Provider
  longTermMemoryEnabled: boolean
  saving: boolean
  error: string | null
  onChange: (value: ContextManagementConfig) => Promise<void>
  onLongTermMemoryEnabled: (enabled: boolean) => Promise<void>
  taskModeEnabled: boolean
  taskModeDisabled: boolean
  onTaskMode: (enabled: boolean) => void
}) {
  return (
    <section className="settings-popover">
      <header>
        <b>Настройки диалога</b>
        <span>
          {provider} · long-term memory {longTermMemoryEnabled ? 'активна' : 'выключена'}
        </span>
      </header>
      <div className="dialog-profile-control">{profileControl}</div>
      <MemoryLayerStatus longTermState={longTermMemoryEnabled ? 'enabled' : 'disabled'} />
      <TaskModeToggle enabled={taskModeEnabled} disabled={taskModeDisabled} onChange={onTaskMode} />
      <label className="toggle-row">
        <span>
          <b>Long-term memory</b>
          <small>
            При включении память профиля отправляется с запросами провайдеру {provider}. Только для
            этого чата; записи профиля не изменяются.
          </small>
        </span>
        <input
          type="checkbox"
          checked={longTermMemoryEnabled}
          disabled={saving}
          onChange={(event) => void onLongTermMemoryEnabled(event.target.checked)}
        />
      </label>
      <StrategySettings
        value={value}
        facts={facts}
        disabled={saving}
        onChange={(next) => void onChange(next)}
      />
      {error && <p className="model-note">{error}</p>}
    </section>
  )
}

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

export type SettingsProps = {
  profileControl: ReactNode
  provider: Provider
  model: string
  models: ProviderModel[]
  modelsLoading: boolean
  systemPrompt: string
  maxTokens: string
  temperature: string
  topP: string
  structuredOutput: boolean
  schema: string
  supportsSampling: boolean
  onProvider: (provider: Provider) => void
  onModel: (value: string) => void
  onSystemPrompt: (value: string) => void
  onMaxTokens: (value: string) => void
  onTemperature: (value: string) => void
  onTopP: (value: string) => void
  onStructuredOutput: (value: boolean) => void
  onSchema: (value: string) => void
  contextManagement: ContextManagementConfig
  summarizerModels: ProviderModel[]
  summarizerModelsLoading: boolean
  summarizerSupportsSampling: boolean
  facts: Record<string, string>
  factsModels: ProviderModel[]
  factsModelsLoading: boolean
  factsSupportsSampling: boolean
  onContextManagement: (value: ContextManagementConfig) => void
  taskModeEnabled: boolean
  taskModeDisabled: boolean
  onTaskMode: (enabled: boolean) => void
}

export function Settings(props: SettingsProps) {
  return (
    <section className="settings-popover">
      <header>
        <b>Настройки запроса</b>
        <span>Конфигурация применяется к обычному чату</span>
      </header>
      <div className="dialog-profile-control">{props.profileControl}</div>
      <MemoryLayerStatus longTermState="unavailable" />
      <TaskModeToggle
        enabled={props.taskModeEnabled}
        disabled={props.taskModeDisabled}
        onChange={props.onTaskMode}
      />
      <p className="model-note">Long-term memory недоступна без профиля.</p>
      <div className="settings-grid">
        <label>
          Провайдер
          <ProviderSelect value={props.provider} onChange={props.onProvider} />
        </label>
        <label>
          Модель
          <ModelsSelect
            value={props.model}
            models={props.models}
            loading={props.modelsLoading}
            onChange={props.onModel}
          />
        </label>
      </div>
      <label>
        System prompt
        <textarea
          value={props.systemPrompt}
          onChange={(e) => {
            props.onSystemPrompt(e.target.value)
            resizeTextArea(e.currentTarget)
          }}
          rows={1}
        />
      </label>
      <label>
        Max output tokens
        <input
          type="number"
          min="1"
          value={props.maxTokens}
          onChange={(e) => props.onMaxTokens(e.target.value)}
        />
      </label>
      {props.supportsSampling ? (
        <div className="settings-grid">
          <label>
            Temperature
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={props.temperature}
              onChange={(e) => props.onTemperature(e.target.value)}
            />
          </label>
          <label>
            Top p
            <input
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value={props.topP}
              onChange={(e) => props.onTopP(e.target.value)}
            />
          </label>
        </div>
      ) : (
        <p className="model-note">Для этой модели параметры sampling задаёт провайдер.</p>
      )}
      <label className="toggle-row">
        <span>
          <b>Structured output</b>
          <small>Ответ строго по JSON Schema</small>
        </span>
        <input
          type="checkbox"
          checked={props.structuredOutput}
          onChange={(e) => props.onStructuredOutput(e.target.checked)}
        />
      </label>
      {props.structuredOutput && (
        <label>
          JSON Schema
          <textarea
            className="code-input"
            value={props.schema}
            onChange={(e) => props.onSchema(e.target.value)}
            rows={5}
          />
        </label>
      )}
      <SummarizationSettings
        value={props.contextManagement}
        models={props.summarizerModels}
        modelsLoading={props.summarizerModelsLoading}
        supportsSampling={props.summarizerSupportsSampling}
        onChange={props.onContextManagement}
        facts={props.facts}
        factsModels={props.factsModels}
        factsModelsLoading={props.factsModelsLoading}
        factsSupportsSampling={props.factsSupportsSampling}
      />
    </section>
  )
}

export function SummarizationSettings({
  value,
  models,
  modelsLoading,
  supportsSampling,
  onChange,
  facts,
  factsModels,
  factsModelsLoading,
  factsSupportsSampling,
}: {
  value: ContextManagementConfig
  models: ProviderModel[]
  modelsLoading: boolean
  supportsSampling: boolean
  onChange: (value: ContextManagementConfig) => void
  facts: Record<string, string>
  factsModels: ProviderModel[]
  factsModelsLoading: boolean
  factsSupportsSampling: boolean
}) {
  const summarizer = value.summarizer
  const provider = summarizer.provider ?? 'openai'
  const updateSummarizer = (next: Partial<ContextManagementConfig['summarizer']>) =>
    onChange({
      ...value,
      summarizer: { ...summarizer, ...next },
    })
  const updateGeneration = (next: Partial<ContextManagementConfig['summarizer']['generation']>) =>
    updateSummarizer({
      generation: { ...summarizer.generation, ...next },
    })

  return (
    <div className="summarization-settings">
      <StrategySettings value={value} facts={facts} onChange={onChange} />
      {value.strategy === 'summary' && (
        <>
          <div className="settings-grid">
            <label>
              Последние пары<small className="field-help">5 = 5 запросов + 5 ответов</small>
              <input
                type="number"
                min="1"
                value={value.recent_exchange_limit}
                onChange={(event) =>
                  onChange({ ...value, recent_exchange_limit: Number(event.target.value) })
                }
              />
            </label>
            <label>
              Размер пачки, пар<small className="field-help">5 = суммаризировать 5 пар</small>
              <input
                type="number"
                min="1"
                value={value.summary_batch_exchange_count}
                onChange={(event) =>
                  onChange({ ...value, summary_batch_exchange_count: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <div className="settings-grid">
            <label>
              Провайдер summary
              <ProviderSelect
                value={provider}
                onChange={(nextProvider) =>
                  updateSummarizer({ provider: nextProvider, model: providerModels[nextProvider] })
                }
              />
            </label>
            <label>
              Модель summary
              <ModelsSelect
                value={summarizer.model ?? providerModels[provider]}
                models={models}
                loading={modelsLoading}
                onChange={(model) => updateSummarizer({ model })}
              />
            </label>
          </div>
          <label>
            Summary prompt
            <textarea
              className="summary-prompt"
              value={summarizer.prompt}
              onChange={(event) => updateSummarizer({ prompt: event.target.value })}
              rows={6}
            />
          </label>
          <label>
            Summary max output tokens
            <input
              type="number"
              min="1"
              value={summarizer.generation.max_output_tokens ?? 512}
              onChange={(event) =>
                updateGeneration({ max_output_tokens: Number(event.target.value) })
              }
            />
          </label>
          {supportsSampling ? (
            <div className="settings-grid">
              <label>
                Summary temperature
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={summarizer.generation.temperature ?? 0.2}
                  onChange={(event) =>
                    updateGeneration({ temperature: Number(event.target.value) })
                  }
                />
              </label>
              <label>
                Summary top p
                <input
                  type="number"
                  min="0.01"
                  max="1"
                  step="0.01"
                  value={summarizer.generation.top_p ?? 1}
                  onChange={(event) => updateGeneration({ top_p: Number(event.target.value) })}
                />
              </label>
            </div>
          ) : (
            <p className="model-note">
              Для этой summary-модели параметры sampling задаёт провайдер.
            </p>
          )}
        </>
      )}
      {value.strategy === 'sticky_facts' && (
        <FactsUpdaterSettings
          value={value}
          models={factsModels}
          modelsLoading={factsModelsLoading}
          supportsSampling={factsSupportsSampling}
          onChange={onChange}
        />
      )}
    </div>
  )
}

export function SummarizationIndicator({
  event,
  retrying,
  onRetry,
}: {
  event: SummarizationEvent
  retrying: boolean
  onRetry: () => void
}) {
  const failed = event.status === 'failed'
  return (
    <div className={`summarization-event ${event.status}`}>
      <span className="summary-event-icon">{failed ? '!' : '✓'}</span>
      <div>
        <b>
          {failed
            ? 'Не удалось сжать контекст'
            : `Сжато пар: ${event.message_count / 2} (${event.message_count} сообщений)`}
        </b>
        <span>{failed ? event.error : `${event.provider} · ${event.model}`}</span>
      </div>
      {event.usage && <TokenUsageSummary usage={event.usage} />}
      {failed && (
        <button className="summary-retry" disabled={retrying} onClick={onRetry}>
          {retrying ? 'Повторяем…' : 'Retry'}
        </button>
      )}
    </div>
  )
}

export function FactsUpdaterSettings({
  value,
  models,
  modelsLoading,
  supportsSampling,
  onChange,
}: {
  value: ContextManagementConfig
  models: ProviderModel[]
  modelsLoading: boolean
  supportsSampling: boolean
  onChange: (value: ContextManagementConfig) => void
}) {
  const updater = value.facts_updater
  const provider = updater.provider ?? 'openai'
  const updateUpdater = (next: Partial<ContextManagementConfig['facts_updater']>) =>
    onChange({
      ...value,
      facts_updater: { ...updater, ...next },
    })
  const updateGeneration = (
    next: Partial<ContextManagementConfig['facts_updater']['generation']>,
  ) =>
    updateUpdater({
      generation: { ...updater.generation, ...next },
    })
  return (
    <div className="facts-updater-settings">
      <div className="settings-grid">
        <label>
          Провайдер facts
          <ProviderSelect
            value={provider}
            onChange={(nextProvider) =>
              updateUpdater({ provider: nextProvider, model: providerModels[nextProvider] })
            }
          />
        </label>
        <label>
          Модель facts
          <ModelsSelect
            value={updater.model ?? providerModels[provider]}
            models={models}
            loading={modelsLoading}
            onChange={(model) => updateUpdater({ model })}
          />
        </label>
      </div>
      <label>
        Facts prompt
        <textarea
          className="summary-prompt"
          value={updater.prompt}
          onChange={(event) => updateUpdater({ prompt: event.target.value })}
          rows={6}
        />
      </label>
      <label>
        Facts max output tokens
        <input
          type="number"
          min="1"
          value={updater.generation.max_output_tokens ?? 512}
          onChange={(event) => updateGeneration({ max_output_tokens: Number(event.target.value) })}
        />
      </label>
      {supportsSampling ? (
        <div className="settings-grid">
          <label>
            Facts temperature
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={updater.generation.temperature ?? 0}
              onChange={(event) => updateGeneration({ temperature: Number(event.target.value) })}
            />
          </label>
          <label>
            Facts top p
            <input
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value={updater.generation.top_p ?? 1}
              onChange={(event) => updateGeneration({ top_p: Number(event.target.value) })}
            />
          </label>
        </div>
      ) : (
        <p className="model-note">Для этой facts-модели параметры sampling задаёт провайдер.</p>
      )}
    </div>
  )
}

export function FactsPanel({ facts }: { facts: Record<string, string> }) {
  const entries = Object.entries(facts)
  return (
    <section className="facts-panel">
      <header>
        <b>Facts · {entries.length}</b>
      </header>
      {entries.length ? (
        entries.map(([key, value]) => (
          <div key={key}>
            <code>{key}</code>
            <span>{value}</span>
          </div>
        ))
      ) : (
        <p>Память пока пуста</p>
      )}
    </section>
  )
}

export function FactsUpdateIndicator({ event }: { event: FactsUpdateEvent }) {
  const failed = event.status === 'failed'
  const changed = Object.keys(event.updates).length
  return (
    <div className={`summarization-event facts-event ${event.status}`}>
      <span className="summary-event-icon">{failed ? '!' : '✓'}</span>
      <div>
        <b>
          {failed
            ? 'Не удалось обновить facts'
            : `Facts обновлены: ${changed}, удалены: ${event.deletions.length}`}
        </b>
        <span>{failed ? event.error : `${event.provider} · ${event.model}`}</span>
      </div>
      {event.usage && <TokenUsageSummary usage={event.usage} />}
    </div>
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
  const labels: Record<Provider, string> = { openai: 'OpenAI', gigachat: 'GigaChat' }
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

export function StrategySettings({
  value,
  facts = {},
  disabled = false,
  onChange,
}: {
  value: ContextManagementConfig
  facts?: Record<string, string>
  disabled?: boolean
  onChange: (value: ContextManagementConfig) => void
}) {
  return (
    <div className="strategy-settings">
      <label>
        Стратегия контекста
        <StrategySelect
          value={value.strategy}
          disabled={disabled}
          onChange={(strategy) => onChange({ ...value, enabled: true, strategy })}
        />
      </label>
      {(value.strategy === 'sliding_window' || value.strategy === 'sticky_facts') && (
        <label>
          Размер окна
          <small className="field-help">
            Количество последних сообщений, system prompt не учитывается
          </small>
          <input
            type="number"
            min="1"
            disabled={disabled}
            value={value.recent_message_limit}
            onChange={(event) =>
              onChange({ ...value, recent_message_limit: Number(event.target.value) })
            }
          />
        </label>
      )}
      {value.strategy === 'sticky_facts' && <FactsPanel facts={facts} />}
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
