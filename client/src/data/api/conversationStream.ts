import { ConversationEvent } from '../../domain/models/conversation'
export type { ConversationEvent } from '../../domain/models/conversation'

export type ConversationCommand = Record<string, unknown> & {
  command: string
  request_id: string
}

type ActiveConversation = {
  request_id: string
  conversation_id: string | null
  last_event_id: string | null
}

const activeRequestIds = new Set<string>()

function activeConversationsKey(scopeId: string): string {
  return `copia.activeConversations.${scopeId}`
}

function readActiveConversations(key: string): ActiveConversation[] {
  try {
    const value = sessionStorage.getItem(key)
    const parsed: unknown = value ? JSON.parse(value) : []
    return Array.isArray(parsed) ? (parsed as ActiveConversation[]) : []
  } catch {
    return []
  }
}

function updateActiveConversation(key: string, conversation: ActiveConversation): void {
  try {
    const conversations = readActiveConversations(key).filter(
      (item) => item.request_id !== conversation.request_id,
    )
    conversations.push(conversation)
    sessionStorage.setItem(key, JSON.stringify(conversations))
  } catch {
    // sessionStorage может быть отключён политикой браузера.
  }
}

function removeActiveConversation(key: string, requestId: string): void {
  try {
    sessionStorage.setItem(
      key,
      JSON.stringify(readActiveConversations(key).filter((item) => item.request_id !== requestId)),
    )
  } catch {
    // sessionStorage может быть отключён политикой браузера.
  }
}

export function parseSseBlock(block: string): ConversationEvent | null {
  let id = ''
  let event = 'message'
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator < 0 ? line : line.slice(0, separator)
    const value = separator < 0 ? '' : line.slice(separator + 1).replace(/^ /, '')
    if (field === 'id') id = value
    if (field === 'event') event = value
    if (field === 'data') data.push(value)
  }
  if (!data.length) return null
  return { id, event, data: JSON.parse(data.join('\n')) } as ConversationEvent
}

export async function streamConversation(
  command: ConversationCommand,
  onEvent: (event: ConversationEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/conversation', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(command),
  })
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null)
    throw new Error(
      typeof body?.detail?.message === 'string'
        ? body.detail.message
        : `Conversation request failed (${response.status})`,
    )
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseSseBlock(block)
      if (event) onEvent(event)
    }
    if (done) {
      const finalEvent = parseSseBlock(buffer)
      if (finalEvent) onEvent(finalEvent)
      return
    }
  }
}

export async function streamConversationResilient(
  command: ConversationCommand,
  onEvent: (event: ConversationEvent) => void,
  storageScopeId?: string,
): Promise<void> {
  activeRequestIds.add(command.request_id)
  try {
    await runConversationStream(command, onEvent, storageScopeId)
  } finally {
    activeRequestIds.delete(command.request_id)
  }
}

async function runConversationStream(
  command: ConversationCommand,
  onEvent: (event: ConversationEvent) => void,
  storageScopeId?: string,
): Promise<void> {
  const sessionId =
    storageScopeId ??
    (typeof command.session_id === 'string'
      ? command.session_id
      : typeof command.target === 'object' && command.target !== null
        ? String((command.target as { id?: unknown }).id ?? 'global')
        : 'global')
  const storageKey = activeConversationsKey(sessionId)
  let conversationId: string | null =
    command.command === 'resume' && typeof command.conversation_id === 'string'
      ? command.conversation_id
      : null
  let lastEventId: string | null =
    command.command === 'resume' && typeof command.after_event_id === 'string'
      ? command.after_event_id
      : null
  let terminal = false
  const seen = new Set<string>()
  updateActiveConversation(storageKey, {
    request_id: command.request_id,
    conversation_id: conversationId,
    last_event_id: lastEventId,
  })
  for (let attempt = 0; attempt < 4 && !terminal; attempt += 1) {
    const nextCommand: ConversationCommand =
      conversationId || command.command === 'resume'
        ? {
            command: 'resume',
            request_id: command.request_id,
            conversation_id: conversationId,
            after_event_id: lastEventId,
          }
        : command
    try {
      await streamConversation(nextCommand, (event) => {
        if (event.id && seen.has(event.id)) return
        if (event.id) {
          seen.add(event.id)
          lastEventId = event.id
        }
        if (
          event.event === 'conversation.started' &&
          typeof event.data.conversation_id === 'string'
        ) {
          conversationId = event.data.conversation_id
        }
        if (event.event === 'conversation.completed' || event.event === 'conversation.failed') {
          terminal = true
          removeActiveConversation(storageKey, command.request_id)
        } else {
          updateActiveConversation(storageKey, {
            request_id: command.request_id,
            conversation_id: conversationId,
            last_event_id: lastEventId,
          })
        }
        onEvent(event)
      })
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('Conversation request failed')) {
        throw error
      }
      if (attempt === 3) throw error
    }
  }
  if (!terminal) throw new Error('Conversation connection was interrupted')
}

export async function resumeActiveConversations(
  sessionId: string,
  onEvent: (event: ConversationEvent) => void,
): Promise<void> {
  const storageKey = activeConversationsKey(sessionId)
  const active = readActiveConversations(storageKey).filter(
    (conversation) => !activeRequestIds.has(conversation.request_id),
  )
  await Promise.all(
    active.map((conversation) =>
      streamConversationResilient(
        {
          command: 'resume',
          request_id: conversation.request_id,
          conversation_id: conversation.conversation_id,
          after_event_id: null,
        },
        onEvent,
        sessionId,
      ).catch((error: unknown) => {
        removeActiveConversation(storageKey, conversation.request_id)
        throw error
      }),
    ),
  )
}
