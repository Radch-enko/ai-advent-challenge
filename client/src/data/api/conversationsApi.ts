import { AgentConfig } from '../../domain/models/agent'
import {
  ConversationCommand,
  ConversationEvent,
  streamConversationResilient,
} from './conversationStream'
import type { SessionChatResponse } from '../../domain/models/session'

export async function sendConversationMessage(
  target: { kind: 'session' | 'agent'; id: string },
  content: string,
  config: AgentConfig | undefined,
  onEvent: (event: ConversationEvent) => void,
): Promise<SessionChatResponse> {
  let result: SessionChatResponse | undefined
  let failure: string | undefined
  const command: ConversationCommand = {
    command: 'message',
    request_id: crypto.randomUUID(),
    target,
    content,
    config,
  }
  await streamConversationResilient(command, (event) => {
    onEvent(event)
    if (event.event === 'conversation.completed') result = event.data.result as SessionChatResponse
    if (event.event === 'conversation.failed')
      failure = String(event.data.message ?? 'Conversation failed')
  })
  if (failure) throw new Error(failure)
  if (!result) throw new Error('Conversation ended without a result')
  return result
}

export async function retryConversationSummarization(
  sessionId: string,
  onEvent: (event: ConversationEvent) => void,
): Promise<SessionChatResponse> {
  let result: SessionChatResponse | undefined
  let failure: string | undefined
  await streamConversationResilient(
    { command: 'retry_summarization', request_id: crypto.randomUUID(), session_id: sessionId },
    (event) => {
      onEvent(event)
      if (event.event === 'conversation.completed')
        result = event.data.result as SessionChatResponse
      if (event.event === 'conversation.failed')
        failure = String(event.data.message ?? 'Conversation failed')
    },
  )
  if (failure) throw new Error(failure)
  if (!result) throw new Error('Conversation ended without a result')
  return result
}

export function decideConversationApproval(
  sessionId: string,
  approvalId: string,
  decision: 'approve' | 'reject',
  onEvent: (event: ConversationEvent) => void,
): Promise<void> {
  return streamConversationResilient(
    {
      command: 'approval_decision',
      request_id: crypto.randomUUID(),
      session_id: sessionId,
      approval_id: approvalId,
      decision,
    },
    onEvent,
  )
}
