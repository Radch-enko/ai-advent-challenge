export type UserProfileLanguage = 'ru' | 'en' | 'auto'
export type UserProfileTone = 'neutral' | 'friendly' | 'formal' | 'direct'
export type UserProfileVerbosity = 'concise' | 'balanced' | 'detailed'
export type UserProfileResponseFormat =
  'plain_text' | 'markdown' | 'bullets' | 'steps' | 'tables' | 'code'

export type UserProfile = {
  id: string
  name: string
  language: UserProfileLanguage
  tone: UserProfileTone
  verbosity: UserProfileVerbosity
  response_format: UserProfileResponseFormat[]
  constraints: string[]
  created_at: string
  updated_at: string
}

export type UserProfileInput = Omit<UserProfile, 'id' | 'created_at' | 'updated_at'>
export type UserProfileUpdate = Partial<UserProfileInput>
