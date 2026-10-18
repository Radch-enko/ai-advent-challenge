"""Mandatory path exclusions shared by repository readers."""

from pathlib import Path

HARD_EXCLUDED_COMPONENTS = frozenset(
    {
        ".cache",
        ".aws",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ssh",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "credentials",
        "dist",
        "env",
        "keys",
        "node_modules",
        "private_keys",
        "secrets",
        "site-packages",
        "target",
        "vendor",
        "venv",
        "virtualenv",
    }
)
SECRET_FILE_SUFFIXES = (".pem", ".key")
SECRET_FILE_NAMES = frozenset({"id_rsa", "id_ed25519", "credentials.md", "secrets.md"})


def is_hard_excluded(relative_path: Path) -> bool:
    parts = {part.casefold() for part in relative_path.parts}
    name = relative_path.name.casefold()
    return (
        bool(parts.intersection(HARD_EXCLUDED_COMPONENTS))
        or any(part.startswith(".env") for part in parts)
        or any(token in name for token in ("credential", "secret", "token", "password"))
        or name in SECRET_FILE_NAMES
        or name.endswith(SECRET_FILE_SUFFIXES)
    )
