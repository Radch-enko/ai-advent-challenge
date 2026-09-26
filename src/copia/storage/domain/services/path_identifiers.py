from __future__ import annotations

from pathlib import Path


def validate_path_identifier(value: str, label: str = "Identifier") -> str:
    """Reject values that could escape a repository's intended directory."""
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
        or Path(value).name != value
    ):
        raise ValueError(f"Invalid {label}")
    return value
