import { Dispatch, FormEvent, MutableRefObject, SetStateAction } from 'react'
import { ApiRequestError } from '../../../data/api/request'
import { sendConversationMessage } from '../../../data/api/conversationsApi'
import { createSession, getSession } from '../../../data/api/sessionsApi'
import { startTask } from '../../../data/api/tasksApi'
import { ConversationEvent } from '../../../data/api/conversationStream'
import { AgentConfig } from '../../../domain/models/agent'
import { ChatMessage, FactsUpdateEvent, SummarizationEvent } from '../../../domain/models/chat'
import {
  initialConversationState,
  reduceConversationEvent,
} from '../../../domain/models/conversation'
import { McpApproval } from '../../../domain/models/mcp'
import { ChatSession } from '../../../domain/models/session'
import { RagSettings } from '../../../domain/models/ragSettings'
import {
  WorkingMemoryItem,
  PendingMemorySuggestion,
  MemoryEvent,
} from '../../../domain/models/memory'
import {
  now,
  transcriptLength,
  upsertFactsEvents,
  upsertSummarizationEvents,
  willSummarize,
} from './conversationUtils'

type SubmissionState = {
  session: ChatSession | null
  selectedProfileId: string | null
  message: string
  messages: ChatMessage[]
  summarizationEvents: SummarizationEvent[]
  isLoading: boolean
  summaryFailed: boolean
  taskIsActive: boolean
  taskModeEnabled: boolean
  ragModeEnabled: boolean
  ragSettings: RagSettings
}

type SubmissionActions = {
  buildConfig: () => AgentConfig
  openSession: (session: ChatSession) => void
  refreshSessions: () => Promise<boolean>
  setActiveSession: Dispatch<SetStateAction<ChatSession | null>>
  setTaskModeDraft: Dispatch<SetStateAction<boolean>>
  setRagModeDraft: Dispatch<SetStateAction<boolean>>
  setRagSettingsDraft: Dispatch<SetStateAction<RagSettings>>
  setMessage: Dispatch<SetStateAction<string>>
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setPendingSessionIds: Dispatch<SetStateAction<string[]>>
  setSummarizingSessionIds: Dispatch<SetStateAction<string[]>>
  setSummarizationEvents: Dispatch<SetStateAction<SummarizationEvent[]>>
  setFactsEvents: Dispatch<SetStateAction<FactsUpdateEvent[]>>
  setFacts: Dispatch<SetStateAction<Record<string, string>>>
  setMemoryEvents: Dispatch<SetStateAction<MemoryEvent[]>>
  setPendingMemory: Dispatch<SetStateAction<PendingMemorySuggestion[]>>
  setWorkingMemory: Dispatch<SetStateAction<WorkingMemoryItem[]>>
  setMcpApproval: Dispatch<SetStateAction<McpApproval | null>>
  setRunningMcpTool: Dispatch<SetStateAction<string | null>>
}

type SubmissionMeta = {
  activeSessionIdRef: MutableRefObject<string | null>
}

type ChatSubmissionOptions = {
  state: SubmissionState
  actions: SubmissionActions
  meta: SubmissionMeta
}

export function useChatSubmission({ state, actions, meta }: ChatSubmissionOptions) {
  const { activeSessionIdRef } = meta

  async function submitTask(instruction: string) {
    let session = state.session
    try {
      const config = actions.buildConfig()
      if (!session) {
        session = await createSession(
          config,
          state.selectedProfileId,
          true,
          state.ragModeEnabled,
          state.ragSettings,
        )
        actions.setActiveSession(session)
        activeSessionIdRef.current = session.id
        localStorage.setItem('copia.activeSessionId', session.id)
        actions.setTaskModeDraft(true)
        actions.setRagModeDraft(session.rag_enabled)
        actions.setRagSettingsDraft(session.rag_settings)
      }
      await startTask(session.id, instruction)
      const latest = await getSession(session.id)
      if (activeSessionIdRef.current === latest.id) actions.openSession(latest)
      void actions.refreshSessions()
    } catch (error) {
      if (activeSessionIdRef.current === session?.id) {
        actions.setMessages((current) => [
          ...current,
          {
            id: Date.now(),
            role: 'error',
            content: error instanceof Error ? error.message : 'Не удалось запустить задачу',
            timestamp: now(),
          },
        ])
      }
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const content = state.message.trim()
    if (!content || state.isLoading || state.summaryFailed || state.taskIsActive) return
    if (state.taskModeEnabled) {
      actions.setMessage('')
      await submitTask(content)
      return
    }

    let session: ChatSession | null = null
    let requestSessionId: string | null = null
    let assistantMessageId: number | null = null
    let conversationState = initialConversationState()
    try {
      const config = actions.buildConfig()
      const timestamp = now()
      const userTranscriptIndex = transcriptLength(state.messages)
      actions.setMessage('')
      actions.setMessages((current) => [
        ...current,
        { id: Date.now(), role: 'user', content, timestamp, transcriptIndex: userTranscriptIndex },
      ])
      session = state.session
      if (!session) {
        session = await createSession(
          config,
          state.selectedProfileId,
          false,
          state.ragModeEnabled,
          state.ragSettings,
        )
        actions.setActiveSession(session)
        activeSessionIdRef.current = session.id
        localStorage.setItem('copia.activeSessionId', session.id)
        actions.setRagModeDraft(session.rag_enabled)
        actions.setRagSettingsDraft(session.rag_settings)
        void actions.refreshSessions()
      }
      const requestSession = session
      requestSessionId = requestSession.id
      const sessionConfig = requestSession.profile_name == null ? config : undefined
      actions.setPendingSessionIds((current) => [...current, requestSession.id])
      const effectiveConfig = sessionConfig ?? requestSession.config
      if (
        willSummarize(
          transcriptLength(state.messages) + 1,
          state.summarizationEvents,
          effectiveConfig.context_management,
        )
      ) {
        actions.setSummarizingSessionIds((current) => [...current, requestSession.id])
      }

      const response = await sendConversationMessage(
        { kind: 'session', id: requestSession.id },
        content,
        sessionConfig,
        (event: ConversationEvent) => {
          if (activeSessionIdRef.current !== requestSession.id) return
          conversationState = reduceConversationEvent(conversationState, event)
          if (event.event === 'message.delta') {
            if (!assistantMessageId) {
              assistantMessageId = Date.now() + 1
              actions.setMessages((current) => [
                ...current,
                {
                  id: assistantMessageId!,
                  role: 'assistant',
                  content: conversationState.text,
                  timestamp: now(),
                  transcriptIndex: userTranscriptIndex + 1,
                },
              ])
            } else {
              const id = assistantMessageId
              actions.setMessages((current) =>
                current.map((entry) =>
                  entry.id === id ? { ...entry, content: conversationState.text } : entry,
                ),
              )
            }
          } else if (event.event === 'tool.approval_required') {
            actions.setMcpApproval(event.data as unknown as McpApproval)
            actions.setRunningMcpTool(null)
          } else if (event.event === 'tool.running') {
            actions.setMcpApproval(null)
            actions.setRunningMcpTool(String(event.data.tool_name ?? ''))
          } else if (
            event.event === 'tool.completed' ||
            event.event === 'conversation.completed' ||
            event.event === 'conversation.failed'
          ) {
            actions.setMcpApproval(null)
            actions.setRunningMcpTool(null)
          }
        },
      )

      if (activeSessionIdRef.current === requestSession.id) {
        if (response.summarization_events.length) {
          actions.setSummarizationEvents((current) =>
            upsertSummarizationEvents(current, response.summarization_events),
          )
        }
        if (response.facts_events.length) {
          actions.setFactsEvents((current) => upsertFactsEvents(current, response.facts_events))
        }
        actions.setFacts(response.facts)
        actions.setMemoryEvents(response.memory_events)
        actions.setPendingMemory(response.pending_memory)
        actions.setWorkingMemory(response.working_memory)
        actions.setMessages((current) => {
          const assistantMessage = {
            id: assistantMessageId ?? Date.now() + 1,
            role: 'assistant' as const,
            content: response.response.content,
            timestamp: now(),
            usage: response.response.usage,
            provider: response.response.provider,
            model: response.response.model,
            durationSeconds: response.duration_seconds,
            executionStatus: 'completed' as const,
            memoryEvents: response.memory_events,
            contextWindow: response.response.context_window,
            sources: response.sources,
            transcriptIndex: userTranscriptIndex + 1,
          }
          return assistantMessageId === null
            ? [...current, assistantMessage]
            : current.map((entry) =>
                entry.id === assistantMessageId ? { ...entry, ...assistantMessage } : entry,
              )
        })
        if (sessionConfig)
          actions.setActiveSession((current) =>
            current ? { ...current, config: sessionConfig } : current,
          )
      }
      window.setTimeout(() => void actions.refreshSessions(), 700)
      window.setTimeout(() => void actions.refreshSessions(), 2500)
    } catch (error) {
      const content = error instanceof Error ? error.message : 'Unexpected error'
      const apiError = error instanceof ApiRequestError ? error : null
      const summaryEvent = apiError?.summarizationEvent
      const factsEvent = apiError?.factsEvent
      if (summaryEvent && activeSessionIdRef.current === session?.id) {
        actions.setSummarizationEvents((current) =>
          upsertSummarizationEvents(current, [summaryEvent]),
        )
        actions.setMessages((current) => [
          ...current,
          { id: Date.now() + 2, role: 'error', content, timestamp: now() },
        ])
        void actions.refreshSessions()
      } else if (factsEvent && activeSessionIdRef.current === session?.id) {
        actions.setMessages((current) => [
          ...current.map((entry) =>
            entry.role === 'user' && entry.transcriptIndex === factsEvent.after_message_index
              ? { ...entry, transcriptIndex: undefined }
              : entry,
          ),
          { id: Date.now() + 2, role: 'error', content, timestamp: now() },
        ])
      } else if (activeSessionIdRef.current === session?.id) {
        actions.setMessages((current) => [
          ...current,
          { id: Date.now() + 2, role: 'error', content, timestamp: now() },
        ])
      }
    } finally {
      if (requestSessionId) {
        actions.setPendingSessionIds((current) => current.filter((id) => id !== requestSessionId))
        actions.setSummarizingSessionIds((current) =>
          current.filter((id) => id !== requestSessionId),
        )
        if (activeSessionIdRef.current === requestSessionId) {
          actions.setMcpApproval(null)
          actions.setRunningMcpTool(null)
        }
      }
    }
  }

  return { submit }
}
