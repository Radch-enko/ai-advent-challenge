type Event<TName extends string, TData extends Record<string, unknown>> = {
  id: string
  event: TName
  data: TData
}

export type ConversationEvent =
  | Event<'conversation.started', { conversation_id: string; request_id: string }>
  | Event<'message.started', { conversation_id: string }>
  | Event<'message.delta', { text: string }>
  | Event<'tool.approval_required', Record<string, unknown>>
  | Event<'tool.running', { tool_name: string; decision?: string }>
  | Event<'tool.completed', { tool_name: string; status: string; duration_seconds?: number }>
  | Event<'approval.accepted', { approval_id: string; decision: string }>
  | Event<'conversation.completed', { conversation_id: string; result?: unknown }>
  | Event<
      'conversation.failed',
      { conversation_id: string; code: string; message: string; http_status?: number }
    >

export type ConversationState = {
  lastEventId: string | null
  text: string
  tools: Record<string, { status: string; name?: string }>
  approval: Record<string, unknown> | null
  status: 'running' | 'completed' | 'failed'
  error: string | null
  result: unknown
  seenEventIds: Set<string>
}

export function initialConversationState(): ConversationState {
  return {
    lastEventId: null,
    text: '',
    tools: {},
    approval: null,
    status: 'running',
    error: null,
    result: null,
    seenEventIds: new Set(),
  }
}

export function reduceConversationEvent(
  state: ConversationState,
  event: ConversationEvent,
): ConversationState {
  if (event.id && state.seenEventIds.has(event.id)) return state
  const next: ConversationState = {
    ...state,
    lastEventId: event.id || state.lastEventId,
    seenEventIds: new Set(state.seenEventIds),
  }
  if (event.id) next.seenEventIds.add(event.id)
  if (event.event === 'message.delta') next.text += String(event.data.text ?? '')
  if (event.event === 'tool.approval_required') next.approval = event.data
  if (event.event === 'tool.running' || event.event === 'tool.completed') {
    const name = String(event.data.tool_name ?? 'unknown')
    next.tools[name] = { name, status: event.event === 'tool.running' ? 'running' : 'completed' }
    if (event.event === 'tool.running') next.approval = null
  }
  if (event.event === 'conversation.completed') {
    next.status = 'completed'
    next.result = event.data.result
    next.approval = null
  }
  if (event.event === 'conversation.failed') {
    next.status = 'failed'
    next.error = String(event.data.message ?? 'Conversation failed')
    next.approval = null
  }
  return next
}
