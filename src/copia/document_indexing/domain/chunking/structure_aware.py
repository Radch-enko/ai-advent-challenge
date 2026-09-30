from __future__ import annotations

import re
from collections import OrderedDict

from copia.document_indexing.domain.chunking.chunk_ids import create_chunk
from copia.document_indexing.domain.models.document_chunk import DocumentChunk
from copia.document_indexing.domain.models.source_document import SourceDocument
from copia.providers.domain.contracts.embedding_provider import EmbeddingProvider


class StructureAwareChunkingStrategy:
    id = "structure-aware"
    display_name = "Structure aware"
    max_tokens = 680
    overlap_tokens = 64

    def chunk(
        self,
        document: SourceDocument,
        provider: EmbeddingProvider,
        model: str,
    ) -> list[DocumentChunk]:
        sections = (
            self._markdown_sections(document.text)
            if document.suffix == ".md"
            else self._text_sections(document.text)
        )
        chunks: list[DocumentChunk] = []
        for section, heading_context, paragraphs in sections:
            chunks.extend(
                self._chunk_section(
                    document,
                    section,
                    heading_context,
                    paragraphs,
                    provider,
                    model,
                    len(chunks),
                )
            )
        return chunks

    def _chunk_section(
        self,
        document: SourceDocument,
        section: str,
        heading_context: str,
        paragraphs: list[str],
        provider: EmbeddingProvider,
        model: str,
        first_sequence: int,
    ) -> list[DocumentChunk]:
        output: list[DocumentChunk] = []
        pending: list[str] = []

        def render(parts: list[str]) -> str:
            body = "\n\n".join(parts)
            return f"{heading_context}\n\n{body}".strip() if heading_context else body

        def flush() -> None:
            if not pending:
                return
            text = render(pending)
            output.append(
                create_chunk(
                    self.id,
                    document,
                    section,
                    text,
                    provider.count_tokens(text, model),
                    first_sequence + len(output),
                )
            )
            pending.clear()

        for paragraph in paragraphs:
            candidate = render([*pending, paragraph])
            if provider.count_tokens(candidate, model) <= self.max_tokens:
                pending.append(paragraph)
                continue
            flush()
            available_tokens = self.max_tokens
            if heading_context:
                available_tokens -= provider.count_tokens(heading_context, model) + 2
            if provider.count_tokens(paragraph, model) <= available_tokens:
                pending.append(paragraph)
                continue
            if available_tokens <= self.overlap_tokens:
                raise ValueError("Markdown heading is too long for a structural chunk")
            body_chunks = provider.split_text(
                paragraph,
                model,
                available_tokens,
                min(self.overlap_tokens, available_tokens - 1),
            )
            for body in body_chunks:
                text = render([body])
                token_count = provider.count_tokens(text, model)
                if token_count > self.max_tokens:
                    raise ValueError(
                        "The embedding tokenizer returned a structural chunk above its token limit"
                    )
                output.append(
                    create_chunk(
                        self.id,
                        document,
                        section,
                        text,
                        token_count,
                        first_sequence + len(output),
                    )
                )
        flush()
        return output

    @staticmethod
    def _text_sections(text: str) -> list[tuple[str, str, list[str]]]:
        paragraphs = [part.strip() for part in re.split(r"\n[ \t]*\n+", text) if part.strip()]
        return [("Document", "", paragraphs)] if paragraphs else []

    @staticmethod
    def _markdown_sections(text: str) -> list[tuple[str, str, list[str]]]:
        sections: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()
        heading_stack: list[tuple[int, str]] = []
        section = "Document"
        heading_context = ""
        paragraph_lines: list[str] = []
        in_fence = False

        def flush_paragraph() -> None:
            if paragraph_lines:
                if section not in sections:
                    sections[section] = (heading_context, [])
                sections[section][1].append("\n".join(paragraph_lines).strip())
                paragraph_lines.clear()

        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"^(?:\x60{3}|~~~)", stripped):
                in_fence = not in_fence
                paragraph_lines.append(line)
                continue
            heading = None if in_fence else re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$", line)
            if heading:
                flush_paragraph()
                level = len(heading.group(1))
                title = heading.group(2).strip()
                heading_stack = [(depth, value) for depth, value in heading_stack if depth < level]
                heading_stack.append((level, title))
                section = " / ".join(value for _, value in heading_stack)
                heading_context = "\n".join(
                    "#" * depth + " " + value for depth, value in heading_stack
                )
                sections.setdefault(section, (heading_context, []))
                continue
            if not stripped and not in_fence:
                flush_paragraph()
            else:
                paragraph_lines.append(line)
        flush_paragraph()
        return [(name, context, paragraphs) for name, (context, paragraphs) in sections.items()]
