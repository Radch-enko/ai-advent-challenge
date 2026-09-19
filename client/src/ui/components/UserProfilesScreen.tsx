import { FormEvent, ReactNode, useState } from 'react'
import {
  ApiRequestError,
  createUserProfile,
  deleteUserProfile,
  updateUserProfile,
} from '../../data/api/copiaApi'
import {
  UserProfile,
  UserProfileInput,
  UserProfileLanguage,
  UserProfileResponseFormat,
  UserProfileTone,
  UserProfileVerbosity,
} from '../../domain/models/userProfile'

const empty: UserProfileInput = {
  name: '',
  language: 'auto',
  tone: 'neutral',
  verbosity: 'balanced',
  response_format: ['plain_text'],
  constraints: [],
}

const languageOptions: Array<[UserProfileLanguage, string]> = [
  ['ru', 'Русский'],
  ['en', 'English'],
  ['auto', 'Auto'],
]
const toneOptions: Array<[UserProfileTone, string]> = [
  ['neutral', 'Нейтральный'],
  ['friendly', 'Дружелюбный'],
  ['formal', 'Формальный'],
  ['direct', 'Прямой'],
]
const verbosityOptions: Array<[UserProfileVerbosity, string]> = [
  ['concise', 'Кратко'],
  ['balanced', 'Сбалансированно'],
  ['detailed', 'Подробно'],
]
const formatOptions: Array<[UserProfileResponseFormat, string]> = [
  ['plain_text', 'обычный текст'],
  ['markdown', 'Markdown'],
  ['bullets', 'списки'],
  ['steps', 'пошаговые инструкции'],
  ['tables', 'таблицы'],
  ['code', 'код'],
]

function labelFor<T extends string>(options: Array<[T, string]>, value: T): string {
  return options.find(([key]) => key === value)?.[1] ?? value
}

function profileSummary(profile: UserProfile): string {
  return `${labelFor(languageOptions, profile.language)} язык · ${labelFor(toneOptions, profile.tone)} стиль · ${labelFor(verbosityOptions, profile.verbosity)} · ${profile.response_format.map((format) => labelFor(formatOptions, format)).join(' / ')}`
}

export function UserProfilesScreen({
  profiles,
  loading,
  error,
  selectedId,
  onRetry,
  onChanged,
  onChooseOtherProfile,
  onManageProfiles,
  onCloseState,
}: {
  profiles: UserProfile[]
  loading: boolean
  error: string | null
  selectedId: string | null
  onRetry: () => Promise<boolean>
  onChanged: () => Promise<boolean>
  onChooseOtherProfile: () => void
  onManageProfiles: () => void
  onCloseState: () => void
}) {
  const [editing, setEditing] = useState<UserProfile | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<UserProfileInput>(empty)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [deleteConfirmationId, setDeleteConfirmationId] = useState<string | null>(null)
  const [deleteNotice, setDeleteNotice] = useState<{
    kind: 'in-use' | 'not-found' | 'deleted' | 'error'
    message: string
  } | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [constraintEditor, setConstraintEditor] = useState<number | null>(null)
  const [constraintDraft, setConstraintDraft] = useState('')

  function edit(profile?: UserProfile) {
    setEditing(profile ?? null)
    setFormOpen(true)
    setForm(
      profile
        ? {
            name: profile.name,
            language: profile.language,
            tone: profile.tone,
            verbosity: profile.verbosity,
            response_format: [...profile.response_format],
            constraints: [...profile.constraints],
          }
        : { ...empty, response_format: [...empty.response_format], constraints: [] },
    )
    setFormError(null)
    setRefreshError(null)
    setDeleteNotice(null)
    setSaveSuccess(false)
    setConstraintEditor(null)
    setConstraintDraft('')
  }

  function closeForm() {
    setFormOpen(false)
    setEditing(null)
    setFormError(null)
    setConstraintEditor(null)
    setConstraintDraft('')
  }

  function updateForm<K extends keyof UserProfileInput>(key: K, value: UserProfileInput[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function toggleFormat(format: UserProfileResponseFormat) {
    const selected = form.response_format.includes(format)
    if (selected && form.response_format.length === 1) return
    if (!selected && form.response_format.length >= 3) return
    updateForm(
      'response_format',
      selected
        ? form.response_format.filter((item) => item !== format)
        : [...form.response_format, format],
    )
  }

  function saveConstraint(index: number) {
    const value = constraintDraft.trim()
    if (!value) return
    const constraints = [...form.constraints]
    if (index === constraints.length) constraints.push(value)
    else constraints[index] = value
    updateForm('constraints', constraints)
    setConstraintEditor(null)
    setConstraintDraft('')
  }

  async function save() {
    setSaving(true)
    setFormError(null)
    try {
      if (editing) await updateUserProfile(editing.id, form)
      else await createUserProfile(form)
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : 'Could not save profile')
      setSaving(false)
      return
    }

    closeForm()
    setSaveSuccess(true)
    try {
      const refreshed = await onChanged()
      setRefreshError(refreshed ? null : 'Профиль сохранен, но список не удалось обновить.')
    } catch {
      setRefreshError('Профиль сохранен, но список не удалось обновить.')
    } finally {
      setSaving(false)
    }
  }

  async function retryRefresh() {
    try {
      const refreshed = await onRetry()
      setRefreshError(refreshed ? null : 'Не удалось обновить список профилей.')
    } catch {
      setRefreshError('Не удалось обновить список профилей.')
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    await save()
  }

  async function remove(profile: UserProfile) {
    setDeletingId(profile.id)
    setDeleteNotice(null)
    try {
      await deleteUserProfile(profile.id)
      setDeleteNotice({ kind: 'deleted', message: `Профиль «${profile.name}» удален.` })
      setDeleteConfirmationId(null)
      setRefreshError(null)
      try {
        const refreshed = await onChanged()
        setRefreshError(refreshed ? null : 'Профиль удален, но список не удалось обновить.')
      } catch {
        setRefreshError('Профиль удален, но список не удалось обновить.')
      }
    } catch (caught) {
      const code = caught instanceof ApiRequestError ? caught.errorCode : undefined
      setDeleteNotice(
        code === 'user_profile_in_use'
          ? {
              kind: 'in-use',
              message: 'Профиль используется сохраненной сессией и не может быть удален.',
            }
          : code === 'user_profile_not_found'
            ? {
                kind: 'not-found',
                message: 'Профиль уже удален или больше не существует.',
              }
            : {
                kind: 'error',
                message: caught instanceof Error ? caught.message : 'Не удалось удалить профиль',
              },
      )
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="user-profiles-screen" aria-labelledby="user-profiles-title">
      <header className="profiles-view-header">
        <div>
          <h1 id="user-profiles-title">Профили общения</h1>
          <span className="profiles-status">
            <i /> Персональный контекст
          </span>
        </div>
        <div className="profiles-header-actions" aria-label="Действия профилей">
          <span aria-hidden="true" title="Поиск профиля">
            ⌕
          </span>
          <span aria-hidden="true" title="Дополнительные действия">
            •••
          </span>
        </div>
      </header>

      <div className="profiles-body">
        <header className="profiles-intro">
          <div>
            <h2>Ваши профили</h2>
            <p>
              Профили определяют тон, язык и детализацию ответов ИИ без изменения системных
              инструкций моделей.
            </p>
          </div>
          <button className="profile-primary-button" type="button" onClick={() => edit()}>
            <b>＋</b> Создать профиль
          </button>
        </header>

        {loading && <ProfileState className="profile-loading" title="Загрузка профилей…" />}
        {error && !loading && (
          <ProfileState
            className="profile-error-state"
            title="Не удалось загрузить профили"
            message="Проверьте соединение и повторите попытку."
            action={
              <button type="button" onClick={onRetry}>
                ↻ Повторить
              </button>
            }
          />
        )}
        {!loading && !error && profiles.length === 0 && (
          <ProfileState
            className="profile-empty-state"
            title="Профили не найдены"
            message="Создайте первый профиль общения, чтобы он появился в списке."
          />
        )}
        {!loading && !error && profiles.length > 0 && (
          <div className="user-profiles-list">
            {profiles.map((profile) => (
              <article
                className={`user-profile-card${deletingId === profile.id ? ' is-deleting' : ''}`}
                key={profile.id}
                aria-busy={deletingId === profile.id}
              >
                <header>
                  <div className="profile-card-title">
                    <span className="profile-icon" aria-hidden="true">
                      ♙
                    </span>
                    <strong>{profile.name}</strong>
                    {profile.id === selectedId && (
                      <span className="active-profile-badge">Выбран</span>
                    )}
                  </div>
                  <div className="profile-card-actions">
                    <button
                      type="button"
                      aria-label={`Изменить профиль ${profile.name}`}
                      onClick={() => edit(profile)}
                    >
                      ✎
                    </button>
                    {deleteConfirmationId === profile.id ? (
                      <div className="delete-confirmation">
                        <button
                          type="button"
                          disabled={deletingId !== null}
                          aria-busy={deletingId === profile.id}
                          onClick={() => void remove(profile)}
                        >
                          {deletingId === profile.id ? (
                            <>
                              <span className="inline-spinner" aria-hidden="true" /> Удаление…
                            </>
                          ) : (
                            'Удалить?'
                          )}
                        </button>
                        <button
                          type="button"
                          disabled={deletingId !== null}
                          onClick={() => setDeleteConfirmationId(null)}
                        >
                          Отмена
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className={deletingId === profile.id ? 'is-loading' : undefined}
                        aria-label={`Удалить профиль ${profile.name}`}
                        disabled={deletingId !== null}
                        onClick={() => {
                          setDeleteNotice(null)
                          setDeleteConfirmationId(profile.id)
                        }}
                      >
                        {deletingId === profile.id ? '↻' : '⌫'}
                      </button>
                    )}
                  </div>
                </header>
                <p>{profileSummary(profile)}</p>
                <div className="profile-tags">
                  <span>
                    Язык: <b>{labelFor(languageOptions, profile.language)}</b>
                  </span>
                  <span>
                    Стиль: <b>{labelFor(toneOptions, profile.tone)}</b>
                  </span>
                  <span>
                    Детали: <b>{labelFor(verbosityOptions, profile.verbosity)}</b>
                  </span>
                  <span>
                    Формат:{' '}
                    <b>
                      {profile.response_format
                        .map((format) => labelFor(formatOptions, format))
                        .join(' / ')}
                    </b>
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}

        {selectedId !== null &&
          !loading &&
          !error &&
          !profiles.some((profile) => profile.id === selectedId) && (
            <ProfileState
              className="profile-not-found-state"
              title="Выбранный профиль не найден"
              message="Он мог быть удален в другой сессии. Откройте профиль в composer и выберите другой или очистите выбор."
              action={
                <ProfileStateActions
                  onChooseOtherProfile={onChooseOtherProfile}
                  onManageProfiles={onManageProfiles}
                  onCloseState={onCloseState}
                />
              }
            />
          )}

        {deleteNotice && (
          <div
            className={`profile-mutation-notice ${deleteNotice.kind}`}
            role={deleteNotice.kind === 'deleted' ? 'status' : 'alert'}
          >
            {deleteNotice.message}
            {deleteNotice.kind === 'deleted' ||
            deleteNotice.kind === 'not-found' ||
            deleteNotice.kind === 'in-use' ? (
              <ProfileStateActions
                onChooseOtherProfile={onChooseOtherProfile}
                onManageProfiles={onManageProfiles}
                onCloseState={onCloseState}
              />
            ) : null}
          </div>
        )}

        {formError && !formOpen && (
          <p className="profile-form-error" role="alert">
            {formError}
          </p>
        )}
        {saveSuccess && !formOpen && (
          <p className="profile-success" role="status">
            ✓ Профиль сохранен. Изменения применены к контексту общения.
          </p>
        )}
        {refreshError && !formOpen && (
          <div className="profile-refresh-error" role="alert">
            <span>{refreshError}</span>
            <button type="button" onClick={() => void retryRefresh()} disabled={loading}>
              Повторить обновление
            </button>
          </div>
        )}
        {profiles.length > 0 && !formOpen && (
          <p className="profile-info-banner">
            <span aria-hidden="true">ⓘ</span> Выбранный профиль автоматически передается во все
            новые сессии общения, обеспечивая стабильное качество ответов.
          </p>
        )}

        {formOpen && (
          <form className="user-profile-form" onSubmit={submit}>
            <header>
              <div>
                <h2>{editing ? 'Редактировать профиль' : 'Создать профиль'}</h2>
                <p>
                  {formError
                    ? 'Проверьте данные и попробуйте еще раз.'
                    : 'Новая конфигурация без ошибок'}
                </p>
              </div>
              <button
                type="button"
                className="form-close"
                aria-label="Закрыть форму"
                onClick={closeForm}
              >
                ×
              </button>
            </header>
            <div className="profile-form-body">
              <label
                className={formError?.toLowerCase().includes('name') ? 'has-error' : undefined}
              >
                Название профиля
                <input
                  required
                  maxLength={80}
                  value={form.name}
                  onChange={(event) => updateForm('name', event.target.value)}
                />
              </label>
              <SegmentedField
                label="Язык ответов"
                options={languageOptions}
                value={form.language}
                onChange={(value) => updateForm('language', value)}
              />
              <SegmentedField
                label="Стиль изложения"
                options={toneOptions}
                value={form.tone}
                onChange={(value) => updateForm('tone', value)}
              />
              <SegmentedField
                label="Уровень подробности"
                options={verbosityOptions}
                value={form.verbosity}
                onChange={(value) => updateForm('verbosity', value)}
              />
              <fieldset>
                <legend>Предпочтительный формат</legend>
                <div className="profile-chip-list">
                  {formatOptions.map(([value, label]) => (
                    <button
                      className={form.response_format.includes(value) ? 'selected' : ''}
                      type="button"
                      key={value}
                      onClick={() => toggleFormat(value)}
                      aria-pressed={form.response_format.includes(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend>Пользовательские ограничения</legend>
                <div className="constraints-editor">
                  {form.constraints.map((constraint, index) =>
                    constraintEditor === index ? (
                      <ConstraintEditor
                        key={index}
                        value={constraintDraft}
                        onChange={setConstraintDraft}
                        onSave={() => saveConstraint(index)}
                        onCancel={() => setConstraintEditor(null)}
                      />
                    ) : (
                      <div className="constraint-chip" key={index}>
                        <span>{constraint}</span>
                        <button
                          type="button"
                          aria-label={`Удалить ограничение ${index + 1}`}
                          onClick={() =>
                            updateForm(
                              'constraints',
                              form.constraints.filter((_, item) => item !== index),
                            )
                          }
                        >
                          ×
                        </button>
                        <button
                          type="button"
                          aria-label={`Изменить ограничение ${index + 1}`}
                          onClick={() => {
                            setConstraintEditor(index)
                            setConstraintDraft(constraint)
                          }}
                        >
                          ✎
                        </button>
                      </div>
                    ),
                  )}
                  {constraintEditor === form.constraints.length && (
                    <ConstraintEditor
                      value={constraintDraft}
                      onChange={setConstraintDraft}
                      onSave={() => saveConstraint(form.constraints.length)}
                      onCancel={() => setConstraintEditor(null)}
                    />
                  )}
                  {constraintEditor === null && form.constraints.length < 8 && (
                    <button
                      className="add-constraint"
                      type="button"
                      onClick={() => {
                        setConstraintEditor(form.constraints.length)
                        setConstraintDraft('')
                      }}
                    >
                      ＋ Добавить
                    </button>
                  )}
                </div>
              </fieldset>
              {formError && (
                <div className="profile-form-error" role="alert">
                  <span>{formError}</span>
                  <button type="button" onClick={() => void save()} disabled={saving}>
                    {saving ? 'Повторяем…' : 'Повторить сохранение'}
                  </button>
                </div>
              )}
              <footer>
                <button type="button" className="profile-secondary-button" onClick={closeForm}>
                  Отмена
                </button>
                <button type="submit" className="profile-primary-button" disabled={saving}>
                  {saving ? 'Сохраняем…' : editing ? 'Сохранить изменения' : 'Создать профиль'}
                </button>
              </footer>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}

function ProfileState({
  className,
  title,
  message,
  action,
}: {
  className: string
  title: string
  message?: string
  action?: ReactNode
}) {
  return (
    <section className={`profile-state ${className}`} aria-live="polite">
      <span className="profile-state-icon" aria-hidden="true">
        {className.includes('error') ? '!' : className.includes('loading') ? '↻' : '♙'}
      </span>
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {action}
    </section>
  )
}

function ProfileStateActions({
  onChooseOtherProfile,
  onManageProfiles,
  onCloseState,
}: {
  onChooseOtherProfile: () => void
  onManageProfiles: () => void
  onCloseState: () => void
}) {
  return (
    <div className="profile-state-actions">
      <button type="button" onClick={onChooseOtherProfile}>
        Выбрать другой профиль
      </button>
      <button type="button" onClick={onManageProfiles}>
        Управление профилями
      </button>
      <button type="button" onClick={onCloseState}>
        Закрыть
      </button>
    </div>
  )
}

function SegmentedField<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Array<[T, string]>
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      <div className="segmented-control">
        {options.map(([option, text]) => (
          <button
            className={option === value ? 'selected' : ''}
            type="button"
            key={option}
            onClick={() => onChange(option)}
            aria-pressed={option === value}
          >
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function ConstraintEditor({
  value,
  onChange,
  onSave,
  onCancel,
}: {
  value: string
  onChange: (value: string) => void
  onSave: () => void
  onCancel: () => void
}) {
  return (
    <div className="constraint-editor">
      <input
        autoFocus
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Ограничение"
      />
      <button type="button" onClick={onSave}>
        Сохранить
      </button>
      <button type="button" onClick={onCancel}>
        Отмена
      </button>
    </div>
  )
}
