import subprocess
from pathlib import Path

from code_assistance.errors import RepositoryError

GIT_TIMEOUT_SECONDS = 5


def find_repository_root(start_path: Path) -> Path:
    candidate = start_path.expanduser()
    if not candidate.exists():
        raise RepositoryError(f"Repository path does not exist: {candidate}")
    if candidate.is_file():
        candidate = candidate.parent

    try:
        result = subprocess.run(
            ["git", "-C", str(candidate.resolve()), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RepositoryError("Git is not installed or is not available on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepositoryError("Git repository discovery timed out.") from exc

    if result.returncode != 0 or not result.stdout.strip():
        raise RepositoryError(f"No Git repository found from {candidate}.")
    try:
        return Path(result.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise RepositoryError("Git returned an invalid repository root.") from exc
