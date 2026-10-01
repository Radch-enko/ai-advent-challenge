class DocumentIndexingError(RuntimeError):
    """Raised when source documents or generated index artifacts are invalid."""


class IndexRunConflict(RuntimeError):
    """Raised when another indexing run is already active."""


class DocumentRetrievalError(RuntimeError):
    """A safe, user-facing error raised when the local index cannot be searched."""
