import { ApiRequestError } from '../../../data/api/request'
import {
  createUserProfile,
  deleteUserProfile,
  updateUserProfile,
} from '../../../data/api/profilesApi'
import { UserProfileInput } from '../../../domain/models/userProfile'

export class UserProfileMutationError extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message)
  }
}

export async function saveUserProfile(profileId: string | null, input: UserProfileInput) {
  if (profileId) await updateUserProfile(profileId, input)
  else await createUserProfile(input)
}

export async function removeUserProfile(profileId: string) {
  try {
    await deleteUserProfile(profileId)
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new UserProfileMutationError(error.message, error.errorCode)
    }
    throw error
  }
}
