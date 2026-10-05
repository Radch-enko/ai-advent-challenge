import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { mapStoredMessages } from '../src/features/chat/application/sessionTranscript'
import { ExecutionSummary } from '../src/features/chat/ui/ExecutionSummary'

describe('session transcript RAG diagnostics', () => {
  it('unwraps a recognized legacy RAG response and keeps arbitrary JSON intact', () => {
    const legacyAnswer = JSON.stringify({
      answer_mode: 'grounded',
      answer: '**Readable answer**',
      citations: [{ chunk_id: 'guide-1', quote: 'a short quote' }],
    })
    const arbitraryJson = JSON.stringify({ answer: 'not a RAG envelope' })
    const extendedJson = JSON.stringify({
      answer_mode: 'grounded',
      answer: 'Keep the full payload',
      citations: [],
      extra: true,
    })

    const messages = mapStoredMessages([
      { role: 'assistant', content: legacyAnswer },
      { role: 'assistant', content: arbitraryJson },
      { role: 'assistant', content: extendedJson },
      {
        role: 'assistant',
        content: 'Saved answer',
        rag_enabled: true,
        rewritten_query: 'normalized search query',
      },
    ])

    expect(messages[0].content).toBe('**Readable answer**')
    expect(messages[1].content).toBe(arbitraryJson)
    expect(messages[2].content).toBe(extendedJson)
    expect(messages[3]).toMatchObject({ ragEnabled: true, rewrittenQuery: 'normalized search query' })
  })

  it('shows enabled, disabled, and unrecorded states with the rewritten query', () => {
    const enabled = renderToStaticMarkup(
      <ExecutionSummary
        showRagDiagnostics
        ragEnabled
        rewrittenQuery="normalized search query"
      />,
    )
    const disabled = renderToStaticMarkup(
      <ExecutionSummary showRagDiagnostics ragEnabled={false} />,
    )
    const legacy = renderToStaticMarkup(<ExecutionSummary showRagDiagnostics />)

    expect(enabled).toContain('RAG: enabled')
    expect(enabled).toContain('Переписанный запрос:')
    expect(enabled).toContain('normalized search query')
    expect(disabled).toContain('RAG: disabled')
    expect(disabled).not.toContain('Переписанный запрос:')
    expect(legacy).toContain('RAG: not recorded')
  })
})
