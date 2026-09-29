import { afterEach, describe, expect, it, vi } from 'vitest'
import { resumeActiveConversations } from '../src/data/api/conversationStream'

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

describe('conversation reload recovery', () => {
  it('replays from the beginning by request ID and clears terminal streams', async () => {
    const storage = new MemoryStorage()
    storage.setItem(
      'copia.activeConversations.session-id',
      JSON.stringify([
        {
          request_id: 'original-request',
          conversation_id: null,
          last_event_id: 'conversation-id:2',
        },
      ]),
    )
    vi.stubGlobal('sessionStorage', storage)
    const responseText = [
      'id: conversation-id:1\nevent: conversation.started\ndata: {"conversation_id":"conversation-id","request_id":"original-request"}\n\n',
      'id: conversation-id:2\nevent: message.delta\ndata: {"text":"Hello"}\n\n',
      'id: conversation-id:3\nevent: conversation.completed\ndata: {"result":{}}\n\n',
    ].join('')
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const command = JSON.parse(String(init.body))
      expect(command).toEqual({
        command: 'resume',
        request_id: 'original-request',
        conversation_id: null,
        after_event_id: null,
      })
      return new Response(responseText, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const events: string[] = []

    await resumeActiveConversations('session-id', (event) => events.push(event.event))

    expect(events).toEqual(['conversation.started', 'message.delta', 'conversation.completed'])
    expect(storage.getItem('copia.activeConversations.session-id')).toBe('[]')
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
