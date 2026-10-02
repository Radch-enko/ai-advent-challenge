import { Dispatch, MutableRefObject, SetStateAction, useEffect } from 'react'
import { updateSessionUserProfile } from '../../../data/api/profilesApi'
import {
  createSession,
  createSessionFromProfile,
  deleteSession,
  forkSession,
  getSession,
  updateSessionContextManagement,
  updateSessionLongTermMemory,
  updateSessionRagMode,
  updateSessionTaskMode,
} from '../../../data/api/sessionsApi'
import { AgentConfig, ContextManagementConfig } from '../../../domain/models/agent'
import { ChatMessage } from '../../../domain/models/chat'
import { ChatSession } from '../../../domain/models/session'
import { TaskState } from '../../../domain/models/task'
import { RagSettings } from '../../../domain/models/ragSettings'
import { mapStoredMessages } from './sessionTranscript'

type SessionOperationsState = {
  activeSession: ChatSession | null
  activeTask: TaskState | undefined
  taskIsActive: boolean
  ragModeDraft: boolean
  ragSettingsDraft: RagSettings
  isLoading: boolean
  profileSettingsSaving: boolean
  forkingMessageIndex: number | null
  lastProfileSelection: { id: string | null } | null
}

type SessionOperationsActions = {
  openSession: (session: ChatSession) => void
  startNewChat: () => void
  refreshSessions: () => Promise<boolean>
  setActiveSession: Dispatch<SetStateAction<ChatSession | null>>
  setTaskModeDraft: Dispatch<SetStateAction<boolean>>
  setRagModeDraft: Dispatch<SetStateAction<boolean>>
  setRagSettingsDraft: Dispatch<SetStateAction<RagSettings>>
  setSelectedUserProfileId: Dispatch<SetStateAction<string | null>>
  setProfileSelectionError: Dispatch<SetStateAction<string | null>>
  setProfileSelectionLoading: Dispatch<SetStateAction<boolean>>
  setLastProfileSelection: Dispatch<SetStateAction<{ id: string | null } | null>>
  setProfileSettingsSaving: Dispatch<SetStateAction<boolean>>
  setProfileSettingsError: Dispatch<SetStateAction<string | null>>
  setForkingMessageIndex: Dispatch<SetStateAction<number | null>>
  setForkError: Dispatch<SetStateAction<string | null>>
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
}

type SessionOperationsOptions = {
  state: SessionOperationsState
  actions: SessionOperationsActions
  meta: { activeSessionIdRef: MutableRefObject<string | null> }
}

export function useSessionOperations({ state, actions, meta }: SessionOperationsOptions) {
  const { activeSessionIdRef } = meta
  const { openSession, refreshSessions, setActiveSession, setMessages } = actions

  useEffect(() => {
    void (async () => {
      await refreshSessions()
      const sessionId = localStorage.getItem('copia.activeSessionId')
      if (!sessionId) return
      activeSessionIdRef.current = sessionId
      try {
        const session = await getSession(sessionId)
        if (activeSessionIdRef.current !== sessionId) return
        openSession(session)
      } catch {
        localStorage.removeItem('copia.activeSessionId')
      }
    })()
  }, [openSession, refreshSessions, activeSessionIdRef])

  useEffect(() => {
    const sessionId = state.activeSession?.id
    const taskId = state.activeTask?.id
    const taskStatus = state.activeTask?.status
    if (
      !sessionId ||
      !taskId ||
      !['running', 'pause_requested', 'paused', 'waiting_for_approval'].includes(taskStatus ?? '')
    )
      return

    let cancelled = false
    const syncTask = async () => {
      try {
        const latest = await getSession(sessionId)
        if (cancelled || activeSessionIdRef.current !== latest.id) return
        setActiveSession(latest)
        setMessages(mapStoredMessages(latest.messages))
      } catch {
        // Следующий цикл повторит загрузку после временной ошибки.
      }
    }
    const interval = window.setInterval(() => void syncTask(), 900)
    void syncTask()
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [
    setActiveSession,
    setMessages,
    activeSessionIdRef,
    state.activeSession?.id,
    state.activeTask?.id,
    state.activeTask?.stage,
    state.activeTask?.status,
  ])

  async function createFromProfile(profileName: string): Promise<ChatSession> {
    return createSessionFromProfile(profileName, state.ragModeDraft, state.ragSettingsDraft)
  }

  async function createWithConfig(config: AgentConfig): Promise<ChatSession> {
    return createSession(config, null, false, state.ragModeDraft, state.ragSettingsDraft)
  }

  async function openSavedSession(sessionId: string) {
    activeSessionIdRef.current = sessionId
    const session = await getSession(sessionId)
    if (activeSessionIdRef.current === sessionId) actions.openSession(session)
  }

  async function removeSession(sessionId: string) {
    await deleteSession(sessionId)
    if (activeSessionIdRef.current === sessionId) actions.startNewChat()
    await actions.refreshSessions()
  }

  async function setTaskMode(enabled: boolean) {
    if (state.taskIsActive) return
    if (!state.activeSession) {
      actions.setTaskModeDraft(enabled)
      return
    }
    try {
      const updated = await updateSessionTaskMode(state.activeSession.id, enabled)
      if (activeSessionIdRef.current === updated.id) {
        actions.setActiveSession(updated)
        actions.setTaskModeDraft(updated.task_mode_enabled)
      }
    } catch (error) {
      actions.setProfileSettingsError(
        error instanceof Error ? error.message : 'Не удалось изменить Task mode',
      )
    }
  }

  async function setRagMode(enabled: boolean) {
    if (state.taskIsActive) return
    if (!state.activeSession) {
      actions.setRagModeDraft(enabled)
      return
    }
    if (state.profileSettingsSaving) return
    actions.setProfileSettingsSaving(true)
    actions.setProfileSettingsError(null)
    try {
      const updated = await updateSessionRagMode(
        state.activeSession.id,
        enabled,
        state.ragSettingsDraft,
      )
      if (activeSessionIdRef.current === updated.id) {
        actions.setActiveSession(updated)
        actions.setRagModeDraft(updated.rag_enabled)
        actions.setRagSettingsDraft(updated.rag_settings)
      }
    } catch (error) {
      if (activeSessionIdRef.current === state.activeSession.id) {
        actions.setProfileSettingsError(
          error instanceof Error ? error.message : 'Не удалось изменить RAG mode',
        )
      }
    } finally {
      actions.setProfileSettingsSaving(false)
    }
  }

  async function saveRagSettings(settings: RagSettings) {
    const session = state.activeSession
    actions.setRagSettingsDraft(settings)
    if (!session || state.taskIsActive || state.profileSettingsSaving) return
    actions.setProfileSettingsSaving(true)
    actions.setProfileSettingsError(null)
    try {
      const updated = await updateSessionRagMode(session.id, session.rag_enabled, settings)
      if (activeSessionIdRef.current === updated.id) {
        actions.setActiveSession(updated)
        actions.setRagSettingsDraft(updated.rag_settings)
      }
    } catch (error) {
      if (activeSessionIdRef.current === session.id) {
        actions.setProfileSettingsError(
          error instanceof Error ? error.message : 'Не удалось сохранить настройки RAG',
        )
      }
    } finally {
      actions.setProfileSettingsSaving(false)
    }
  }

  async function selectUserProfile(profileId: string | null) {
    const session = state.activeSession
    if (!session) {
      actions.setSelectedUserProfileId(profileId)
      actions.setProfileSelectionError(null)
      return
    }
    actions.setProfileSelectionLoading(true)
    actions.setProfileSelectionError(null)
    actions.setLastProfileSelection({ id: profileId })
    try {
      const updated = await updateSessionUserProfile(session.id, profileId)
      actions.setActiveSession(updated)
      actions.setSelectedUserProfileId(updated.user_profile_id)
      actions.setProfileSelectionError(null)
      actions.setLastProfileSelection(null)
      await actions.refreshSessions()
    } catch (error) {
      actions.setProfileSelectionError(
        error instanceof Error ? error.message : 'Не удалось выбрать профиль',
      )
    } finally {
      actions.setProfileSelectionLoading(false)
    }
  }

  function retryProfileSelection() {
    if (state.lastProfileSelection) void selectUserProfile(state.lastProfileSelection.id)
  }

  async function setProfileContextManagement(value: ContextManagementConfig) {
    const session = state.activeSession
    if (!session || session.profile_name == null || state.profileSettingsSaving) return
    actions.setProfileSettingsSaving(true)
    actions.setProfileSettingsError(null)
    try {
      const updated = await updateSessionContextManagement(session.id, value)
      if (activeSessionIdRef.current === session.id) actions.setActiveSession(updated)
      await actions.refreshSessions()
    } catch (error) {
      actions.setProfileSettingsError(
        error instanceof Error ? error.message : 'Не удалось сохранить настройку',
      )
    } finally {
      actions.setProfileSettingsSaving(false)
    }
  }

  async function setLongTermMemoryEnabled(enabled: boolean) {
    const session = state.activeSession
    if (!session || session.profile_name == null || state.profileSettingsSaving) return
    actions.setProfileSettingsSaving(true)
    actions.setProfileSettingsError(null)
    try {
      const updated = await updateSessionLongTermMemory(session.id, enabled)
      if (activeSessionIdRef.current === session.id) actions.setActiveSession(updated)
    } catch (error) {
      if (activeSessionIdRef.current === session.id) {
        actions.setProfileSettingsError(
          error instanceof Error ? error.message : 'Не удалось сохранить настройку',
        )
      }
    } finally {
      actions.setProfileSettingsSaving(false)
    }
  }

  async function forkFromMessage(messageIndex: number) {
    const session = state.activeSession
    if (!session || state.isLoading || state.forkingMessageIndex != null) return
    actions.setForkingMessageIndex(messageIndex)
    actions.setForkError(null)
    try {
      actions.openSession(await forkSession(session.id, messageIndex))
    } catch (error) {
      actions.setForkError(error instanceof Error ? error.message : 'Не удалось создать ветку')
    } finally {
      actions.setForkingMessageIndex(null)
    }
  }

  return {
    createFromProfile,
    createWithConfig,
    openSavedSession,
    removeSession,
    setTaskMode,
    setRagMode,
    saveRagSettings,
    selectUserProfile,
    retryProfileSelection,
    setProfileContextManagement,
    setLongTermMemoryEnabled,
    forkFromMessage,
  }
}
