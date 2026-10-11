import { afterEach, expect, it, vi } from 'vitest'
import {
  resumeActiveConversations,
  streamConversationResilient,
} from '../src/data/api/conversationStream'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }
}

afterEach(() => vi.unstubAllGlobals())

it('keeps the pending user message until a conversation finishes', async () => {
  const storage = new MemoryStorage()
  vi.stubGlobal('sessionStorage', storage)
  let finish = () => {}
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      finish = () => {
        controller.enqueue(
          new TextEncoder().encode(
            'id: demo:1\nevent: conversation.completed\ndata: {"conversation_id":"demo","result":{}}\n\n',
          ),
        )
        controller.close()
      }
    },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(body, { status: 200 })),
  )

  const streaming = streamConversationResilient(
    { command: 'message', request_id: 'demo-request', target: { kind: 'session', id: 'demo' } },
    () => {},
    'demo',
    { content: 'Where is the fictional compass?', transcript_index: 2 },
  )
  const active = JSON.parse(storage.getItem('copia.activeConversations.demo') ?? '[]')
  expect(active[0].pending_user_message).toEqual({
    content: 'Where is the fictional compass?',
    transcript_index: 2,
  })

  finish()
  await streaming
  expect(storage.getItem('copia.activeConversations.demo')).toBe('[]')
})

it('restores the pending user message before replaying the answer', async () => {
  const storage = new MemoryStorage()
  storage.setItem(
    'copia.activeConversations.demo',
    JSON.stringify([
      {
        request_id: 'demo-request',
        conversation_id: 'demo-conversation',
        last_event_id: null,
        pending_user_message: {
          content: 'Where is the fictional compass?',
          transcript_index: 2,
        },
      },
    ]),
  )
  vi.stubGlobal('sessionStorage', storage)
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          'id: demo:1\nevent: conversation.completed\ndata: {"conversation_id":"demo-conversation","result":{}}\n\n',
          { status: 200 },
        ),
    ),
  )
  const order: string[] = []

  await resumeActiveConversations(
    'demo',
    (event) => order.push(event.event),
    (message) => order.push(`user:${message.content}`),
  )

  expect(order).toEqual(['user:Where is the fictional compass?', 'conversation.completed'])
  expect(storage.getItem('copia.activeConversations.demo')).toBe('[]')
})
