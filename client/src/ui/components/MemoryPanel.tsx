import { FormEvent, ReactNode, useEffect, useState } from 'react'
import {
  LongTermMemoryItem,
  MemoryEvent,
  PendingMemorySuggestion,
  WorkingMemoryItem,
} from '../../domain/models/memory'

type MemoryValue = Pick<LongTermMemoryItem, 'category' | 'key' | 'value'>

type Props = {
  open: boolean
  profileName?: string | null
  facts: Record<string, string>
  memoryEvents: MemoryEvent[]
  workingMemory: WorkingMemoryItem[]
  pendingMemory: PendingMemorySuggestion[]
  longTermMemory: LongTermMemoryItem[]
  onToggle: () => void
  onClearWorking: () => Promise<void>
  onUndoWorking: () => Promise<void>
  onEditWorking: (item: WorkingMemoryItem) => Promise<void>
  onDeleteWorking: (item: WorkingMemoryItem) => Promise<void>
  onApprovePending: (suggestion: PendingMemorySuggestion) => Promise<void>
  onRejectPending: (suggestion: PendingMemorySuggestion) => Promise<void>
  onAddLongTermMemory: (value: MemoryValue) => Promise<void>
  onEditLongTermMemory: (itemId: string, value: MemoryValue) => Promise<void>
  onDeleteLongTermMemory: (itemId: string) => Promise<void>
}

type MemoryModalProps = {
  children: ReactNode
  onClose: () => void
}

export function MemoryModal({ children, onClose }: MemoryModalProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      className="memory-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Память"
      onClick={onClose}
    >
      <div className="memory-modal" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="memory-modal-close"
          aria-label="Закрыть память"
          onClick={onClose}
        >
          ×
        </button>
        {children}
      </div>
    </div>
  )
}

export function MemoryPanel({
  open,
  profileName,
  facts,
  memoryEvents,
  workingMemory,
  pendingMemory,
  longTermMemory,
  onToggle,
  onClearWorking,
  onUndoWorking,
  onEditWorking,
  onDeleteWorking,
  onApprovePending,
  onRejectPending,
  onAddLongTermMemory,
  onEditLongTermMemory,
  onDeleteLongTermMemory,
}: Props) {
  if (!open) {
    return (
      <button
        type="button"
        className="memory-panel-trigger"
        aria-expanded={false}
        onClick={onToggle}
      >
        Память · {workingMemory.length + longTermMemory.length + pendingMemory.length}
      </button>
    )
  }

  const visibleEvents = memoryEvents.filter(
    (event) => !(event.scope === 'short_term' && event.action === 'saved'),
  )

  return (
    <section className="memory-panel" aria-label="Memory panel">
      <button
        type="button"
        className="memory-panel-heading"
        aria-expanded={true}
        onClick={onToggle}
      >
        <span>
          <b>Память</b>
          <small>Слои контекста и предложения</small>
        </span>
        <span aria-hidden="true">⌃</span>
      </button>
      <div
        className={`memory-section working-memory-section ${workingMemory.length ? '' : 'compact'}`}
      >
        <header>
          <b>Working memory · {workingMemory.length}</b>
          <span>
            <button
              type="button"
              className="memory-action"
              disabled={workingMemory.length === 0}
              onClick={() => void onClearWorking()}
            >
              Clear
            </button>
            <button type="button" className="memory-action" onClick={() => void onUndoWorking()}>
              Undo last automatic change
            </button>
          </span>
        </header>
        {workingMemory.map((item) => (
          <div className="memory-item" key={item.id}>
            <code>{item.key}</code>
            <span>{item.value}</span>
            <button
              type="button"
              className="memory-action"
              onClick={() => void onDeleteWorking(item)}
            >
              Delete
            </button>
            <button
              type="button"
              className="memory-action"
              onClick={() => void onEditWorking(item)}
            >
              Edit
            </button>
          </div>
        ))}
        {workingMemory.length === 0 && <p>Working memory is empty</p>}
      </div>

      <section className="memory-section saved-memory-section">
        <header>
          <b>Long-term memory · {longTermMemory.length}</b>
          <span>{profileName ? 'Профиль · сохранено' : 'Недоступна без профиля'}</span>
        </header>
        {profileName ? (
          <LongTermMemoryEditor
            items={longTermMemory}
            onAdd={onAddLongTermMemory}
            onEdit={onEditLongTermMemory}
            onDelete={onDeleteLongTermMemory}
          />
        ) : (
          <p>Long-term memory доступна только для профильного чата</p>
        )}
      </section>

      <section
        className={`memory-section pending-memory-section ${pendingMemory.length ? '' : 'compact'}`}
      >
        <header>
          <b>Pending suggestions · {pendingMemory.length}</b>
          <span>Не сохранено</span>
        </header>
        {pendingMemory.map((suggestion) => (
          <div className="memory-item pending-memory-item" key={suggestion.id}>
            <div>
              <strong>Предложение · {suggestion.candidate.action}</strong>
              <span>
                {suggestion.candidate.category} · {suggestion.candidate.key}
              </span>
              <small>{suggestion.candidate.reason}</small>
            </div>
            {profileName && (
              <button
                type="button"
                className="memory-action"
                onClick={() => void onApprovePending(suggestion)}
              >
                Approve
              </button>
            )}
            <button
              type="button"
              className="memory-action"
              onClick={() => void onRejectPending(suggestion)}
            >
              Reject
            </button>
          </div>
        ))}
        {pendingMemory.length === 0 && <p>Нет предложений для сохранения</p>}
      </section>

      <FactsSection facts={facts} />
      {visibleEvents.length > 0 && <MemoryEvents events={visibleEvents} />}
    </section>
  )
}

export function LongTermMemoryEditor({
  items,
  onAdd,
  onEdit,
  onDelete,
}: {
  items: LongTermMemoryItem[]
  onAdd: (value: MemoryValue) => Promise<void>
  onEdit: (itemId: string, value: MemoryValue) => Promise<void>
  onDelete: (itemId: string) => Promise<void>
}) {
  const [draft, setDraft] = useState<MemoryValue>({ category: 'profile', key: '', value: '' })
  const [editing, setEditing] = useState<LongTermMemoryItem | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.key.trim() || !draft.value.trim()) return
    await onAdd({ ...draft, key: draft.key.trim(), value: draft.value.trim() })
    setDraft({ category: 'profile', key: '', value: '' })
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault()
    if (!editing || !editing.key.trim() || !editing.value.trim()) return
    await onEdit(editing.id, {
      category: editing.category,
      key: editing.key.trim(),
      value: editing.value.trim(),
    })
    setEditing(null)
  }

  return (
    <div className="saved-memory-content">
      {items.map((item) => (
        <div className="memory-item" key={item.id}>
          <code>
            {item.category} · {item.key}
          </code>
          <span>{item.value}</span>
          <button type="button" className="memory-action" onClick={() => setEditing(item)}>
            Изменить
          </button>
          <button type="button" className="memory-action" onClick={() => void onDelete(item.id)}>
            Удалить
          </button>
        </div>
      ))}
      {!items.length && <p>Долгосрочная память пока пуста</p>}
      <form onSubmit={(event) => void submit(event)}>
        <select
          value={draft.category}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              category: event.target.value as LongTermMemoryItem['category'],
            }))
          }
        >
          <option value="decision">Decision</option>
          <option value="profile">Profile</option>
          <option value="knowledge">Knowledge</option>
        </select>
        <input
          value={draft.key}
          maxLength={80}
          placeholder="key"
          onChange={(event) => setDraft((current) => ({ ...current, key: event.target.value }))}
        />
        <textarea
          value={draft.value}
          maxLength={1000}
          placeholder="value"
          onChange={(event) => setDraft((current) => ({ ...current, value: event.target.value }))}
        />
        <button type="submit">Добавить</button>
      </form>
      {editing && (
        <form onSubmit={(event) => void saveEdit(event)}>
          <select
            value={editing.category}
            onChange={(event) =>
              setEditing({
                ...editing,
                category: event.target.value as LongTermMemoryItem['category'],
              })
            }
          >
            <option value="decision">Decision</option>
            <option value="profile">Profile</option>
            <option value="knowledge">Knowledge</option>
          </select>
          <input
            value={editing.key}
            onChange={(event) => setEditing({ ...editing, key: event.target.value })}
          />
          <textarea
            value={editing.value}
            onChange={(event) => setEditing({ ...editing, value: event.target.value })}
          />
          <button type="submit">Сохранить</button>
          <button type="button" onClick={() => setEditing(null)}>
            Отмена
          </button>
        </form>
      )}
    </div>
  )
}

function FactsSection({ facts }: { facts: Record<string, string> }) {
  const entries = Object.entries(facts)
  return (
    <section className="memory-section facts-memory-section">
      <header>
        <b>Sticky Facts · {entries.length}</b>
      </header>
      {entries.length ? (
        entries.map(([key, value]) => (
          <div className="memory-item" key={key}>
            <code>{key}</code>
            <span>{value}</span>
          </div>
        ))
      ) : (
        <p>Факты пока пусты</p>
      )}
    </section>
  )
}

function MemoryEvents({ events }: { events: MemoryEvent[] }) {
  return (
    <section className="memory-section memory-events-section">
      <header>
        <b>Memory events · {events.length}</b>
      </header>
      {events.map((event) => (
        <div className="memory-item" key={event.id}>
          <strong>
            {event.scope} · {event.action}
          </strong>
          {event.key && <span>{event.key}</span>}
          {event.message && <small>{event.message}</small>}
        </div>
      ))}
    </section>
  )
}
