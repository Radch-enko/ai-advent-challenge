import { Provider } from './provider'

export type AgentConfig = {
  name: string
  description?: string
  avatar_path?: string
  provider: Provider
  model: string
  system_prompt?: string
  generation: {
    max_output_tokens?: number
    temperature?: number
    top_p?: number
  }
  structured_output?: {
    schema: Record<string, unknown>
    strict: boolean
  }
  context_management: ContextManagementConfig
}

export type CompletionConfig = Omit<
  AgentConfig,
  'name' | 'description' | 'avatar_path' | 'context_management'
>

export type ContextStrategy = 'summary' | 'sliding_window' | 'sticky_facts' | 'branching'

export type ContextManagementConfig = {
  enabled: boolean
  strategy: ContextStrategy
  recent_message_limit: number
  recent_exchange_limit: number
  summary_batch_exchange_count: number
  summarizer: {
    provider?: Provider | null
    model?: string | null
    prompt: string
    generation: {
      max_output_tokens?: number
      temperature?: number
      top_p?: number
    }
  }
  facts_updater: {
    provider?: Provider | null
    model?: string | null
    prompt: string
    generation: {
      max_output_tokens?: number
      temperature?: number
      top_p?: number
    }
  }
}
