import { providerModels } from '../application/configDefaults'
import { ContextManagementConfig } from '../../../domain/models/agent'
import { ProviderModel } from '../../../domain/models/provider'
import { ModelsSelect, ProviderSelect, StrategySelect } from './settingsControls'

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
