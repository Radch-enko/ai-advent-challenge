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

it('does not replay a request already streaming in this tab', async () => {
  vi.stubGlobal('sessionStorage', new MemoryStorage())
  const terminal = new TextEncoder().encode(
    'id: demo:1\nevent: conversation.completed\ndata: {"conversation_id":"demo","result":{}}\n\n',
  )
  let finishPrimary = () => {}
  const primaryBody = new ReadableStream<Uint8Array>({
    start(controller) {
      finishPrimary = () => {
        controller.enqueue(terminal)
        controller.close()
      }
    },
  })
  const fetchMock = vi.fn(async () =>
    new Response(fetchMock.mock.calls.length === 1 ? primaryBody : terminal, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  const primaryEvents: string[] = []
  const replayedEvents: string[] = []

  const primary = streamConversationResilient(
    { command: 'message', request_id: 'demo-request' },
    (event) => primaryEvents.push(event.event),
    'demo-session',
  )
  const recovery = resumeActiveConversations('demo-session', (event) =>
    replayedEvents.push(event.event),
  )
  finishPrimary()
  await Promise.all([primary, recovery])

  expect(fetchMock).toHaveBeenCalledOnce()
  expect(primaryEvents).toEqual(['conversation.completed'])
  expect(replayedEvents).toEqual([])
})
