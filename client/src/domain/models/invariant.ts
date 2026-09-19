export type Invariant = {
  id: string
  name: string
  text: string
  created_at: string
  updated_at: string
}

export type InvariantInput = Pick<Invariant, 'name' | 'text'>
