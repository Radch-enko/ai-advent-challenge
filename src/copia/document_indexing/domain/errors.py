class DocumentIndexingError(RuntimeError):
    """Raised when source documents or generated index artifacts are invalid."""


class IndexRunConflict(RuntimeError):
    """Raised when another indexing run is already active."""
