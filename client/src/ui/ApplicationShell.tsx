import { ReactNode } from 'react'
import { ChatSessionSummary } from '../domain/models/session'

export type AppMode =
  'chat' | 'agents' | 'profiles' | 'documents' | 'invariants' | 'mcp' | 'summaries'

type Props = {
  mode: AppMode
  sidebarCollapsed: boolean
  sessions: ChatSessionSummary[]
  activeSessionId: string | null
  profileControl: ReactNode
  children: ReactNode
  onNewChat: () => void
  onNavigate: (mode: AppMode) => void
  onOpenInvariants: () => void
  onToggleSidebar: (collapsed: boolean) => void
  onOpenSession: (sessionId: string) => void
  onRemoveSession: (sessionId: string) => void
}

export function ApplicationShell({
  mode,
  sidebarCollapsed,
  sessions,
  activeSessionId,
  profileControl,
  children,
  onNewChat,
  onNavigate,
  onOpenInvariants,
  onToggleSidebar,
  onOpenSession,
  onRemoveSession,
}: Props) {
  return (
    <main className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {!sidebarCollapsed && (
        <aside className="sidebar" aria-label="Навигация Copia">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              ◇
            </div>
            <strong>Copia</strong>
            <button
              type="button"
              className="sidebar-collapse"
              aria-label="Скрыть навигацию"
              title="Скрыть навигацию"
              onClick={() => onToggleSidebar(true)}
            >
              ‹
            </button>
          </div>
          <nav className="primary-nav" aria-label="Основная навигация">
            <button
              type="button"
              className={`new-chat ${mode === 'chat' ? 'active' : ''}`}
              aria-current={mode === 'chat' ? 'page' : undefined}
              onClick={onNewChat}
            >
              <b aria-hidden="true">＋</b> Новый чат
            </button>
            <button
              type="button"
              className={`agents-nav ${mode === 'agents' ? 'active' : ''}`}
              aria-current={mode === 'agents' ? 'page' : undefined}
              onClick={() => onNavigate('agents')}
            >
              Агенты
            </button>
            <button
              type="button"
              className={`agents-nav ${mode === 'profiles' ? 'active' : ''}`}
              aria-current={mode === 'profiles' ? 'page' : undefined}
              onClick={() => onNavigate('profiles')}
            >
              Профили общения
            </button>
            <button
              type="button"
              className={'agents-nav ' + (mode === 'documents' ? 'active' : '')}
              aria-current={mode === 'documents' ? 'page' : undefined}
              onClick={() => onNavigate('documents')}
            >
              Документы
            </button>
            <div className="nav-section-label">Расширения (MCP)</div>
            <button
              type="button"
              className={`agents-nav ${mode === 'invariants' ? 'active' : ''}`}
              aria-current={mode === 'invariants' ? 'page' : undefined}
              onClick={onOpenInvariants}
            >
              Инварианты
            </button>
            <button
              type="button"
              className={`agents-nav ${mode === 'mcp' ? 'active' : ''}`}
              aria-current={mode === 'mcp' ? 'page' : undefined}
              onClick={() => onNavigate('mcp')}
            >
              <span className="mcp-nav-icon" aria-hidden="true">
                ◇
              </span>{' '}
              MCP
            </button>
            <button
              type="button"
              className={`agents-nav ${mode === 'summaries' ? 'active' : ''}`}
              aria-current={mode === 'summaries' ? 'page' : undefined}
              onClick={() => onNavigate('summaries')}
            >
              Сводки
            </button>
            <div className="saved-chats" aria-label="Сохранённые чаты">
              {sessions.map((session) => {
                const title = session.title ?? 'Новый чат'
                const isActive = session.id === activeSessionId
                return (
                  <div className="saved-chat" key={session.id}>
                    <button
                      type="button"
                      className={isActive ? 'active' : ''}
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => onOpenSession(session.id)}
                    >
                      {title}
                    </button>
                    <button
                      type="button"
                      className="delete-chat"
                      aria-label={`Удалить чат «${title}»`}
                      onClick={() => onRemoveSession(session.id)}
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          </nav>
          {profileControl}
        </aside>
      )}
      {sidebarCollapsed && (
        <button
          type="button"
          className="sidebar-bubble"
          aria-label="Показать навигацию"
          title="Показать навигацию"
          onClick={() => onToggleSidebar(false)}
        >
          ›
        </button>
      )}

      <section className="chat-stage">{children}</section>
    </main>
  )
}
