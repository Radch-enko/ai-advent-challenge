import {
  SummarizationSettings,
  ModelsSelect,
  ProviderSelect,
} from '../../configuration/ui/settingsComponents'
import {
  resizeTextArea,
  supportsSamplingParameters,
} from '../../chat/application/conversationUtils'
import {
  providerModels,
  defaultContextManagement,
} from '../../configuration/application/configDefaults'
import { loadProviderModels } from '../../configuration/application/modelCatalog'
import { FormEvent, useEffect, useState } from 'react'
import { AgentConfig, ContextManagementConfig } from '../../../domain/models/agent'
import { Provider, ProviderModel } from '../../../domain/models/provider'
import { McpConnection } from '../../../domain/models/mcp'

export function Agents({
  profiles,
  mcpConnections,
  onLaunch,
  onCreate,
}: {
  profiles: Record<string, AgentConfig>
  mcpConnections: McpConnection[]
  onLaunch: (profile: string) => Promise<void>
  onCreate: (config: AgentConfig) => Promise<void>
}) {
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('Новый агент')
  const [provider, setProvider] = useState<Provider>('openai')
  const [model, setModel] = useState('gpt-5.4-mini')
  const [availableModels, setAvailableModels] = useState<ProviderModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [prompt, setPrompt] = useState('You are a helpful assistant.')
  const [maxTokens, setMaxTokens] = useState('512')
  const [temperature, setTemperature] = useState('0.7')
  const [topP, setTopP] = useState('1')
  const [contextManagement, setContextManagement] = useState<ContextManagementConfig>(() =>
    defaultContextManagement('openai', providerModels.openai),
  )
  const [summarizerModels, setSummarizerModels] = useState<ProviderModel[]>([])
  const [summarizerModelsLoading, setSummarizerModelsLoading] = useState(false)
  const [factsModels, setFactsModels] = useState<ProviderModel[]>([])
  const [factsModelsLoading, setFactsModelsLoading] = useState(false)
  const [mcpAccess, setMcpAccess] = useState<AgentConfig['mcp_access']>([])
  const summarizerProvider = contextManagement.summarizer.provider ?? provider
  const summarizerModel = contextManagement.summarizer.model ?? model
  const factsProvider = contextManagement.facts_updater.provider ?? provider
  const factsModel = contextManagement.facts_updater.model ?? model
  useEffect(() => {
    loadProviderModels(provider, setAvailableModels, setModelsLoading)
  }, [provider])
  useEffect(() => {
    loadProviderModels(summarizerProvider, setSummarizerModels, setSummarizerModelsLoading)
  }, [summarizerProvider])
  useEffect(() => {
    loadProviderModels(factsProvider, setFactsModels, setFactsModelsLoading)
  }, [factsProvider])
  const changeProvider = (nextProvider: Provider) => {
    setProvider(nextProvider)
    setModel(providerModels[nextProvider])
  }
  const create = async (event: FormEvent) => {
    event.preventDefault()
    await onCreate({
      name,
      provider,
      model,
      system_prompt: prompt,
      generation: {
        max_output_tokens: Number(maxTokens),
        temperature: Number(temperature),
        top_p: Number(topP),
      },
      context_management: contextManagement,
      mcp_access: mcpAccess,
    })
  }
  return (
    <div className="agents-screen">
      <div className="agents-title">
        <div>
          <h1>Агенты</h1>
          <p>Агент хранит независимую конфигурацию и историю в памяти текущего сервиса.</p>
        </div>
        <button onClick={() => setCreating(true)}>Создать агента</button>
      </div>
      {creating && (
        <form className="agent-form" onSubmit={(event) => void create(event)}>
          <header>
            <b>Новый агент</b>
            <button type="button" onClick={() => setCreating(false)}>
              ×
            </button>
          </header>
          <label>
            Название
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <div className="settings-grid">
            <label>
              Провайдер
              <ProviderSelect value={provider} onChange={changeProvider} />
            </label>
            <label>
              Модель
              <ModelsSelect
                value={model}
                models={availableModels}
                loading={modelsLoading}
                onChange={setModel}
              />
            </label>
          </div>
          <label>
            System prompt
            <textarea
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                resizeTextArea(e.currentTarget)
              }}
              rows={1}
            />
          </label>
          <div className="settings-grid">
            <label>
              Max output tokens
              <input
                type="number"
                min="1"
                value={maxTokens}
                onChange={(e) => setMaxTokens(e.target.value)}
              />
            </label>
            <label>
              Temperature
              <input
                type="number"
                min="0"
                max="2"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
              />
            </label>
            <label>
              Top p
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={topP}
                onChange={(e) => setTopP(e.target.value)}
              />
            </label>
          </div>
          <SummarizationSettings
            value={contextManagement}
            models={summarizerModels}
            modelsLoading={summarizerModelsLoading}
            supportsSampling={supportsSamplingParameters(summarizerProvider, summarizerModel)}
            onChange={setContextManagement}
            facts={{}}
            factsModels={factsModels}
            factsModelsLoading={factsModelsLoading}
            factsSupportsSampling={supportsSamplingParameters(factsProvider, factsModel)}
          />
          {mcpConnections.length > 0 && (
            <fieldset className="agent-mcp-settings">
              <legend>MCP tools</legend>
              <p>Каждый вызов потребует отдельного подтверждения в чате.</p>
              {mcpConnections.map((connection) => {
                const selected = mcpAccess?.find((access) => access.connection_id === connection.id)
                return (
                  <div key={connection.id}>
                    <strong>{connection.name}</strong>
                    {connection.tools.map((tool) => {
                      const checked = selected?.enabled_tools.includes(tool.name) ?? false
                      return (
                        <label key={tool.name}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) =>
                              setMcpAccess((current = []) => {
                                const existing = current.find(
                                  (item) => item.connection_id === connection.id,
                                )
                                const tools = new Set(existing?.enabled_tools ?? [])
                                if (event.target.checked) tools.add(tool.name)
                                else tools.delete(tool.name)
                                const rest = current.filter(
                                  (item) => item.connection_id !== connection.id,
                                )
                                return tools.size
                                  ? [
                                      ...rest,
                                      {
                                        connection_id: connection.id,
                                        enabled_tools: [...tools],
                                      },
                                    ]
                                  : rest
                              })
                            }
                          />{' '}
                          {tool.name}
                        </label>
                      )
                    })}
                  </div>
                )
              })}
            </fieldset>
          )}
          <button className="create-submit" type="submit">
            Создать и открыть чат
          </button>
        </form>
      )}
      <div className="agent-list">
        {Object.entries(profiles).map(([id, config]) => (
          <article key={id}>
            <div className="agent-avatar">
              {config.avatar_path ? (
                <img src={config.avatar_path} alt="" />
              ) : (
                config.name.slice(0, 1)
              )}
            </div>
            <div className="agent-card-content">
              <b>{config.name}</b>
              <p>{config.description ?? 'Описание пока не добавлено.'}</p>
              <span>
                {config.provider} · {config.model}
              </span>
            </div>
            <button onClick={() => void onLaunch(id)}>Запустить чат</button>
          </article>
        ))}
      </div>
    </div>
  )
}
