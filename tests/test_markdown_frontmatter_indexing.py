from __future__ import annotations

from copia.document_indexing.domain.chunking import StructureAwareChunkingStrategy
from copia.document_indexing.domain.models.source_document import SourceDocument


class TokenCountingProvider:
    def count_tokens(self, text: str, model: str) -> int:
        return len(text.split())


def test_yaml_front_matter_is_removed_from_markdown_chunks() -> None:
    document = SourceDocument(
        source="Examples/sample-note.md",
        title="sample-note",
        suffix=".md",
        text=(
            "\ufeff---\r\n"
            "type: example-note\r\n"
            'period: "sample-period"\r\n'
            "status: draft\r\n"
            "---\r\n\r\n"
            "# Example Note\r\n\r\n"
            "## Sample Section\r\n\r\n"
            "- Example action: review the sample outline."
        ),
        size_bytes=0,
    )

    chunks = StructureAwareChunkingStrategy().chunk(
        document,
        TokenCountingProvider(),
        "fake-model",
    )

    assert len(chunks) == 1
    assert chunks[0].section == "Example Note / Sample Section"
    assert "example-note" not in chunks[0].text
    assert 'period: "sample-period"' not in chunks[0].text
    assert "status: draft" not in chunks[0].text
    assert "Example action: review the sample outline." in chunks[0].text


def test_markdown_without_closed_front_matter_keeps_leading_content() -> None:
    document = SourceDocument(
        source="note.md",
        title="note",
        suffix=".md",
        text="---\n\nThis is note content.\n\n# Details\n\nMore content.",
        size_bytes=0,
    )

    chunks = StructureAwareChunkingStrategy().chunk(
        document,
        TokenCountingProvider(),
        "fake-model",
    )

    assert any("This is note content." in chunk.text for chunk in chunks)
