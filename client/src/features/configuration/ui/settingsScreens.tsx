import { ReactNode } from 'react'
import { resizeTextArea } from '../../chat/application/conversationUtils'
import { ContextManagementConfig } from '../../../domain/models/agent'
import { Provider, ProviderModel } from '../../../domain/models/provider'
import { RagSettings } from '../../../domain/models/ragSettings'
import { SummarizationSettings, StrategySettings } from './contextSettings'
import {
  MemoryLayerStatus,
  ModelsSelect,
  ProviderSelect,
  RagModeToggle,
  RagSettingsControls,
  TaskModeToggle,
} from './settingsControls'

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
  ragEnabled,
  ragModeDisabled,
  onRagMode,
  ragSettings,
  onRagSettingsChange,
  onRagSettingsSave,
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
  ragEnabled: boolean
  ragModeDisabled: boolean
  onRagMode: (enabled: boolean) => void
  ragSettings: RagSettings
  onRagSettingsChange: (settings: RagSettings) => void
  onRagSettingsSave: (settings: RagSettings) => void
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
      <RagModeToggle enabled={ragEnabled} disabled={ragModeDisabled} onChange={onRagMode} />
      {ragEnabled && (
        <RagSettingsControls
          value={ragSettings}
          disabled={ragModeDisabled}
          onChange={onRagSettingsChange}
          onSave={onRagSettingsSave}
        />
      )}
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
  ragEnabled: boolean
  ragModeDisabled: boolean
  onRagMode: (enabled: boolean) => void
  ragSettings: RagSettings
  onRagSettingsChange: (settings: RagSettings) => void
  onRagSettingsSave: (settings: RagSettings) => void
  error?: string | null
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
      <RagModeToggle
        enabled={props.ragEnabled}
        disabled={props.ragModeDisabled}
        onChange={props.onRagMode}
      />
      {props.ragEnabled && (
        <RagSettingsControls
          value={props.ragSettings}
          disabled={props.ragModeDisabled}
          onChange={props.onRagSettingsChange}
          onSave={props.onRagSettingsSave}
        />
      )}
      {props.error && <p className="model-note">{props.error}</p>}
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
        Системный промпт
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
