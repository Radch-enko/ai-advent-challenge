from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SENSITIVE_KEY = re.compile(
    r"(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"client[_-]?secret|auth[_-]?key|cookie|set[_-]?cookie|password|secret|token|"
    r"www-authenticate|proxy-authenticate)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD = re.compile(
    r"(?P<prefix>[\"']?(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|client[_-]?secret|auth[_-]?key|cookie|set[_-]?cookie|password|secret|"
    r"token)[\"']?\s*[:=]\s*)"
    r"(?P<value>[\"'](?:\\.|[^\"'])*(?:[\"']|$)|[^,\s;&}#\r\n]+)",
    re.IGNORECASE,
)
_AUTH_VALUE = re.compile(r"\b(Bearer|Basic)\s+(?!\[REDACTED\])[^\s,;]+", re.IGNORECASE)
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])"
)
_COMMON_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_-]{8,}|"
    r"github_pat_[A-Za-z0-9_]{8,}|glpat-[A-Za-z0-9_-]{8,})(?![A-Za-z0-9_-])"
)
_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.DOTALL,
)
_SENSITIVE_QUERY = re.compile(
    r"([?&#](?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"client[_-]?secret|auth[_-]?key|cookie|set[_-]?cookie|token|secret|password|key)=[^&#]*)",
    re.IGNORECASE,
)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_CREDENTIAL_PATH = re.compile(
    r"(?P<prefix>/(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|client[_-]?secret|auth[_-]?key)(?:=|:|/))(?P<value>[^/?#&]+)",
    re.IGNORECASE,
)


def is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and _SENSITIVE_KEY.search(key) is not None


def sanitize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc.rsplit("@", 1)[-1]
    path = _CREDENTIAL_PATH.sub(r"\g<prefix>[REDACTED]", parts.path)

    def replace_query(match: re.Match[str]) -> str:
        return f"{match.group(0).split('=', 1)[0]}=[REDACTED]"

    query = _SENSITIVE_QUERY.sub(replace_query, f"?{parts.query}")[1:] if parts.query else ""
    fragment = (
        _SENSITIVE_QUERY.sub(replace_query, f"#{parts.fragment}")[1:] if parts.fragment else ""
    )
    return urlunsplit((parts.scheme, netloc, path, query, fragment))


def sanitize_text(value: str) -> str:
    value = _URL_IN_TEXT.sub(lambda match: sanitize_url(match.group(0)), value)
    value = _AUTH_VALUE.sub(r"\1 [REDACTED]", value)

    def replace_field(match: re.Match[str]) -> str:
        raw = match.group("value")
        quote = raw[:1] if raw[:1] in {"'", '"'} else ""
        return f"{match.group('prefix')}{quote}[REDACTED]{quote}"

    value = _SENSITIVE_FIELD.sub(replace_field, value)
    value = _JWT.sub("[REDACTED]", value)
    value = _COMMON_TOKEN.sub("[REDACTED]", value)
    return _PEM_PRIVATE_KEY.sub("[REDACTED]", value)


def sanitize_value(value: Any) -> Any:
    """Redact credentials recursively while preserving ordinary personal context."""
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if is_sensitive_key(key) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item) for item in value)
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def sanitize_error(value: str, *, max_length: int = 500) -> str:
    """Sanitize a compact error surface without removing ordinary user context."""
    return " ".join(sanitize_text(value).replace("\n", " ").split())[:max_length]
