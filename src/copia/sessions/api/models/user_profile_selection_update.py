from __future__ import annotations

from pydantic import BaseModel


class UserProfileSelectionUpdate(BaseModel):
    user_profile_id: str | None = None
