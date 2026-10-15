class CodeAssistanceError(Exception):
    """Base class for errors safe to show to the CLI user."""


class ConfigurationError(CodeAssistanceError):
    """The user configuration is missing or invalid."""


class RepositoryError(CodeAssistanceError):
    """The selected directory is not a usable Git repository."""


class DocumentError(CodeAssistanceError):
    """A supported documentation file could not be handled safely."""


class UnsafePathError(DocumentError):
    """A document resolves outside the selected repository."""


class ProviderError(CodeAssistanceError):
    """An OpenAI request failed or returned invalid data."""


class IndexErrorBase(CodeAssistanceError):
    """The local index is unavailable or incompatible."""


class IndexCorruptionError(IndexErrorBase):
    """The local SQLite index is damaged."""


class IndexCompatibilityError(IndexErrorBase):
    """The local index does not match the configured embedding space."""


class BranchUnavailableError(CodeAssistanceError):
    """The configured MCP tool could not provide current Git context."""


class GitUnavailableError(CodeAssistanceError):
    """A read-only Git MCP tool could not provide valid data."""
