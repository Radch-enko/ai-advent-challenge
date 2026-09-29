import { Invariant, InvariantInput } from '../../domain/models/invariant'
import { request } from './request'

export function getInvariants(): Promise<Invariant[]> {
  return request('/invariants')
}

export function createInvariant(value: InvariantInput): Promise<Invariant> {
  return request('/invariants', {
    method: 'POST',
    body: JSON.stringify(value),
  })
}

export function updateInvariant(itemId: string, value: InvariantInput): Promise<Invariant> {
  return request(`/invariants/${encodeURIComponent(itemId)}`, {
    method: 'PATCH',
    body: JSON.stringify(value),
  })
}

export function deleteInvariant(itemId: string): Promise<void> {
  return fetch(`/api/invariants/${encodeURIComponent(itemId)}`, { method: 'DELETE' }).then(
    (response) => {
      if (!response.ok) throw new Error(`Could not delete invariant: ${response.status}`)
    },
  )
}
