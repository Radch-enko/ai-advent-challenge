import { ChatMessage } from '../../../domain/models/chat'
import { StoredMessage } from '../../../domain/models/session'
import { formatMessageTimestamp } from './conversationUtils'

export function mapStoredMessages(messages: StoredMessage[]): ChatMessage[] {
  return messages.map((item, index) => ({
    id: index,
    role: item.role,
    content: displayStoredContent(item.content),
    timestamp: formatMessageTimestamp(item.created_at),
    usage: item.usage,
    contextWindow: item.context_window,
    provider: item.provider,
    model: item.model,
    durationSeconds: item.duration_seconds,
    executionStatus: item.execution_status ?? undefined,
    executionError: item.execution_error,
    taskId: item.task_id ?? undefined,
    taskStepId: item.task_step_id ?? undefined,
    sources: item.sources ?? [],
    ragEnabled: item.rag_enabled,
    rewrittenQuery: item.rewritten_query,
    transcriptIndex: index,
  }))
}

function displayStoredContent(content: string): string {
  try {
    const decoded: unknown = JSON.parse(content)
    if (!isLegacyRagAnswer(decoded)) return content
    return decoded.answer
  } catch {
    return content
  }
}

function isLegacyRagAnswer(
  value: unknown,
): value is { answer_mode: string; answer: string; citations: unknown[] } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const candidate = value as Record<string, unknown>
  const knownFields = ['answer_mode', 'answer', 'citations']
  return (
    Object.keys(candidate).length === knownFields.length &&
    knownFields.every((field) => Object.hasOwn(candidate, field)) &&
    typeof candidate.answer_mode === 'string' &&
    ['grounded', 'general_knowledge', 'clarification_needed', 'personal_unknown'].includes(
      candidate.answer_mode,
    ) &&
    typeof candidate.answer === 'string' &&
    Array.isArray(candidate.citations) &&
    candidate.citations.every(isLegacyCitation)
  )
}

function isLegacyCitation(value: unknown): boolean {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const citation = value as Record<string, unknown>
  return (
    Object.keys(citation).length === 2 &&
    typeof citation.chunk_id === 'string' &&
    typeof citation.quote === 'string'
  )
}
