from __future__ import annotations

import hashlib

from copia.document_indexing.domain.models.document_chunk import DocumentChunk
from copia.document_indexing.domain.models.source_document import SourceDocument


def create_chunk(
    strategy_id: str,
    document: SourceDocument,
    section: str,
    text: str,
    token_count: int,
    sequence: int,
) -> DocumentChunk:
    digest = hashlib.sha256(
        f"{strategy_id}\0{document.source}\0{sequence}\0{text}".encode()
    ).hexdigest()[:20]
    return DocumentChunk(
        text=text,
        source=document.source,
        title=document.title,
        section=section,
        chunk_id=f"{strategy_id}-{digest}",
        token_count=token_count,
    )
