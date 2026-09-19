from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from ..domain.models.user_profile import UserProfile


class UserProfileStorageError(ValueError):
    """Raised when the user-profile storage cannot be read or validated."""


class UserProfileNameConflictError(ValueError):
    """Raised when a profile name is already used, ignoring letter case."""


class JsonUserProfilesRepository:
    def __init__(self, path: Path | None = None) -> None:
        configured = os.getenv("COPIA_USER_PROFILES_PATH")
        self._path = (
            Path(configured) if configured else (path or Path("~/.copia/user_profiles.json"))
        )
        self._path = self._path.expanduser()
        self._lock = RLock()

    def list(self) -> list[UserProfile]:
        with self._lock:
            return self._load()

    def get(self, profile_id: str) -> UserProfile | None:
        return next((profile for profile in self.list() if profile.id == profile_id), None)

    def create(self, profile: UserProfile) -> UserProfile:
        with self._lock:
            profiles = self._load()
            self._ensure_name_available(profiles, profile.name)
            profiles.append(profile)
            self._save(profiles)
        return profile

    def update(self, profile_id: str, changes: dict[str, object]) -> UserProfile:
        with self._lock:
            profiles = self._load()
            for index, profile in enumerate(profiles):
                if profile.id == profile_id:
                    updated = profile.model_validate({**profile.model_dump(), **changes})
                    self._ensure_name_available(profiles, updated.name, excluded_id=profile_id)
                    profiles[index] = updated
                    self._save(profiles)
                    return updated
        raise KeyError(profile_id)

    @staticmethod
    def _ensure_name_available(
        profiles: list[UserProfile], name: str, excluded_id: str | None = None
    ) -> None:
        if any(
            profile.id != excluded_id and profile.name.casefold() == name.casefold()
            for profile in profiles
        ):
            raise UserProfileNameConflictError("A user profile with this name already exists")

    def delete(self, profile_id: str) -> None:
        with self._lock:
            profiles = self._load()
            remaining = [profile for profile in profiles if profile.id != profile_id]
            if len(remaining) == len(profiles):
                raise KeyError(profile_id)
            self._save(remaining)

    def _load(self) -> list[UserProfile]:
        if not self._path.is_file():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
                raise ValueError
            profiles = [UserProfile.model_validate(item) for item in payload["profiles"]]
            names = [profile.name.casefold() for profile in profiles]
            if len(names) != len(set(names)):
                raise UserProfileStorageError("User profile storage is unavailable")
            return profiles
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise UserProfileStorageError("User profile storage is unavailable") from error

    def _save(self, profiles: list[UserProfile]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=".user-profiles-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(
                    {"profiles": [profile.model_dump(mode="json") for profile in profiles]},
                    temporary,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self._path)
        except OSError as error:
            raise UserProfileStorageError("User profile storage is unavailable") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
