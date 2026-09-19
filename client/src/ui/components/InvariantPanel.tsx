import { FormEvent, useState } from 'react'
import { Invariant, InvariantInput } from '../../domain/models/invariant'

type Props = {
  items: Invariant[]
  onAdd: (value: InvariantInput) => Promise<void>
  onEdit: (itemId: string, value: InvariantInput) => Promise<void>
  onDelete: (itemId: string) => Promise<void>
}

export function InvariantPanel({ items, onAdd, onEdit, onDelete }: Props) {
  const [draft, setDraft] = useState<InvariantInput>({ name: '', text: '' })
  const [editing, setEditing] = useState<Invariant | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) {
      setError('Введите название инварианта')
      return
    }
    if (!draft.text.trim()) {
      setError('Введите текст инварианта')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onAdd({ name: draft.name.trim(), text: draft.text.trim() })
      setDraft({ name: '', text: '' })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось сохранить инвариант')
    } finally {
      setSaving(false)
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault()
    if (!editing?.name.trim()) {
      setError('Введите название инварианта')
      return
    }
    if (!editing.text.trim()) {
      setError('Введите текст инварианта')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onEdit(editing.id, {
        name: editing.name.trim(),
        text: editing.text.trim(),
      })
      setEditing(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось обновить инвариант')
    } finally {
      setSaving(false)
    }
  }

  async function deleteItem(item: Invariant) {
    setSaving(true)
    setError(null)
    try {
      await onDelete(item.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось удалить инвариант')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="invariant-panel" aria-label="Инварианты">
      <header className="invariant-panel-heading">
        <div>
          <b>Инварианты</b>
          <small>Правила, которые Copia не нарушает</small>
        </div>
        <span className="invariant-count">{items.length} активных</span>
      </header>
      <p className="invariant-explanation">
        Инварианты применяются к каждому запросу Copia, включая новые чаты и агентов, и хранятся
        отдельно от истории диалогов.
      </p>
      <div className="invariant-list">
        {items.map((item) => (
          <article className="invariant-item" key={item.id}>
            <div>
              <span className="invariant-name">{item.name}</span>
              <p>{item.text}</p>
            </div>
            <div className="invariant-actions">
              <button type="button" disabled={saving} onClick={() => setEditing(item)}>
                Изменить
              </button>
              <button type="button" disabled={saving} onClick={() => void deleteItem(item)}>
                Удалить
              </button>
            </div>
          </article>
        ))}
        {!items.length && (
          <div className="invariant-empty">
            <b>Инварианты ещё не заданы</b>
            <span>Добавьте правила, которые Copia должна соблюдать во всех чатах.</span>
          </div>
        )}
      </div>
      <form className="invariant-form" onSubmit={(event) => void submit(event)}>
        <label>
          Название
          <input
            value={draft.name}
            maxLength={80}
            disabled={saving}
            placeholder="Например: Выбранная архитектура"
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
          />
        </label>
        <label>
          Текст инварианта
          <textarea
            value={draft.text}
            maxLength={400}
            disabled={saving}
            placeholder="Например: Backend остаётся на Python и FastAPI"
            onChange={(event) => setDraft((current) => ({ ...current, text: event.target.value }))}
            rows={3}
          />
        </label>
        <button className="invariant-submit" type="submit" disabled={saving}>
          {saving ? 'Сохраняем…' : 'Добавить инвариант'}
        </button>
      </form>
      {editing && (
        <form className="invariant-edit-form" onSubmit={(event) => void saveEdit(event)}>
          <b>Редактирование инварианта</b>
          <input
            value={editing.name}
            maxLength={80}
            disabled={saving}
            aria-label="Название инварианта"
            onChange={(event) => setEditing({ ...editing, name: event.target.value })}
          />
          <textarea
            value={editing.text}
            maxLength={400}
            disabled={saving}
            aria-label="Текст инварианта"
            onChange={(event) => setEditing({ ...editing, text: event.target.value })}
            rows={3}
          />
          <div>
            <button type="submit" disabled={saving}>
              Сохранить
            </button>
            <button type="button" disabled={saving} onClick={() => setEditing(null)}>
              Отмена
            </button>
          </div>
        </form>
      )}
      {error && <p className="invariant-error">{error}</p>}
    </section>
  )
}
