import { formatTokens, formatPercentage, contextTokenCount } from '../application/conversationUtils'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { isSafeMarkdownHref } from '../application/conversationUtils'
import { UserProfile } from '../../../domain/models/userProfile'
import { TokenUsage } from '../../../domain/models/chat'

export function TokenUsageSummary({ usage }: { usage: TokenUsage }) {
  return (
    <span className="token-usage">
      Input {formatTokens(usage.prompt_tokens)}
      {usage.cached_prompt_tokens != null && (
        <> · Cached {formatTokens(usage.cached_prompt_tokens)}</>
      )}
      {' · '}Output {formatTokens(usage.completion_tokens)} · Total{' '}
      {formatTokens(usage.total_tokens)}
    </span>
  )
}

export function ProfileIndicator({
  profiles,
  selectedId,
  loading,
  error,
  onSelect,
  onManage,
  selectionError,
  selectionLoading,
  onRetrySelection,
  onRetryProfiles,
  sessionRefreshError,
  onRetrySessionRefresh,
}: {
  profiles: UserProfile[]
  selectedId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string | null) => void
  onManage: () => void
  selectionError: string | null
  selectionLoading: boolean
  onRetrySelection: () => void
  onRetryProfiles: () => void
  sessionRefreshError: string | null
  onRetrySessionRefresh: () => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const firstOptionRef = useRef<HTMLButtonElement>(null)
  const clearOptionRef = useRef<HTMLButtonElement>(null)
  const selected = profiles.find((profile) => profile.id === selectedId)
  const selectedProfileMissing = selectedId !== null && selected === undefined
  const popoverId = 'user-profile-popover'
  const triggerLabel = loading
    ? 'Профиль пользователя: загрузка'
    : selectionLoading
      ? 'Профиль пользователя: сохраняется'
      : error !== null
        ? 'Профиль пользователя: список недоступен'
        : selectionError !== null
          ? 'Профиль пользователя: выбор не сохранен'
          : selectedProfileMissing
            ? 'Профиль пользователя: выбранный профиль недоступен'
            : sessionRefreshError !== null
              ? 'Профиль пользователя: список сессий не обновлен'
              : `Профиль пользователя: ${selected?.name ?? 'Без профиля'}`
  const triggerText = loading
    ? 'Загрузка профиля…'
    : selectionLoading
      ? 'Сохраняем…'
      : error !== null
        ? 'Список недоступен'
        : selectionError !== null
          ? 'Выбор не сохранен'
          : selectedProfileMissing
            ? 'Профиль недоступен'
            : sessionRefreshError !== null
              ? 'Сессии не обновлены'
              : (selected?.name ?? 'Без профиля')

  useEffect(() => {
    if (!open) return
    const firstFocusable = firstOptionRef.current ?? clearOptionRef.current
    firstFocusable?.focus()
  }, [open])

  function closePopover() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  return (
    <span className="user-profile-indicator">
      <button
        type="button"
        className="model-indicator"
        ref={triggerRef}
        aria-label={triggerLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={popoverId}
        aria-invalid={error !== null || selectionError !== null || selectedProfileMissing}
        aria-busy={loading || selectionLoading}
        title={selectedProfileMissing ? 'Выбранный профиль недоступен' : undefined}
        onClick={() => {
          if (open) {
            closePopover()
          } else {
            setOpen(true)
          }
        }}
      >
        {triggerText}
      </button>
      {open && (
        <span
          id={popoverId}
          className="user-profile-popover"
          role="dialog"
          aria-label="Выбор профиля"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              closePopover()
            }
          }}
        >
          <section className="user-profile-section user-profile-summary">
            <h2>Активный профиль</h2>
            <span>
              {selected
                ? `${selected.name} · ${selected.language} · ${selected.tone} · ${selected.verbosity}`
                : selectedProfileMissing
                  ? 'Профиль недоступен'
                  : 'Без профиля'}
            </span>
          </section>
          <div className="user-profile-separator" role="separator" />
          {loading && <p className="user-profile-state">Загрузка профилей…</p>}
          {error && (
            <div className="user-profile-state error" role="alert">
              <span>Не удалось загрузить список профилей.</span>
              <button type="button" onClick={onRetryProfiles} disabled={loading}>
                Повторить
              </button>
            </div>
          )}
          {selectionError && (
            <div className="user-profile-state error" role="alert">
              <span>{selectionError}</span>
              <button type="button" onClick={onRetrySelection} disabled={selectionLoading}>
                {selectionLoading ? 'Повторяем…' : 'Повторить выбор'}
              </button>
            </div>
          )}
          {selectedProfileMissing && !loading && !error && (
            <div className="user-profile-state missing" role="alert">
              <span>Выбранный профиль больше недоступен.</span>
              <button type="button" onClick={() => onSelect(null)} disabled={selectionLoading}>
                Очистить выбор
              </button>
            </div>
          )}
          {sessionRefreshError && (
            <div className="user-profile-state refresh-error" role="alert">
              <span>{sessionRefreshError}</span>
              <button type="button" onClick={onRetrySessionRefresh}>
                Обновить список сессий
              </button>
            </div>
          )}
          <section className="user-profile-section user-profile-quick-select">
            <h2>Быстрый выбор</h2>
            {!loading && !error && profiles.length === 0 && (
              <p className="user-profile-state">Нет профилей. Можно продолжить без профиля.</p>
            )}
            {!loading &&
              !error &&
              profiles.length > 0 &&
              profiles.map((profile) => (
                <span className="user-profile-option" key={profile.id}>
                  <button
                    type="button"
                    ref={profile === profiles[0] ? firstOptionRef : undefined}
                    aria-pressed={profile.id === selectedId}
                    disabled={selectionLoading}
                    onClick={() => {
                      onSelect(profile.id)
                      closePopover()
                    }}
                  >
                    <strong>{profile.name}</strong>
                    <small>
                      {profile.language} · {profile.tone} · {profile.verbosity} ·{' '}
                      {profile.response_format.join(', ')} · constraints:{' '}
                      {profile.constraints.length}
                    </small>
                  </button>
                </span>
              ))}
          </section>
          <div className="user-profile-separator" role="separator" />
          <footer className="user-profile-footer">
            <button
              type="button"
              ref={clearOptionRef}
              aria-pressed={selectedId === null}
              disabled={selectionLoading}
              onClick={() => {
                onSelect(null)
                closePopover()
              }}
            >
              Без профиля
            </button>
            <button
              type="button"
              onClick={() => {
                closePopover()
                onManage()
              }}
            >
              Управление профилями
            </button>
          </footer>
        </span>
      )}
    </span>
  )
}

export function ContextProgress({
  usage,
  contextWindow,
}: {
  usage: TokenUsage
  contextWindow?: number | null
}) {
  const used = contextTokenCount(usage) ?? 0
  if (!contextWindow) return null
  const percentage = Math.min(100, (used / contextWindow) * 100)
  const level = percentage >= 95 ? 'critical' : percentage >= 80 ? 'warning' : ''
  const label = `${formatTokens(used)} / ${formatTokens(contextWindow)} · ${formatPercentage(percentage)}`
  return (
    <span
      className={`context-progress ${level}`}
      role="progressbar"
      aria-label={`Заполнение контекстного окна: ${label}`}
      aria-valuemin={0}
      aria-valuemax={contextWindow}
      aria-valuenow={Math.min(used, contextWindow)}
    >
      <i style={{ width: `${percentage}%` }} />
    </span>
  )
}

export function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => (isSafeMarkdownHref(url) ? url : '')}
      components={{
        a: ({ node, ...props }) => {
          void node
          return <a {...props} target="_blank" rel="noreferrer" />
        },
        img: ({ node, ...props }) => {
          void node
          return <img {...props} loading="lazy" className="message-image" />
        },
        table: ({ node, ...props }) => {
          void node
          return (
            <div className="markdown-table-wrapper">
              <table {...props} />
            </div>
          )
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
