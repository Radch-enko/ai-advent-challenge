import { defaultContextManagement } from '../../configuration/application/configDefaults'
import { KeyboardEvent, useEffect, useRef } from 'react'
import { ContextManagementConfig } from '../../../domain/models/agent'
import { Provider } from '../../../domain/models/provider'
import {
  ChatMessage,
  FactsUpdateEvent,
  SummarizationEvent,
  TokenUsage,
} from '../../../domain/models/chat'

export function normalizeContextManagement(
  value: ContextManagementConfig | undefined,
  provider: Provider,
  model: string,
): ContextManagementConfig {
  if (!value) return defaultContextManagement(provider, model)
  const defaults = defaultContextManagement(provider, model)
  const factsUpdater = value.facts_updater ?? defaults.facts_updater
  return {
    ...value,
    strategy: value.strategy ?? 'summary',
    recent_message_limit: value.recent_message_limit ?? 10,
    summarizer: {
      ...value.summarizer,
      provider: value.summarizer.provider ?? provider,
      model: value.summarizer.model ?? model,
      generation: { ...value.summarizer.generation },
    },
    facts_updater: {
      ...factsUpdater,
      provider: factsUpdater.provider ?? provider,
      model: factsUpdater.model ?? model,
      generation: { ...factsUpdater.generation },
    },
  }
}

export function transcriptLength(messages: ChatMessage[]) {
  return messages.filter((message) => message.transcriptIndex != null).length
}

export function upsertSummarizationEvents(
  current: SummarizationEvent[],
  updates: SummarizationEvent[],
) {
  const replacements = new Map(updates.map((event) => [event.id, event]))
  const merged = current.map((event) => replacements.get(event.id) ?? event)
  const existingIds = new Set(current.map((event) => event.id))
  return [...merged, ...updates.filter((event) => !existingIds.has(event.id))]
}

export function upsertFactsEvents(current: FactsUpdateEvent[], updates: FactsUpdateEvent[]) {
  const replacements = new Map(updates.map((event) => [event.id, event]))
  const merged = current.map((event) => replacements.get(event.id) ?? event)
  const existingIds = new Set(current.map((event) => event.id))
  return [...merged, ...updates.filter((event) => !existingIds.has(event.id))]
}

export function willSummarize(
  messageCount: number,
  events: SummarizationEvent[],
  config: ContextManagementConfig,
) {
  if (!config.enabled || config.strategy !== 'summary') return false
  const summarizedMessageCount = events
    .filter((event) => event.status === 'completed')
    .reduce((total, event) => total + event.message_count, 0)
  return (
    messageCount - summarizedMessageCount - config.recent_exchange_limit * 2 >=
    config.summary_batch_exchange_count * 2
  )
}

export function now() {
  return formatMessageTimestamp(new Date())
}

export function formatMessageTimestamp(value: string | Date | null | undefined) {
  const date = value instanceof Date ? value : value ? new Date(value) : null
  if (date == null || Number.isNaN(date.getTime())) return ''

  const current = new Date()
  const time = new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
  if (
    date.getFullYear() === current.getFullYear() &&
    date.getMonth() === current.getMonth() &&
    date.getDate() === current.getDate()
  ) {
    return `Сегодня, ${time}`
  }

  const day = new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date)
  return `${day}, ${time}`
}

export function formatTokens(value?: number) {
  return value == null ? '—' : new Intl.NumberFormat('ru-RU').format(value)
}

export function formatPercentage(value: number) {
  return `${value < 0.1 && value > 0 ? value.toFixed(2) : value.toFixed(1)}%`
}

export function contextTokenCount(usage?: TokenUsage | null) {
  if (!usage) return undefined
  if (usage.prompt_tokens != null && usage.completion_tokens != null)
    return usage.prompt_tokens + usage.completion_tokens
  return usage.total_tokens
}

export function contextUsageLabel(usage?: TokenUsage | null, contextWindow?: number | null) {
  const used = contextTokenCount(usage)
  if (used == null || !contextWindow) return undefined
  return `${formatTokens(used)} / ${formatTokens(contextWindow)} · ${formatPercentage(Math.min(100, (used / contextWindow) * 100))}`
}

export function resizeTextArea(element: HTMLTextAreaElement | null) {
  if (!element) return
  element.style.height = '0px'
  element.style.height = `${Math.min(element.scrollHeight, 180)}px`
}

export function handleComposerKeyDown(
  event: KeyboardEvent<HTMLTextAreaElement>,
  form: HTMLFormElement | null,
) {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  form?.requestSubmit()
}

export function useOutsideClose(isOpen: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const closeIfOutside = (event: MouseEvent) => {
      if (event.target instanceof Node && !ref.current?.contains(event.target)) onClose()
    }
    document.addEventListener('mousedown', closeIfOutside)
    return () => document.removeEventListener('mousedown', closeIfOutside)
  }, [isOpen, onClose])
  return ref
}

export function supportsSamplingParameters(provider: Provider, model: string): boolean {
  if (provider === 'gigachat' || provider === 'ollama') return true
  const normalized = model.trim().toLowerCase()
  const unsupportedPrefixes = [
    'gpt-5-mini-',
    'gpt-5-nano-',
    'gpt-5.1',
    'gpt-5.2',
    'gpt-6',
    'o1',
    'o3',
    'o4',
  ]
  return (
    !['gpt-5', 'gpt-5-mini', 'gpt-5-nano'].includes(normalized) &&
    !unsupportedPrefixes.some((prefix) => normalized.startsWith(prefix))
  )
}

export function isSafeMarkdownHref(value: string): boolean {
  try {
    const url = new URL(value, 'https://copia.local')
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}
