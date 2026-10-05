import { Dispatch, MutableRefObject, SetStateAction } from 'react'
import { ApiRequestError } from '../../../data/api/request'
import {
  decideConversationApproval,
  retryConversationSummarization,
} from '../../../data/api/conversationsApi'
import { ChatMessage, SummarizationEvent } from '../../../domain/models/chat'
import {
  initialConversationState,
  reduceConversationEvent,
} from '../../../domain/models/conversation'
import { McpApproval } from '../../../domain/models/mcp'
import { ChatSession } from '../../../domain/models/session'
import { TaskState } from '../../../domain/models/task'
import { MemoryEvent } from '../../../domain/models/memory'
import { now, transcriptLength, upsertSummarizationEvents } from './conversationUtils'

type ControlsState = {
  session: ChatSession | null
  activeTask: TaskState | undefined
  isLoading: boolean
}

type ControlsActions = {
  refreshSessions: () => Promise<boolean>
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setPendingSessionIds: Dispatch<SetStateAction<string[]>>
  setSummarizingSessionIds: Dispatch<SetStateAction<string[]>>
  setSummarizationEvents: Dispatch<SetStateAction<SummarizationEvent[]>>
  setMemoryEvents: Dispatch<SetStateAction<MemoryEvent[]>>
  setMcpApproval: Dispatch<SetStateAction<McpApproval | null>>
  setRunningMcpTool: Dispatch<SetStateAction<string | null>>
}

type ControlsMeta = {
  activeSessionIdRef: MutableRefObject<string | null>
}

type ConversationControlsOptions = {
  state: ControlsState
  actions: ControlsActions
  meta: ControlsMeta
}

export function useConversationControls({ state, actions, meta }: ConversationControlsOptions) {
  async function respondToMcpApproval(approval: McpApproval, decision: 'approve' | 'reject') {
    if (!state.session) return
    try {
      await decideConversationApproval(state.session.id, approval.id, decision, (event) => {
        if (event.event === 'conversation.failed') {
          throw new Error(String(event.data.message ?? 'Не удалось отправить решение'))
        }
      })
      actions.setMcpApproval(null)
      if (decision === 'approve' && approval.id !== state.activeTask?.mcp_approval?.id)
        actions.setRunningMcpTool(approval.tool_name)
    } catch (approvalError) {
      actions.setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: 'error',
          content:
            approvalError instanceof Error ? approvalError.message : 'Не удалось отправить решение',
          timestamp: now(),
        },
      ])
    }
  }

  async function retrySummarization() {
    const session = state.session
    if (!session || state.isLoading) return
    actions.setPendingSessionIds((current) => [...current, session.id])
    actions.setSummarizingSessionIds((current) => [...current, session.id])
    let assistantMessageId: number | null = null
    let conversationState = initialConversationState()
    try {
      const response = await retryConversationSummarization(session.id, (event) => {
        conversationState = reduceConversationEvent(conversationState, event)
        if (event.event !== 'message.delta' || meta.activeSessionIdRef.current !== session.id)
          return
        if (assistantMessageId === null) {
          assistantMessageId = Date.now()
          const id = assistantMessageId
          actions.setMessages((current) => [
            ...current,
            {
              id,
              role: 'assistant',
              content: conversationState.text,
              timestamp: now(),
              transcriptIndex: transcriptLength(current),
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
      })
      if (meta.activeSessionIdRef.current === session.id) {
        actions.setSummarizationEvents((current) =>
          upsertSummarizationEvents(current, response.summarization_events),
        )
        actions.setMemoryEvents(response.memory_events)
        actions.setMessages((current) => {
          const message: ChatMessage = {
            id: assistantMessageId ?? Date.now(),
            role: 'assistant',
            content: response.response.content,
            timestamp: now(),
            usage: response.response.usage,
            provider: response.response.provider,
            model: response.response.model,
            durationSeconds: response.duration_seconds,
            executionStatus: 'completed',
            memoryEvents: response.memory_events,
            contextWindow: response.response.context_window,
            sources: response.sources,
            ragEnabled: response.rag_enabled,
            rewrittenQuery: response.rewritten_query,
            transcriptIndex: transcriptLength(current),
          }
          return assistantMessageId === null
            ? [...current, message]
            : current.map((entry) =>
                entry.id === assistantMessageId ? { ...entry, ...message } : entry,
              )
        })
      }
      void actions.refreshSessions()
    } catch (error) {
      const apiError = error instanceof ApiRequestError ? error : null
      const summaryEvent = apiError?.summarizationEvent
      if (summaryEvent && meta.activeSessionIdRef.current === session.id) {
        actions.setSummarizationEvents((current) =>
          upsertSummarizationEvents(current, [summaryEvent]),
        )
        actions.setMessages((current) => [
          ...current,
          {
            id: Date.now(),
            role: 'error',
            content: summaryEvent.error ?? 'Conversation summarization failed',
            timestamp: now(),
          },
        ])
      } else if (meta.activeSessionIdRef.current === session.id) {
        actions.setMessages((current) => [
          ...current,
          {
            id: Date.now(),
            role: 'error',
            content: error instanceof Error ? error.message : 'Unexpected error',
            timestamp: now(),
          },
        ])
      }
    } finally {
      actions.setPendingSessionIds((current) => current.filter((id) => id !== session.id))
      actions.setSummarizingSessionIds((current) => current.filter((id) => id !== session.id))
    }
  }

  return { respondToMcpApproval, retrySummarization }
}
