import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from platformdirs import user_data_path

from code_assistance.errors import ConfigurationError

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_CHAT_MODEL = "gpt-5-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
MAX_SUPPORTED_FILE_BYTES = 10_485_760
MAX_EMBEDDING_DIMENSIONS = 8_192


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    base_url: str
    chat_model: str
    embedding_model: str
    embedding_dimensions: int | None
    request_timeout_seconds: float
    max_file_bytes: int
    top_k: int
    minimum_similarity: float
    mcp_command: tuple[str, ...] | None
    mcp_tool_name: str
    mcp_timeout_seconds: float


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.toml"


def default_index_directory() -> Path:
    return Path(user_data_path("code-assistance", appauthor=False)) / "indexes"


def default_env_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _table(value: object, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section [{name}] must be a TOML table.")
    return cast(dict[str, Any], value)


def _string(table: dict[str, Any], key: str, default: str, section: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"[{section}].{key} must be a non-empty string.")
    return value.strip()


def _positive_integer(
    table: dict[str, Any],
    key: str,
    default: int,
    section: str,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"[{section}].{key} must be a positive integer.")
    return int(value)


def _positive_number(
    table: dict[str, Any],
    key: str,
    default: int | float,
    section: str,
) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigurationError(f"[{section}].{key} must be a positive number.")
    return float(value)


def _optional_positive_integer(
    table: dict[str, Any],
    key: str,
    section: str,
) -> int | None:
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"[{section}].{key} must be a positive integer.")
    if value > MAX_EMBEDDING_DIMENSIONS:
        raise ConfigurationError(f"[{section}].{key} must not exceed {MAX_EMBEDDING_DIMENSIONS}.")
    return int(value)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(
            f"Cannot read configuration file at {config_path}. "
            "Check its TOML syntax and permissions."
        ) from exc

    openai = _table(raw.get("openai"), "openai")
    index = _table(raw.get("index"), "index")
    mcp = _table(raw.get("git_mcp"), "git_mcp")

    base_url = _string(openai, "base_url", DEFAULT_BASE_URL, "openai").rstrip("/")
    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ConfigurationError(
            "[openai].base_url must be an HTTP(S) endpoint without embedded credentials."
        )

    chat_model = _string(openai, "chat_model", DEFAULT_CHAT_MODEL, "openai")
    embedding_model = _string(openai, "embedding_model", DEFAULT_EMBEDDING_MODEL, "openai")
    dimensions = _optional_positive_integer(openai, "embedding_dimensions", "openai")

    request_timeout = _positive_number(openai, "timeout_seconds", 60, "openai")
    if request_timeout > 300:
        raise ConfigurationError("[openai].timeout_seconds must not exceed 300.")
    max_file_bytes = _positive_integer(index, "max_file_bytes", 1_048_576, "index")
    if max_file_bytes > MAX_SUPPORTED_FILE_BYTES:
        raise ConfigurationError(
            f"[index].max_file_bytes must not exceed {MAX_SUPPORTED_FILE_BYTES}."
        )
    top_k = _positive_integer(index, "top_k", 5, "index")
    if top_k > 20:
        raise ConfigurationError("[index].top_k must not exceed 20.")
    minimum_similarity = index.get("minimum_similarity", 0.25)
    if (
        isinstance(minimum_similarity, bool)
        or not isinstance(minimum_similarity, (int, float))
        or not 0 <= minimum_similarity <= 1
    ):
        raise ConfigurationError("[index].minimum_similarity must be between 0 and 1.")

    command_value = mcp.get("command")
    command: tuple[str, ...] | None
    if command_value is None:
        command = None
    elif (
        isinstance(command_value, list)
        and command_value
        and all(isinstance(part, str) and part.strip() for part in command_value)
    ):
        command = tuple(part.strip() for part in command_value)
    else:
        raise ConfigurationError(
            "[git_mcp].command must be a non-empty array of executable and arguments; "
            "shell command strings are not accepted."
        )

    mcp_tool_name = _string(mcp, "tool_name", "get_current_branch", "git_mcp")
    mcp_timeout = _positive_number(mcp, "timeout_seconds", 10, "git_mcp")
    if mcp_timeout > 120:
        raise ConfigurationError("[git_mcp].timeout_seconds must not exceed 120.")

    return AppConfig(
        config_path=config_path,
        base_url=base_url,
        chat_model=chat_model,
        embedding_model=embedding_model,
        embedding_dimensions=dimensions,
        request_timeout_seconds=request_timeout,
        max_file_bytes=max_file_bytes,
        top_k=top_k,
        minimum_similarity=float(minimum_similarity),
        mcp_command=command,
        mcp_tool_name=mcp_tool_name,
        mcp_timeout_seconds=mcp_timeout,
    )


def api_key_from_environment(env_file: Path | None = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key

    dotenv_path = env_file or default_env_file()
    try:
        api_key = _read_env_api_key(dotenv_path)
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(
            f"Cannot read the local environment file at {dotenv_path}."
        ) from exc

    if not api_key:
        raise ConfigurationError(
            "OPENAI_API_KEY is not set. Set it in the shell or in the Code Assistance .env file."
        )
    return api_key


def _read_env_api_key(env_file: Path) -> str:
    try:
        with env_file.open("r", encoding="utf-8") as source:
            for line in source:
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                if entry.startswith("export "):
                    entry = entry[len("export ") :].lstrip()

                key, separator, value = entry.partition("=")
                if key.strip() != "OPENAI_API_KEY":
                    continue
                if not separator:
                    return ""

                value = value.strip()
                if value.startswith(("'", '"')):
                    quote = value[0]
                    closing_quote = value.find(quote, 1)
                    if closing_quote < 0:
                        raise UnicodeError("The local environment file has an invalid value.")
                    trailing = value[closing_quote + 1 :].strip()
                    if trailing and not trailing.startswith("#"):
                        raise UnicodeError("The local environment file has an invalid value.")
                    return value[1:closing_quote].strip()

                comment_index = value.find(" #")
                if comment_index >= 0:
                    value = value[:comment_index]
                return value.strip()
    except FileNotFoundError:
        return ""
    return ""
