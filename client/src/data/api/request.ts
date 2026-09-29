import type { FactsUpdateEvent, SummarizationEvent } from '../../domain/models/chat'

export type ApiResult<T> = { data: T; status: number }

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(apiErrorMessage(body, status))
  }

  get errorCode(): string | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    return typeof detail === 'object' &&
      detail !== null &&
      'code' in detail &&
      typeof detail.code === 'string'
      ? detail.code
      : undefined
  }

  get summarizationEvent(): SummarizationEvent | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    if (typeof detail !== 'object' || detail === null || !('summarization_event' in detail)) {
      return undefined
    }
    return detail.summarization_event as SummarizationEvent
  }

  get factsEvent(): FactsUpdateEvent | undefined {
    if (typeof this.body !== 'object' || this.body === null || !('detail' in this.body)) {
      return undefined
    }
    const detail = this.body.detail
    if (typeof detail !== 'object' || detail === null || !('facts_event' in detail)) {
      return undefined
    }
    return detail.facts_event as FactsUpdateEvent
  }
}

function apiErrorMessage(body: unknown, status: number): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return `Request failed with status ${status}`
  }
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    return String(detail.message)
  }
  return `Request failed with status ${status}`
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestWithMeta<T>(path, init)).data
}

async function requestWithMeta<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiRequestError(response.status, body)
  }
  return {
    data: response.status === 204 ? (undefined as T) : ((await response.json()) as T),
    status: response.status,
  }
}
