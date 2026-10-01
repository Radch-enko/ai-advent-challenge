import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AgentConfig, ContextManagementConfig } from './domain/models/agent'
import { ChatSession } from './domain/models/session'
import { Provider, ProviderModel } from './domain/models/provider'
import { ChatMessage, FactsUpdateEvent, SummarizationEvent } from './domain/models/chat'
import { McpApproval } from './domain/models/mcp'
import { ChatTranscript } from './features/chat/ui/ChatTranscript'
import { ChatComposer } from './features/chat/ui/ChatComposer'
import { InvariantPanel } from './features/invariants/ui/InvariantPanel'
import { MemoryModal, MemoryPanel } from './features/memory/ui/MemoryPanel'
import { UserProfilesScreen } from './features/profiles/ui/UserProfilesScreen'
import { TaskPlanApprovalBar } from './features/tasks/ui/TaskPlanApprovalBar'
import { McpSettingsScreen } from './features/mcp/ui/McpSettingsScreen'
import { SummariesScreen } from './features/summaries/ui/SummariesScreen'
import { DocumentsScreen } from './features/document-indexing/ui/DocumentsScreen'
import { useInvariants } from './features/invariants/application/useInvariants'
import { useSavedSessions } from './features/chat/application/useSavedSessions'
import { useUserProfiles } from './features/profiles/application/useUserProfiles'
import { useAgentProfiles } from './features/agents/application/useAgentProfiles'
import { useMcpConnections } from './features/mcp/application/useMcpConnections'
import { useTaskActions } from './features/tasks/application/useTaskActions'
import { useSessionMemory } from './features/memory/application/useSessionMemory'
import { mapStoredMessages } from './features/chat/application/sessionTranscript'
import { useConversationRecovery } from './features/chat/application/useConversationRecovery'
import { useChatSubmission } from './features/chat/application/useChatSubmission'
import { useSessionOperations } from './features/chat/application/useSessionOperations'
import { useConversationControls } from './features/chat/application/useConversationControls'
import { AppMode, ApplicationShell } from './ui/ApplicationShell'
import { ProfileIndicator } from './features/chat/ui/chatAppComponents'
import { ProfileSessionSettings, Settings } from './features/configuration/ui/settingsComponents'
import { Agents } from './features/agents/ui/Agents'
import {
  contextTokenCount,
  normalizeContextManagement,
  supportsSamplingParameters,
  transcriptLength,
} from './features/chat/application/conversationUtils'
import {
  defaultContextManagement,
  providerModels,
} from './features/configuration/application/configDefaults'
import { loadProviderModels } from './features/configuration/application/modelCatalog'
import { isActiveTask, tasksForSession } from './features/tasks/application/taskSelectors'

const starterMessages: ChatMessage[] = []

export function App() {
  const [mode, setMode] = useState<AppMode>('chat')
  const [provider, setProvider] = useState<Provider>('openai')
  const [model, setModel] = useState(providerModels.openai)
  const [systemPrompt, setSystemPrompt] = useState('You are Copia, a helpful personal assistant.')
  const [maxTokens, setMaxTokens] = useState('512')
  const [temperature, setTemperature] = useState('0.7')
  const [topP, setTopP] = useState('1')
  const [structuredOutput, setStructuredOutput] = useState(false)
  const [schema, setSchema] = useState('{\n  "type": "object",\n  "properties": {}\n}')
  const [contextManagement, setContextManagement] = useState<ContextManagementConfig>(() =>
    defaultContextManagement('openai', providerModels.openai),
  )
  const [summarizerModels, setSummarizerModels] = useState<ProviderModel[]>([])
  const [summarizerModelsLoading, setSummarizerModelsLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages)
  const [summarizationEvents, setSummarizationEvents] = useState<SummarizationEvent[]>([])
  const [factsEvents, setFactsEvents] = useState<FactsUpdateEvent[]>([])
  const [forkingMessageIndex, setForkingMessageIndex] = useState<number | null>(null)
  const [forkError, setForkError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('copia.sidebarCollapsed') === 'true',
  )
  const [pendingSessionIds, setPendingSessionIds] = useState<string[]>([])
  const [summarizingSessionIds, setSummarizingSessionIds] = useState<string[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [taskModeDraft, setTaskModeDraft] = useState(false)
  const [ragModeDraft, setRagModeDraft] = useState(false)
  const [profileSettingsSaving, setProfileSettingsSaving] = useState(false)
  const [profileSettingsError, setProfileSettingsError] = useState<string | null>(null)
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false)
  const [models, setModels] = useState<ProviderModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [mcpApproval, setMcpApproval] = useState<McpApproval | null>(null)
  const [runningMcpTool, setRunningMcpTool] = useState<string | null>(null)
  const [profileSelectionError, setProfileSelectionError] = useState<string | null>(null)
  const [profileSelectionLoading, setProfileSelectionLoading] = useState(false)
  const [lastProfileSelection, setLastProfileSelection] = useState<{
    id: string | null
  } | null>(null)
  const [selectedUserProfileId, setSelectedUserProfileId] = useState<string | null>(null)
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const {
    profiles: userProfiles,
    loading: userProfilesLoading,
    error: userProfilesError,
    refresh: refreshUserProfiles,
  } = useUserProfiles()
  const {
    sessions: savedSessions,
    error: sessionListRefreshError,
    refresh: refreshSessions,
  } = useSavedSessions()
  const {
    items: invariants,
    refresh: refreshInvariants,
    add: addInvariant,
    edit: editInvariant,
    remove: removeInvariant,
  } = useInvariants()
  const profiles = useAgentProfiles()
  const { connections: mcpConnections, refresh: refreshMcpConnections } = useMcpConnections()
  const activeSessionIdRef = useRef<string | null>(null)
  const {
    facts,
    setFacts,
    longTermMemory,
    setLongTermMemory,
    memoryEvents,
    setMemoryEvents,
    pendingMemory,
    setPendingMemory,
    workingMemory,
    setWorkingMemory,
    editWorking,
    clearWorking,
    undoWorking,
    removeWorking,
    approvePending,
    rejectPending,
    addLongTermMemory,
    editLongTermMemory,
    removeLongTermMemory,
  } = useSessionMemory({
    session: activeSession,
    activeSessionIdRef,
    setSettingsError: setProfileSettingsError,
  })
  useConversationRecovery({
    sessionId: activeSession?.id,
    messages,
    activeSessionIdRef,
    setMessages,
    setPendingSessionIds,
    setSummarizingSessionIds,
    setMcpApproval,
    setRunningMcpTool,
    refreshSessions,
  })
  const supportsSampling = supportsSamplingParameters(provider, model)
  const summarizerProvider = contextManagement.summarizer.provider ?? provider
  const summarizerModel = contextManagement.summarizer.model ?? model
  const summarizerSupportsSampling = supportsSamplingParameters(summarizerProvider, summarizerModel)
  const factsProvider = contextManagement.facts_updater.provider ?? provider
  const factsModel = contextManagement.facts_updater.model ?? model
  const [factsModels, setFactsModels] = useState<ProviderModel[]>([])
  const [factsModelsLoading, setFactsModelsLoading] = useState(false)
  const factsSupportsSampling = supportsSamplingParameters(factsProvider, factsModel)
  const isProfileSession = activeSession?.profile_name != null
  const isLoading = activeSession != null && pendingSessionIds.includes(activeSession.id)
  const taskModeEnabled = activeSession?.task_mode_enabled ?? taskModeDraft
  const ragModeEnabled = activeSession?.rag_enabled ?? ragModeDraft
  const sessionTasks = useMemo(() => tasksForSession(activeSession), [activeSession])
  const activeTask = sessionTasks.find(isActiveTask)
  const taskIsActive = activeTask != null
  const tasksById = useMemo(
    () => new Map(sessionTasks.map((task) => [task.id, task])),
    [sessionTasks],
  )
  const lastTaskSubtaskMessageIndexes = useMemo(() => {
    const indexes = new Map<string, number>()
    messages.forEach((entry, index) => {
      if (entry.taskId && entry.taskStepId) indexes.set(entry.taskId, index)
    })
    return indexes
  }, [messages])
  const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({})
  const [expandedTaskMessageKeys, setExpandedTaskMessageKeys] = useState<Record<string, boolean>>(
    {},
  )
  const {
    retryingTaskId,
    taskRetryError,
    planFeedback,
    setPlanFeedback,
    planApprovalSubmitting,
    planApprovalError,
    setPlanApprovalError,
    approvePlan: approveActiveTaskPlan,
    requestChanges: requestActiveTaskPlanChanges,
    pause: pauseActiveTask,
    resume: resumeActiveTask,
    retry: retryFailedTask,
    resetForSession: resetTaskActionsForSession,
  } = useTaskActions({
    session: activeSession,
    activeTask,
    activeSessionIdRef,
    setActiveSession,
    setMessages,
    setExpandedTaskMessageKeys,
  })
  const isSummarizing = activeSession != null && summarizingSessionIds.includes(activeSession.id)
  const effectiveContextManagement =
    isProfileSession && activeSession ? activeSession.config.context_management : contextManagement
  const failedSummarization =
    effectiveContextManagement.strategy === 'summary'
      ? [...summarizationEvents].reverse().find((event) => event.status === 'failed')
      : undefined
  const contextWindowStart =
    effectiveContextManagement.strategy === 'sliding_window' ||
    effectiveContextManagement.strategy === 'sticky_facts'
      ? Math.max(0, transcriptLength(messages) - effectiveContextManagement.recent_message_limit)
      : null
  const latestUsage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index--) {
      if (messages[index].role === 'assistant' && contextTokenCount(messages[index].usage) != null)
        return messages[index]
    }
    return null
  }, [messages])
  const { submit } = useChatSubmission({
    state: {
      session: activeSession,
      selectedProfileId: selectedUserProfileId,
      message,
      messages,
      summarizationEvents,
      isLoading,
      summaryFailed: failedSummarization != null,
      taskIsActive,
      taskModeEnabled,
      ragModeEnabled,
    },
    actions: {
      buildConfig,
      openSession: (session) => openSession(session),
      refreshSessions,
      setActiveSession,
      setTaskModeDraft,
      setRagModeDraft,
      setMessage,
      setMessages,
      setPendingSessionIds,
      setSummarizingSessionIds,
      setSummarizationEvents,
      setFactsEvents,
      setFacts,
      setMemoryEvents,
      setPendingMemory,
      setWorkingMemory,
      setMcpApproval,
      setRunningMcpTool,
    },
    meta: { activeSessionIdRef },
  })
  const { respondToMcpApproval, retrySummarization } = useConversationControls({
    state: { session: activeSession, activeTask, isLoading },
    actions: {
      refreshSessions,
      setMessages,
      setPendingSessionIds,
      setSummarizingSessionIds,
      setSummarizationEvents,
      setMemoryEvents,
      setMcpApproval,
      setRunningMcpTool,
    },
    meta: { activeSessionIdRef },
  })
  useEffect(() => {
    loadProviderModels(provider, setModels, setModelsLoading)
  }, [provider])
  useEffect(() => {
    loadProviderModels(summarizerProvider, setSummarizerModels, setSummarizerModelsLoading)
  }, [summarizerProvider])
  useEffect(() => {
    loadProviderModels(factsProvider, setFactsModels, setFactsModelsLoading)
  }, [factsProvider])
  useEffect(() => {
    if (mode === 'agents') {
      void refreshMcpConnections()
    }
  }, [mode, refreshMcpConnections])
  useEffect(() => {
    if (activeTask?.status !== 'waiting_for_approval') {
      setPlanFeedback('')
      setPlanApprovalError(null)
    }
  }, [activeTask?.id, activeTask?.status, setPlanFeedback, setPlanApprovalError])

  const baseConfig = useMemo<AgentConfig>(
    () => ({
      name: 'Copia',
      provider,
      model: model.trim(),
      system_prompt: systemPrompt.trim() || undefined,
      generation: { max_output_tokens: Number(maxTokens) },
      context_management: contextManagement,
      mcp_access: activeSession?.config.mcp_access ?? [],
    }),
    [activeSession?.config.mcp_access, contextManagement, maxTokens, model, provider, systemPrompt],
  )

  function buildConfig(): AgentConfig {
    const result = {
      ...baseConfig,
      generation: { ...baseConfig.generation },
      context_management: {
        ...baseConfig.context_management,
        summarizer: {
          ...baseConfig.context_management.summarizer,
          generation: { ...baseConfig.context_management.summarizer.generation },
        },
      },
    }
    if (supportsSampling) {
      result.generation.temperature = Number(temperature)
      result.generation.top_p = Number(topP)
    }
    if (structuredOutput) result.structured_output = { schema: JSON.parse(schema), strict: true }
    return result
  }

  function changeProvider(nextProvider: Provider) {
    setProvider(nextProvider)
    setModel(providerModels[nextProvider])
  }

  const applyConfig = useCallback((config: AgentConfig) => {
    setProvider(config.provider)
    setModel(config.model)
    setSystemPrompt(config.system_prompt ?? '')
    setMaxTokens(String(config.generation.max_output_tokens ?? 512))
    setTemperature(String(config.generation.temperature ?? 0.7))
    setTopP(String(config.generation.top_p ?? 1))
    setStructuredOutput(config.structured_output != null)
    if (config.structured_output)
      setSchema(JSON.stringify(config.structured_output.schema, null, 2))
    setContextManagement(
      normalizeContextManagement(config.context_management, config.provider, config.model),
    )
  }, [])

  const openSession = useCallback(
    (session: ChatSession) => {
      setMode('chat')
      setActiveSession(session)
      setMcpApproval(null)
      setRunningMcpTool(null)
      setTaskModeDraft(session.task_mode_enabled)
      setRagModeDraft(session.rag_enabled)
      resetTaskActionsForSession()
      setSelectedUserProfileId(session.user_profile_id)
      activeSessionIdRef.current = session.id
      localStorage.setItem('copia.activeSessionId', session.id)
      if (session.profile_name == null) applyConfig(session.config)
      setMessages(mapStoredMessages(session.messages))
      setSummarizationEvents(session.context.events)
      setFactsEvents(session.context.facts_events ?? [])
      void refreshInvariants()
      setProfileSettingsError(null)
      setForkError(null)
      setMemoryPanelOpen(false)
      void refreshSessions()
    },
    [applyConfig, refreshInvariants, refreshSessions, resetTaskActionsForSession],
  )

  const startNewChat = useCallback(() => {
    setMode('chat')
    setActiveSession(null)
    setMcpApproval(null)
    setRunningMcpTool(null)
    setTaskModeDraft(false)
    setRagModeDraft(false)
    activeSessionIdRef.current = null
    localStorage.removeItem('copia.activeSessionId')
    setMessages(starterMessages)
    setSummarizationEvents([])
    setFactsEvents([])
    setFacts({})
    setLongTermMemory([])
    setPendingMemory([])
    setWorkingMemory([])
    setExpandedTaskIds({})
    setExpandedTaskMessageKeys({})
    setProfileSettingsError(null)
    setForkError(null)
    setMemoryPanelOpen(false)
  }, [setFacts, setLongTermMemory, setPendingMemory, setWorkingMemory])

  const sessionOperations = useSessionOperations({
    state: {
      activeSession,
      activeTask,
      taskIsActive,
      ragModeDraft,
      isLoading,
      profileSettingsSaving,
      forkingMessageIndex,
      lastProfileSelection,
    },
    actions: {
      openSession,
      startNewChat,
      refreshSessions,
      setActiveSession,
      setTaskModeDraft,
      setRagModeDraft,
      setSelectedUserProfileId,
      setProfileSelectionError,
      setProfileSelectionLoading,
      setLastProfileSelection,
      setProfileSettingsSaving,
      setProfileSettingsError,
      setForkingMessageIndex,
      setForkError,
      setMessages,
    },
    meta: { activeSessionIdRef },
  })

  function setSidebarVisibility(collapsed: boolean) {
    setSidebarCollapsed(collapsed)
    localStorage.setItem('copia.sidebarCollapsed', String(collapsed))
  }

  const profileControl = (
    <ProfileIndicator
      profiles={userProfiles}
      selectedId={selectedUserProfileId}
      loading={userProfilesLoading}
      error={userProfilesError}
      onSelect={(id) => void sessionOperations.selectUserProfile(id)}
      onManage={() => setMode('profiles')}
      selectionError={profileSelectionError}
      selectionLoading={profileSelectionLoading}
      onRetrySelection={sessionOperations.retryProfileSelection}
      onRetryProfiles={() => void refreshUserProfiles()}
      sessionRefreshError={sessionListRefreshError}
      onRetrySessionRefresh={() => void refreshSessions()}
    />
  )

  function toggleTaskMessage(key: string) {
    setExpandedTaskMessageKeys((current) => ({
      ...current,
      [key]: !current[key],
    }))
  }

  async function openInvariantsScreen() {
    await refreshInvariants()
    setMode('invariants')
  }

  const memoryPanelContent = activeSession ? (
    <MemoryPanel
      open={true}
      profileName={activeSession.profile_name}
      facts={facts}
      memoryEvents={memoryEvents}
      workingMemory={workingMemory}
      pendingMemory={pendingMemory}
      longTermMemory={longTermMemory}
      onToggle={() => setMemoryPanelOpen(false)}
      onClearWorking={() => clearWorking(activeSession.id)}
      onUndoWorking={() => undoWorking(activeSession.id)}
      onEditWorking={(item) => editWorking(activeSession.id, item)}
      onDeleteWorking={(item) => removeWorking(activeSession.id, item)}
      onApprovePending={(suggestion) => approvePending(activeSession.id, suggestion)}
      onRejectPending={(suggestion) => rejectPending(activeSession.id, suggestion)}
      onAddLongTermMemory={(value) =>
        activeSession.profile_name
          ? addLongTermMemory(activeSession.id, activeSession.profile_name, value)
          : Promise.resolve()
      }
      onEditLongTermMemory={(itemId, value) =>
        activeSession.profile_name
          ? editLongTermMemory(activeSession.id, activeSession.profile_name, itemId, value)
          : Promise.resolve()
      }
      onDeleteLongTermMemory={(itemId) =>
        activeSession.profile_name
          ? removeLongTermMemory(activeSession.id, activeSession.profile_name, itemId)
          : Promise.resolve()
      }
    />
  ) : null

  const invariantPanelContent = (
    <InvariantPanel
      items={invariants}
      onAdd={addInvariant}
      onEdit={editInvariant}
      onDelete={removeInvariant}
    />
  )

  return (
    <ApplicationShell
      mode={mode}
      sidebarCollapsed={sidebarCollapsed}
      sessions={savedSessions}
      activeSessionId={activeSession?.id ?? null}
      profileControl={profileControl}
      onNewChat={startNewChat}
      onNavigate={setMode}
      onOpenInvariants={() => void openInvariantsScreen()}
      onToggleSidebar={setSidebarVisibility}
      onOpenSession={(sessionId) => void sessionOperations.openSavedSession(sessionId)}
      onRemoveSession={(sessionId) => void sessionOperations.removeSession(sessionId)}
    >
      {mode === 'mcp' ? (
        <McpSettingsScreen />
      ) : mode === 'documents' ? (
        <DocumentsScreen />
      ) : mode === 'summaries' ? (
        <SummariesScreen />
      ) : mode === 'invariants' ? (
        <section className="invariants-screen">{invariantPanelContent}</section>
      ) : mode === 'profiles' ? (
        <UserProfilesScreen
          profiles={userProfiles}
          loading={userProfilesLoading}
          error={userProfilesError}
          selectedId={selectedUserProfileId}
          onRetry={refreshUserProfiles}
          onChanged={() => refreshUserProfiles(false)}
          onChooseOtherProfile={() => setMode('chat')}
          onManageProfiles={() => setMode('profiles')}
          onCloseState={() => setMode('chat')}
        />
      ) : mode === 'agents' ? (
        <Agents
          profiles={profiles}
          mcpConnections={mcpConnections}
          onLaunch={async (profile) => {
            openSession(await sessionOperations.createFromProfile(profile))
            setMode('chat')
          }}
          onCreate={async (config) => {
            openSession(await sessionOperations.createWithConfig(config))
            setMode('chat')
          }}
        />
      ) : (
        <>
          <ChatTranscript
            messages={messages}
            activeSession={activeSession}
            sessionTasks={sessionTasks}
            tasksById={tasksById}
            activeTask={activeTask}
            lastTaskSubtaskMessageIndexes={lastTaskSubtaskMessageIndexes}
            expandedTaskIds={expandedTaskIds}
            expandedTaskMessageKeys={expandedTaskMessageKeys}
            taskModeEnabled={taskModeEnabled}
            taskRetryingId={retryingTaskId}
            taskRetryError={taskRetryError}
            contextWindowStart={contextWindowStart}
            contextManagement={effectiveContextManagement}
            summarizationEvents={summarizationEvents}
            factsEvents={factsEvents}
            isLoading={isLoading}
            isSummarizing={isSummarizing}
            failedSummarization={failedSummarization}
            forkError={forkError}
            forkingMessageIndex={forkingMessageIndex}
            mcpApproval={mcpApproval}
            runningMcpTool={runningMcpTool}
            onToggleTaskMessage={toggleTaskMessage}
            onToggleTask={(taskId) =>
              setExpandedTaskIds((current) => ({ ...current, [taskId]: !current[taskId] }))
            }
            onPauseTask={() => void pauseActiveTask()}
            onResumeTask={() => void resumeActiveTask()}
            onRetryTask={(task) => void retryFailedTask(task)}
            onForkMessage={(messageIndex) => void sessionOperations.forkFromMessage(messageIndex)}
            onRetrySummarization={() => void retrySummarization()}
            onRespondToMcpApproval={(approval, decision) =>
              void respondToMcpApproval(approval, decision)
            }
          />
          <ChatComposer
            message={message}
            usage={latestUsage?.usage}
            contextWindow={latestUsage?.contextWindow}
            modelLabel={isProfileSession && activeSession ? activeSession.config.name : model}
            sessionAvailable={activeSession !== null}
            settingsOpen={settingsOpen}
            settingsContent={
              isProfileSession && activeSession ? (
                <ProfileSessionSettings
                  profileControl={profileControl}
                  value={activeSession.config.context_management}
                  facts={facts}
                  provider={activeSession.config.provider}
                  longTermMemoryEnabled={activeSession.long_term_memory_enabled}
                  saving={profileSettingsSaving}
                  error={profileSettingsError}
                  onChange={sessionOperations.setProfileContextManagement}
                  onLongTermMemoryEnabled={sessionOperations.setLongTermMemoryEnabled}
                  taskModeEnabled={taskModeEnabled}
                  taskModeDisabled={taskIsActive}
                  onTaskMode={(enabled) => void sessionOperations.setTaskMode(enabled)}
                  ragEnabled={ragModeEnabled}
                  ragModeDisabled={taskIsActive || profileSettingsSaving}
                  onRagMode={(enabled) => void sessionOperations.setRagMode(enabled)}
                />
              ) : (
                <Settings
                  profileControl={profileControl}
                  provider={provider}
                  model={model}
                  models={models}
                  modelsLoading={modelsLoading}
                  systemPrompt={systemPrompt}
                  maxTokens={maxTokens}
                  temperature={temperature}
                  topP={topP}
                  structuredOutput={structuredOutput}
                  schema={schema}
                  supportsSampling={supportsSampling}
                  onProvider={changeProvider}
                  onModel={setModel}
                  onSystemPrompt={setSystemPrompt}
                  onMaxTokens={setMaxTokens}
                  onTemperature={setTemperature}
                  onTopP={setTopP}
                  onStructuredOutput={setStructuredOutput}
                  onSchema={setSchema}
                  contextManagement={contextManagement}
                  summarizerModels={summarizerModels}
                  summarizerModelsLoading={summarizerModelsLoading}
                  summarizerSupportsSampling={summarizerSupportsSampling}
                  onContextManagement={setContextManagement}
                  facts={facts}
                  factsModels={factsModels}
                  factsModelsLoading={factsModelsLoading}
                  factsSupportsSampling={factsSupportsSampling}
                  taskModeEnabled={taskModeEnabled}
                  taskModeDisabled={taskIsActive}
                  onTaskMode={(enabled) => void sessionOperations.setTaskMode(enabled)}
                  ragEnabled={ragModeEnabled}
                  ragModeDisabled={taskIsActive || profileSettingsSaving}
                  onRagMode={(enabled) => void sessionOperations.setRagMode(enabled)}
                  error={profileSettingsError}
                />
              )
            }
            planApprovalContent={
              activeTask?.status === 'waiting_for_approval' &&
              activeTask.stage === 'plan_review' &&
              !activeTask.mcp_approval ? (
                <TaskPlanApprovalBar
                  task={activeTask}
                  feedback={planFeedback}
                  submitting={planApprovalSubmitting}
                  error={planApprovalError}
                  onFeedbackChange={setPlanFeedback}
                  onApprove={() => void approveActiveTaskPlan()}
                  onRequestChanges={() => void requestActiveTaskPlanChanges()}
                />
              ) : null
            }
            memoryPanelOpen={memoryPanelOpen}
            isLoading={isLoading}
            summaryFailed={failedSummarization != null}
            taskIsActive={taskIsActive}
            canPauseTask={activeSession?.task?.status === 'running'}
            onMessageChange={setMessage}
            onSubmit={(event) => void submit(event)}
            onToggleSettings={() => setSettingsOpen((open) => !open)}
            onToggleMemory={() => setMemoryPanelOpen(true)}
            onPauseTask={() => void pauseActiveTask()}
          />
          {activeSession && memoryPanelOpen && memoryPanelContent && (
            <MemoryModal onClose={() => setMemoryPanelOpen(false)}>
              {memoryPanelContent}
            </MemoryModal>
          )}
        </>
      )}
    </ApplicationShell>
  )
}
