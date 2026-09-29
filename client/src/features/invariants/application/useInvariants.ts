import { useCallback, useEffect, useState } from 'react'
import {
  createInvariant,
  deleteInvariant,
  getInvariants,
  updateInvariant,
} from '../../../data/api/invariantsApi'
import { Invariant, InvariantInput } from '../../../domain/models/invariant'

export function useInvariants() {
  const [items, setItems] = useState<Invariant[]>([])

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      setItems(await getInvariants())
      return true
    } catch {
      setItems([])
      return false
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => void refresh())
  }, [refresh])

  const add = useCallback(async (value: InvariantInput) => {
    const created = await createInvariant(value)
    setItems((current) => [...current, created])
  }, [])

  const edit = useCallback(async (itemId: string, value: InvariantInput) => {
    const updated = await updateInvariant(itemId, value)
    setItems((current) => current.map((item) => (item.id === itemId ? updated : item)))
  }, [])

  const remove = useCallback(async (itemId: string) => {
    await deleteInvariant(itemId)
    setItems((current) => current.filter((item) => item.id !== itemId))
  }, [])

  return { items, refresh, add, edit, remove }
}
