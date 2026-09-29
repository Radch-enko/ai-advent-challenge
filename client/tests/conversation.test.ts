import { describe, expect, it } from 'vitest'
import { parseSseBlock } from '../src/data/api/conversationStream'
import {
  initialConversationState,
  reduceConversationEvent,
} from '../src/domain/models/conversation'

describe('conversation event stream', () => {
  it('parses typed events and accumulates text incrementally', () => {
    const first = parseSseBlock('id: c:1\nevent: message.delta\ndata: {"text":"Hi "}')!
    const second = parseSseBlock('id: c:2\nevent: message.delta\ndata: {"text":"there"}')!
    let state = reduceConversationEvent(initialConversationState(), first)
    state = reduceConversationEvent(state, second)
    expect(state.text).toBe('Hi there')
    expect(state.lastEventId).toBe('c:2')
  })

  it('tracks tool and approval lifecycle and ignores replayed IDs', () => {
    let state = initialConversationState()
    state = reduceConversationEvent(state, {
      id: 'c:1',
      event: 'tool.approval_required',
      data: { approval_id: 'a' },
    })
    state = reduceConversationEvent(state, {
      id: 'c:2',
      event: 'tool.running',
      data: { tool_name: 'search' },
    })
    expect(state.approval).toBeNull()
    expect(state.tools.search.status).toBe('running')
    expect(
      reduceConversationEvent(state, {
        id: 'c:2',
        event: 'tool.completed',
        data: { tool_name: 'search' },
      }),
    ).toBe(state)
  })

  it('records terminal success and safe failure', () => {
    const completed = reduceConversationEvent(initialConversationState(), {
      id: 'c:1',
      event: 'conversation.completed',
      data: { result: { ok: true } },
    })
    const failed = reduceConversationEvent(initialConversationState(), {
      id: 'c:1',
      event: 'conversation.failed',
      data: { message: 'Provider failed' },
    })
    expect(completed.status).toBe('completed')
    expect(failed.status).toBe('failed')
    expect(failed.error).toBe('Provider failed')
  })
})
