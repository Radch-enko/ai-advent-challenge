import { ChatMessage } from '../../../domain/models/chat'
import { StoredMessage } from '../../../domain/models/session'
import { formatMessageTimestamp } from './conversationUtils'

export function mapStoredMessages(messages: StoredMessage[]): ChatMessage[] {
  return messages.map((item, index) => ({
    id: index,
    role: item.role,
    content: item.content,
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
    transcriptIndex: index,
  }))
}
