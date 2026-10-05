import { Dispatch, MutableRefObject, SetStateAction, useEffect, useRef } from 'react'
import { resumeActiveConversations } from '../../../data/api/conversationStream'
import { ChatMessage, TokenUsage } from '../../../domain/models/chat'
import { Provider } from '../../../domain/models/provider'
import { MemoryEvent } from '../../../domain/models/memory'
import { McpApproval } from '../../../domain/models/mcp'
import { now, transcriptLength } from './conversationUtils'

type ConversationRecoveryOptions = {
  sessionId: string | undefined
  messages: ChatMessage[]
  activeSessionIdRef: MutableRefObject<string | null>
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setPendingSessionIds: Dispatch<SetStateAction<string[]>>
  setSummarizingSessionIds: Dispatch<SetStateAction<string[]>>
  setMcpApproval: Dispatch<SetStateAction<McpApproval | null>>
  setRunningMcpTool: Dispatch<SetStateAction<string | null>>
  refreshSessions: () => Promise<unknown>
}

export function useConversationRecovery({
  sessionId,
  messages,
  activeSessionIdRef,
  setMessages,
  setPendingSessionIds,
  setSummarizingSessionIds,
  setMcpApproval,
  setRunningMcpTool,
  refreshSessions,
}: ConversationRecoveryOptions) {
  const recoveringSessionRef = useRef<string | null>(null)

  useEffect(() => {
    if (!sessionId || recoveringSessionRef.current === sessionId) return
    recoveringSessionRef.current = sessionId
    let assistantMessageId: number | null = null
    const transcriptIndex = transcriptLength(messages)
    const lastUserIndex = messages.reduce(
      (last, entry, index) => (entry.role === 'user' ? index : last),
      -1,
    )
    let text = ''
    setPendingSessionIds((current) =>
      current.includes(sessionId) ? current : [...current, sessionId],
    )

    void resumeActiveConversations(sessionId, (event) => {
      if (activeSessionIdRef.current !== sessionId) return
      if (event.event === 'message.delta') {
        text += String(event.data.text ?? '')
        if (assistantMessageId === null) {
          const existingAssistant = messages.find(
            (entry) =>
              entry.role === 'assistant' &&
              (entry.transcriptIndex ?? -1) > lastUserIndex &&
              entry.content.startsWith(text),
          )
          assistantMessageId = existingAssistant?.id ?? Date.now()
          const id = assistantMessageId
          if (existingAssistant) {
            setMessages((current) =>
              current.map((entry) => (entry.id === id ? { ...entry, content: text } : entry)),
            )
          } else {
            setMessages((current) => [
              ...current,
              { id, role: 'assistant', content: text, timestamp: now(), transcriptIndex },
            ])
          }
        } else {
          const id = assistantMessageId
          setMessages((current) =>
            current.map((entry) => (entry.id === id ? { ...entry, content: text } : entry)),
          )
        }
      } else if (event.event === 'tool.approval_required') {
        setMcpApproval(event.data as unknown as McpApproval)
      } else if (event.event === 'tool.running') {
        setMcpApproval(null)
        setRunningMcpTool(String(event.data.tool_name ?? ''))
      } else if (event.event === 'tool.completed') {
        setRunningMcpTool(null)
      } else if (event.event === 'conversation.completed') {
        const result = event.data.result as
          | {
              response?: {
                content?: string
                usage?: TokenUsage
                provider?: Provider
                model?: string
                context_window?: number
              }
              duration_seconds?: number
              rag_enabled?: boolean | null
              rewritten_query?: string | null
              memory_events?: MemoryEvent[]
              sources?: import('../../../domain/models/knowledgeSource').KnowledgeSource[]
            }
          | undefined
        if (result?.response) {
          const id = assistantMessageId ?? Date.now()
          if (assistantMessageId === null) assistantMessageId = id
          setMessages((current) =>
            current.some((entry) => entry.id === id)
              ? current.map((entry) =>
                  entry.id === id
                    ? {
                        ...entry,
                        content: result.response?.content ?? text,
                        usage: result.response?.usage,
                        provider: result.response?.provider,
                        model: result.response?.model,
                        durationSeconds: result.duration_seconds,
                        executionStatus: 'completed',
                        memoryEvents: result.memory_events,
                        contextWindow: result.response?.context_window,
                        sources: result.sources,
                        ragEnabled: result.rag_enabled,
                        rewrittenQuery: result.rewritten_query,
                      }
                    : entry,
                )
              : [
                  ...current,
                  {
                    id,
                    role: 'assistant',
                    content: result.response?.content ?? text,
                    timestamp: now(),
                    usage: result.response?.usage,
                    provider: result.response?.provider,
                    model: result.response?.model,
                    durationSeconds: result.duration_seconds,
                    executionStatus: 'completed',
                    memoryEvents: result.memory_events,
                    contextWindow: result.response?.context_window,
                    sources: result.sources,
                    ragEnabled: result.rag_enabled,
                    rewrittenQuery: result.rewritten_query,
                    transcriptIndex,
                  },
                ],
          )
        }
        setMcpApproval(null)
        setRunningMcpTool(null)
      } else if (event.event === 'conversation.failed') {
        setMcpApproval(null)
        setRunningMcpTool(null)
        setMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: 'error',
            content: String(event.data.message ?? 'Conversation failed'),
            timestamp: now(),
          },
        ])
      }
    })
      .catch((error: unknown) => {
        if (activeSessionIdRef.current !== sessionId) return
        setMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: 'error',
            content: error instanceof Error ? error.message : 'Conversation reconnect failed',
            timestamp: now(),
          },
        ])
      })
      .finally(() => {
        setPendingSessionIds((current) => current.filter((id) => id !== sessionId))
        setSummarizingSessionIds((current) => current.filter((id) => id !== sessionId))
        setMcpApproval(null)
        setRunningMcpTool(null)
        void refreshSessions()
      })
  }, [
    activeSessionIdRef,
    messages,
    refreshSessions,
    sessionId,
    setMessages,
    setMcpApproval,
    setPendingSessionIds,
    setRunningMcpTool,
    setSummarizingSessionIds,
  ])
}
