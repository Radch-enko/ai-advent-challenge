from datetime import datetime

from pydantic import ConfigDict, field_validator

from copia.user_profiles.domain.models.user_profile_fields import _UserProfileFields


class UserProfile(_UserProfileFields):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    created_at: datetime
    updated_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        from uuid import UUID

        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("id must be a UUID") from error
        return value
