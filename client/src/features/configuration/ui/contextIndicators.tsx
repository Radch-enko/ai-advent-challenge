import { TokenUsageSummary } from '../../chat/ui/chatAppComponents'
import { FactsUpdateEvent, SummarizationEvent } from '../../../domain/models/chat'

export function SummarizationIndicator({
  event,
  retrying,
  onRetry,
}: {
  event: SummarizationEvent
  retrying: boolean
  onRetry: () => void
}) {
  const failed = event.status === 'failed'
  return (
    <div className={`summarization-event ${event.status}`}>
      <span className="summary-event-icon">{failed ? '!' : '✓'}</span>
      <div>
        <b>
          {failed
            ? 'Не удалось сжать контекст'
            : `Сжато пар: ${event.message_count / 2} (${event.message_count} сообщений)`}
        </b>
        <span>{failed ? event.error : `${event.provider} · ${event.model}`}</span>
      </div>
      {event.usage && <TokenUsageSummary usage={event.usage} />}
      {failed && (
        <button className="summary-retry" disabled={retrying} onClick={onRetry}>
          {retrying ? 'Повторяем…' : 'Retry'}
        </button>
      )}
    </div>
  )
}

export function FactsUpdateIndicator({ event }: { event: FactsUpdateEvent }) {
  const failed = event.status === 'failed'
  const changed = Object.keys(event.updates).length
  return (
    <div className={`summarization-event facts-event ${event.status}`}>
      <span className="summary-event-icon">{failed ? '!' : '✓'}</span>
      <div>
        <b>
          {failed
            ? 'Не удалось обновить facts'
            : `Facts обновлены: ${changed}, удалены: ${event.deletions.length}`}
        </b>
        <span>{failed ? event.error : `${event.provider} · ${event.model}`}</span>
      </div>
      {event.usage && <TokenUsageSummary usage={event.usage} />}
    </div>
  )
}
