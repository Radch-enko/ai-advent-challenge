import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRequestError, ChatSession, ChatSessionSummary, createSession, createSessionFromProfile, deleteSession, getModels, getProfiles, getSession, getSessions, sendSessionMessageWithMeta } from './data/api/copiaApi'
import { AgentConfig } from './domain/models/agent'
import { Provider, ProviderModel } from './domain/models/provider'
import { ChatMessage, RequestLog, TokenUsage } from './domain/models/chat'
import { RequestLogs } from './ui/components/RequestLogs'

const providerModels: Record<Provider, string> = {
  openai: 'gpt-5.4-mini',
  gigachat: 'GigaChat',
}

const starterMessages: ChatMessage[] = []

export function App() {
  const [mode, setMode] = useState<'chat' | 'agents'>('chat')
  const [provider, setProvider] = useState<Provider>('openai')
  const [model, setModel] = useState(providerModels.openai)
  const [systemPrompt, setSystemPrompt] = useState('You are Copia, a helpful personal assistant.')
  const [maxTokens, setMaxTokens] = useState('512')
  const [temperature, setTemperature] = useState('0.7')
  const [topP, setTopP] = useState('1')
  const [structuredOutput, setStructuredOutput] = useState(false)
  const [schema, setSchema] = useState('{\n  "type": "object",\n  "properties": {}\n}')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages)
  const [pendingSessionIds, setPendingSessionIds] = useState<string[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeLog, setActiveLog] = useState<RequestLog | null>(null)
  const [logTab, setLogTab] = useState<'request' | 'response'>('request')
  const [models, setModels] = useState<ProviderModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [profiles, setProfiles] = useState<Record<string, AgentConfig>>({})
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [savedSessions, setSavedSessions] = useState<ChatSessionSummary[]>([])
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const activeSessionIdRef = useRef<string | null>(null)
  const settingsRef = useOutsideClose(settingsOpen, () => setSettingsOpen(false))
  const supportsSampling = supportsSamplingParameters(provider, model)
  const isProfileSession = activeSession?.profile_name != null
  const isLoading = activeSession != null && pendingSessionIds.includes(activeSession.id)
  const latestUsage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index--) {
      if (messages[index].role === 'assistant' && contextTokenCount(messages[index].usage) != null) return messages[index]
    }
    return null
  }, [messages])

  useEffect(() => resizeTextArea(composerRef.current), [message])
  useEffect(() => { setModelsLoading(true); getModels(provider).then(setModels).catch(() => setModels([])).finally(() => setModelsLoading(false)) }, [provider])
  useEffect(() => { getProfiles().then(setProfiles).catch(() => setProfiles({})) }, [])
  useEffect(() => { void restoreSession() }, [])

  const baseConfig = useMemo<AgentConfig>(() => ({
    name: 'Copia',
    provider,
    model: model.trim(),
    system_prompt: systemPrompt.trim() || undefined,
    generation: { max_output_tokens: Number(maxTokens) },
  }), [maxTokens, model, provider, systemPrompt])

  function buildConfig(): AgentConfig {
    const result = { ...baseConfig, generation: { ...baseConfig.generation } }
    if (supportsSampling) {
      result.generation.temperature = Number(temperature)
      result.generation.top_p = Number(topP)
    }
    if (structuredOutput) result.structured_output = { schema: JSON.parse(schema), strict: true }
    return result
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const content = message.trim()
    if (!content || isLoading) return

    let requestForLog: object = {}
    let configForLog: AgentConfig | null = null
    let startedAt = 0
    let session: ChatSession | null = null
    try {
      const config = buildConfig()
      configForLog = config
      const timestamp = now()
      setMessage('')
      setMessages((current) => [...current, { id: Date.now(), role: 'user', content, timestamp }])
      startedAt = performance.now()
      session = activeSession
      if (!session) {
        session = await createSession(config)
        setActiveSession(session)
        activeSessionIdRef.current = session.id
        localStorage.setItem('copia.activeSessionId', session.id)
        void refreshSessions()
      }
      const requestSession = session
      const sessionConfig = requestSession.profile_name == null ? config : undefined
      requestForLog = { session_id: requestSession.id, config: sessionConfig ?? requestSession.config, content }
      setPendingSessionIds((current) => [...current, requestSession.id])
      const result = await sendSessionMessageWithMeta(requestSession.id, content, sessionConfig)
      const response = result.data
      const trace = response.response.trace
      const log: RequestLog = {
        provider: response.response.provider,
        model: response.response.model,
        status: trace?.status_code ?? result.status,
        duration: `${((performance.now() - startedAt) / 1000).toFixed(2)}s`,
        request: trace?.request_body ?? requestForLog,
        response: trace?.response_body ?? response,
      }
      if (activeSessionIdRef.current === requestSession.id) {
        setMessages((current) => [...current, {
          id: Date.now() + 1,
          role: 'assistant',
          content: response.response.content,
          timestamp: now(),
          log,
          usage: response.response.usage,
          contextWindow: response.response.context_window,
        }])
        if (sessionConfig) setActiveSession((current) => current ? { ...current, config: sessionConfig } : current)
      }
      window.setTimeout(() => void refreshSessions(), 700)
      window.setTimeout(() => void refreshSessions(), 2500)
    } catch (error) {
      const content = error instanceof Error ? error.message : 'Unexpected error'
      const apiError = error instanceof ApiRequestError ? error : null
      const trace = apiError?.providerTrace
      const log: RequestLog = {
        provider: activeSession?.config.provider ?? configForLog?.provider ?? provider,
        model: activeSession?.config.model ?? configForLog?.model ?? model,
        status: trace?.status_code ?? apiError?.status ?? 0,
        duration: startedAt ? `${((performance.now() - startedAt) / 1000).toFixed(2)}s` : '0.00s',
        request: trace?.request_body ?? requestForLog,
        response: trace?.response_body ?? apiError?.body ?? { error: content },
      }
      if (activeSessionIdRef.current === session?.id) {
        setMessages((current) => [...current, { id: Date.now() + 2, role: 'error', content, timestamp: now(), log }])
      }
    } finally {
      if (requestForLog && 'session_id' in requestForLog) {
        const sessionId = String(requestForLog.session_id)
        setPendingSessionIds((current) => current.filter((id) => id !== sessionId))
      }
    }
  }

  function changeProvider(nextProvider: Provider) {
    setProvider(nextProvider)
    setModel(providerModels[nextProvider])
  }

  function openSession(session: ChatSession) {
    setActiveSession(session)
    activeSessionIdRef.current = session.id
    localStorage.setItem('copia.activeSessionId', session.id)
    if (session.profile_name == null) applyConfig(session.config)
    setMessages(session.messages.map((item, index) => ({
      id: index,
      role: item.role,
      content: item.content,
      timestamp: '',
      usage: item.usage,
      contextWindow: item.context_window,
    })))
    setActiveLog(null)
    void refreshSessions()
  }

  async function restoreSession() {
    await refreshSessions()
    const sessionId = localStorage.getItem('copia.activeSessionId')
    if (!sessionId) return
    try { openSession(await getSession(sessionId)) } catch { localStorage.removeItem('copia.activeSessionId') }
  }

  async function refreshSessions() {
    try { setSavedSessions(await getSessions()) } catch { setSavedSessions([]) }
  }

  function applyConfig(config: AgentConfig) {
    setProvider(config.provider)
    setModel(config.model)
    setSystemPrompt(config.system_prompt ?? '')
    setMaxTokens(String(config.generation.max_output_tokens ?? 512))
    setTemperature(String(config.generation.temperature ?? 0.7))
    setTopP(String(config.generation.top_p ?? 1))
    setStructuredOutput(config.structured_output != null)
    if (config.structured_output) setSchema(JSON.stringify(config.structured_output.schema, null, 2))
  }

  function startNewChat() {
    setMode('chat')
    setActiveSession(null)
    activeSessionIdRef.current = null
    localStorage.removeItem('copia.activeSessionId')
    setMessages(starterMessages)
    setActiveLog(null)
  }

  async function removeSession(sessionId: string) {
    await deleteSession(sessionId)
    if (activeSession?.id === sessionId) startNewChat()
    await refreshSessions()
  }

  return (
    <main className={`app-shell ${activeLog ? 'has-logs' : ''}`}>
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">◇</div><strong>Copia</strong></div>
        <nav className="primary-nav">
          <button className={`new-chat ${mode === 'chat' ? 'active' : ''}`} onClick={startNewChat}><b>＋</b> Новый чат</button>
          <button className={`agents-nav ${mode === 'agents' ? 'active' : ''}`} onClick={() => setMode('agents')}>Агенты</button>
          <div className="saved-chats">{savedSessions.map((session) => <div className="saved-chat" key={session.id}><button className={session.id === activeSession?.id ? 'active' : ''} onClick={() => void getSession(session.id).then(openSession)}>{session.title ?? 'Новый чат'}</button><button className="delete-chat" aria-label="Удалить чат" onClick={() => void removeSession(session.id)}>×</button></div>)}</div>
        </nav>
      </aside>

      <section className="chat-stage">
        {mode === 'agents' ? <Agents profiles={profiles} onLaunch={async (profile) => { openSession(await createSessionFromProfile(profile)); setMode('chat') }} onCreate={async (config) => { openSession(await createSession(config)); setMode('chat') }} /> : <>
        <div className="messages-scroll" aria-live="polite"><div className="message-list">
          {messages.map((entry) => <article className={`message ${entry.role}`} key={entry.id}>
            {entry.role !== 'user' && <span className="avatar">{entry.role === 'error' ? '!' : activeSession?.config.avatar_path ? <img src={activeSession.config.avatar_path} alt={activeSession.config.name} /> : '◇'}</span>}
            <div className="message-body">
              <div className="markdown"><Markdown content={entry.content} /></div>
              {(entry.timestamp || entry.log || entry.usage) && <footer>
                {entry.timestamp && <span>{entry.timestamp}</span>}
                {entry.usage && <TokenUsageSummary usage={entry.usage} />}
                {entry.log && <button onClick={() => { setActiveLog(entry.log ?? null); setLogTab('request') }}>Логи</button>}
              </footer>}
            </div>
          </article>)}
          {isLoading && <article className="message assistant loading"><span className="avatar">{activeSession?.config.avatar_path ? <img src={activeSession.config.avatar_path} alt={activeSession.config.name} /> : '◇'}</span><div className="message-body"><p><i /><i /><i /></p><footer>Loading…</footer></div></article>}
        </div></div>
        <div className="composer-area">
          {!isProfileSession && settingsOpen && <div ref={settingsRef}><Settings
            provider={provider} model={model} models={models} modelsLoading={modelsLoading} systemPrompt={systemPrompt} maxTokens={maxTokens}
            temperature={temperature} topP={topP} structuredOutput={structuredOutput} schema={schema}
            supportsSampling={supportsSampling} onProvider={changeProvider} onModel={setModel}
            onSystemPrompt={setSystemPrompt} onMaxTokens={setMaxTokens} onTemperature={setTemperature}
            onTopP={setTopP} onStructuredOutput={setStructuredOutput} onSchema={setSchema}
          /></div>}
          <form className="composer" ref={formRef} onSubmit={submit}>
            <span className="model-indicator" title={contextUsageLabel(latestUsage?.usage, latestUsage?.contextWindow)}>
              <span className="model-chip">{isProfileSession ? activeSession?.config.name : model}</span>
              {latestUsage?.usage && <ContextProgress usage={latestUsage.usage} contextWindow={latestUsage.contextWindow} />}
            </span><span className="composer-divider" />
            {!isProfileSession && <button type="button" className={`tune ${settingsOpen ? 'active' : ''}`} onMouseDown={(event) => event.stopPropagation()} onClick={() => setSettingsOpen((open) => !open)} aria-label="Request settings">☷</button>}
            <textarea ref={composerRef} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => handleComposerKeyDown(event, formRef.current)} placeholder="Напишите сообщение Copia…" rows={1} disabled={isLoading} />
            <button className="send" type="submit" disabled={isLoading || !message.trim()} aria-label="Send">↑</button>
          </form>
          <p className="hint">Copia может допускать ошибки. Проверяйте важную информацию.</p>
        </div>
        </> }</section>
      {activeLog && <RequestLogs log={activeLog} tab={logTab} onTab={setLogTab} onClose={() => setActiveLog(null)} />}
    </main>
  )
}

function TokenUsageSummary({ usage }: { usage: TokenUsage }) {
  return <span className="token-usage">
    Input {formatTokens(usage.prompt_tokens)} · Output {formatTokens(usage.completion_tokens)} · Total {formatTokens(usage.total_tokens)}
  </span>
}

function ContextProgress({ usage, contextWindow }: { usage: TokenUsage; contextWindow?: number | null }) {
  const used = contextTokenCount(usage) ?? 0
  if (!contextWindow) return null
  const percentage = Math.min(100, used / contextWindow * 100)
  const level = percentage >= 95 ? 'critical' : percentage >= 80 ? 'warning' : ''
  const label = `${formatTokens(used)} / ${formatTokens(contextWindow)} · ${formatPercentage(percentage)}`
  return <span className={`context-progress ${level}`} role="progressbar" aria-label={`Заполнение контекстного окна: ${label}`} aria-valuemin={0} aria-valuemax={contextWindow} aria-valuenow={Math.min(used, contextWindow)}><i style={{ width: `${percentage}%` }} /></span>
}

type SettingsProps = {
  provider: Provider; model: string; models: ProviderModel[]; modelsLoading: boolean; systemPrompt: string; maxTokens: string; temperature: string; topP: string
  structuredOutput: boolean; schema: string; supportsSampling: boolean
  onProvider: (provider: Provider) => void; onModel: (value: string) => void; onSystemPrompt: (value: string) => void
  onMaxTokens: (value: string) => void; onTemperature: (value: string) => void; onTopP: (value: string) => void
  onStructuredOutput: (value: boolean) => void; onSchema: (value: string) => void
}

function Settings(props: SettingsProps) {
  return <section className="settings-popover">
    <header><b>Настройки запроса</b><span>Конфигурация применяется к обычному чату</span></header>
    <div className="settings-grid">
      <label>Провайдер<ProviderSelect value={props.provider} onChange={props.onProvider} /></label>
      <label>Модель<ModelsSelect value={props.model} models={props.models} loading={props.modelsLoading} onChange={props.onModel} /></label>
    </div>
    <label>System prompt<textarea value={props.systemPrompt} onChange={(e) => { props.onSystemPrompt(e.target.value); resizeTextArea(e.currentTarget) }} rows={1} /></label>
    <label>Max output tokens<input type="number" min="1" value={props.maxTokens} onChange={(e) => props.onMaxTokens(e.target.value)} /></label>
    {props.supportsSampling ? <div className="settings-grid">
      <label>Temperature<input type="number" min="0" max="2" step="0.1" value={props.temperature} onChange={(e) => props.onTemperature(e.target.value)} /></label>
      <label>Top p<input type="number" min="0.01" max="1" step="0.01" value={props.topP} onChange={(e) => props.onTopP(e.target.value)} /></label>
    </div> : <p className="model-note">Для этой модели параметры sampling задаёт провайдер.</p>}
    <label className="toggle-row"><span><b>Structured output</b><small>Ответ строго по JSON Schema</small></span><input type="checkbox" checked={props.structuredOutput} onChange={(e) => props.onStructuredOutput(e.target.checked)} /></label>
    {props.structuredOutput && <label>JSON Schema<textarea className="code-input" value={props.schema} onChange={(e) => props.onSchema(e.target.value)} rows={5} /></label>}
  </section>
}

function ModelsSelect({ value, models, loading, onChange }: { value: string; models: ProviderModel[]; loading: boolean; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useOutsideClose(isOpen, () => setIsOpen(false))
  return <div className="react-select" ref={ref}><button type="button" className="select-trigger" disabled={loading} onClick={() => setIsOpen(!isOpen)}>{loading ? 'Загрузка моделей…' : value}<span>⌄</span></button>{isOpen && <div className="select-menu">{models.length ? models.map((model) => <button type="button" key={model.id} onClick={() => { onChange(model.id); setIsOpen(false) }}>{model.id}</button>) : <span>Не удалось загрузить модели</span>}</div>}</div>
}

function Agents({ profiles, onLaunch, onCreate }: { profiles: Record<string, AgentConfig>; onLaunch: (profile: string) => Promise<void>; onCreate: (config: AgentConfig) => Promise<void> }) {
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
  useEffect(() => { setModelsLoading(true); getModels(provider).then(setAvailableModels).catch(() => setAvailableModels([])).finally(() => setModelsLoading(false)) }, [provider])
  const changeProvider = (nextProvider: Provider) => { setProvider(nextProvider); setModel(providerModels[nextProvider]) }
  const create = async (event: FormEvent) => { event.preventDefault(); await onCreate({ name, provider, model, system_prompt: prompt, generation: { max_output_tokens: Number(maxTokens), temperature: Number(temperature), top_p: Number(topP) } }) }
  return <div className="agents-screen"><div className="agents-title"><div><h1>Агенты</h1><p>Агент хранит независимую конфигурацию и историю в памяти текущего сервиса.</p></div><button onClick={() => setCreating(true)}>Создать агента</button></div>
    {creating && <form className="agent-form" onSubmit={(event) => void create(event)}><header><b>Новый агент</b><button type="button" onClick={() => setCreating(false)}>×</button></header><label>Название<input value={name} onChange={(e) => setName(e.target.value)} required /></label><div className="settings-grid"><label>Провайдер<ProviderSelect value={provider} onChange={changeProvider} /></label><label>Модель<ModelsSelect value={model} models={availableModels} loading={modelsLoading} onChange={setModel} /></label></div><label>System prompt<textarea value={prompt} onChange={(e) => { setPrompt(e.target.value); resizeTextArea(e.currentTarget) }} rows={1} /></label><div className="settings-grid"><label>Max output tokens<input type="number" min="1" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} /></label><label>Temperature<input type="number" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(e.target.value)} /></label><label>Top p<input type="number" min="0.01" max="1" step="0.01" value={topP} onChange={(e) => setTopP(e.target.value)} /></label></div><button className="create-submit" type="submit">Создать и открыть чат</button></form>}
    <div className="agent-list">{Object.entries(profiles).map(([id, config]) => <article key={id}>
      <div className="agent-avatar">{config.avatar_path ? <img src={config.avatar_path} alt="" /> : config.name.slice(0, 1)}</div>
      <div className="agent-card-content"><b>{config.name}</b><p>{config.description ?? 'Описание пока не добавлено.'}</p><span>{config.provider} · {config.model}</span></div>
      <button onClick={() => void onLaunch(id)}>Запустить чат</button>
    </article>)}</div></div>
}

function ProviderSelect({ value, onChange }: { value: Provider; onChange: (provider: Provider) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useOutsideClose(isOpen, () => setIsOpen(false))
  const labels: Record<Provider, string> = { openai: 'OpenAI', gigachat: 'GigaChat' }
  return <div className="react-select" ref={ref}>
    <button type="button" className="select-trigger" onClick={() => setIsOpen((open) => !open)} aria-expanded={isOpen}>{labels[value]}<span>⌄</span></button>
    {isOpen && <div className="select-menu">{(Object.keys(labels) as Provider[]).map((option) => <button type="button" key={option} className={option === value ? 'selected' : ''} onClick={() => { onChange(option); setIsOpen(false) }}>{labels[option]}</button>)}</div>}
  </div>
}

function Markdown({ content }: { content: string }) {
  const blocks: ReactNode[] = []
  const lines = content.split('\n')
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (line.startsWith('```')) {
      const language = line.slice(3).trim()
      const code: string[] = []
      while (++index < lines.length && !lines[index].startsWith('```')) code.push(lines[index])
      blocks.push(<pre key={index}><code className={language ? `language-${language}` : undefined}>{code.join('\n')}</code></pre>)
    } else if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^#+/)![0].length
      const Tag = `h${level}` as 'h1' | 'h2' | 'h3'
      blocks.push(<Tag key={index}>{inlineMarkdown(line.slice(level + 1))}</Tag>)
    } else if (/^[-*+]\s/.test(line)) {
      const items: ReactNode[] = []
      while (index < lines.length && /^[-*+]\s/.test(lines[index])) { items.push(<li key={index}>{inlineMarkdown(lines[index].slice(2))}</li>); index++ }
      blocks.push(<ul key={index}>{items}</ul>); index--; 
    } else if (/^\d+\.\s/.test(line)) {
      const items: ReactNode[] = []
      while (index < lines.length && /^\d+\.\s/.test(lines[index])) { items.push(<li key={index}>{inlineMarkdown(lines[index].replace(/^\d+\.\s/, ''))}</li>); index++ }
      blocks.push(<ol key={index}>{items}</ol>); index--;
    } else if (line.startsWith('> ')) {
      blocks.push(<blockquote key={index}>{inlineMarkdown(line.slice(2))}</blockquote>)
    } else if (line.trim()) {
      blocks.push(<p key={index}>{inlineMarkdown(line)}</p>)
    }
    index++
  }
  return <>{blocks}</>
}

function inlineMarkdown(value: string): ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^\s)]+\)|\*[^*]+\*)/g
  return value.split(pattern).filter(Boolean).map((part, index) => {
    if (part.startsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('[')) { const [, text, href] = part.match(/^\[([^\]]+)\]\(([^\s)]+)\)$/)!; return <a key={index} href={href} target="_blank" rel="noreferrer">{text}</a> }
    if (part.startsWith('*')) return <em key={index}>{part.slice(1, -1)}</em>
    return part
  })
}

function now() { return `Сегодня, ${new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date())}` }

function formatTokens(value?: number) { return value == null ? '—' : new Intl.NumberFormat('ru-RU').format(value) }

function formatPercentage(value: number) { return `${value < 0.1 && value > 0 ? value.toFixed(2) : value.toFixed(1)}%` }

function contextTokenCount(usage?: TokenUsage | null) {
  if (!usage) return undefined
  if (usage.prompt_tokens != null && usage.completion_tokens != null) return usage.prompt_tokens + usage.completion_tokens
  return usage.total_tokens
}

function contextUsageLabel(usage?: TokenUsage | null, contextWindow?: number | null) {
  const used = contextTokenCount(usage)
  if (used == null || !contextWindow) return undefined
  return `${formatTokens(used)} / ${formatTokens(contextWindow)} · ${formatPercentage(Math.min(100, used / contextWindow * 100))}`
}

function resizeTextArea(element: HTMLTextAreaElement | null) {
  if (!element) return
  element.style.height = '0px'
  element.style.height = `${Math.min(element.scrollHeight, 180)}px`
}

function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>, form: HTMLFormElement | null) {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  form?.requestSubmit()
}

function useOutsideClose(isOpen: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const closeIfOutside = (event: MouseEvent) => {
      if (event.target instanceof Node && !ref.current?.contains(event.target)) onClose()
    }
    document.addEventListener('mousedown', closeIfOutside)
    return () => document.removeEventListener('mousedown', closeIfOutside)
  }, [isOpen, onClose])
  return ref
}

function supportsSamplingParameters(provider: Provider, model: string): boolean {
  if (provider === 'gigachat') return true
  const normalized = model.trim().toLowerCase()
  const unsupportedPrefixes = ['gpt-5-mini-', 'gpt-5-nano-', 'gpt-5.1', 'gpt-5.2', 'gpt-6', 'o1', 'o3', 'o4']
  return !['gpt-5', 'gpt-5-mini', 'gpt-5-nano'].includes(normalized) && !unsupportedPrefixes.some((prefix) => normalized.startsWith(prefix))
}
