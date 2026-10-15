from bisect import bisect_right

from code_assistance.models import Chunk, Document

MAX_CHUNK_CHARACTERS = 2_000
CHUNK_OVERLAP_CHARACTERS = 200
PREFERRED_BREAK_SEARCH = 800


def chunk_document(document: Document) -> list[Chunk]:
    text = document.text
    if not text.strip():
        return []

    line_starts = [0]
    line_starts.extend(
        index + 1
        for index, character in enumerate(text)
        if character == "\n" and index + 1 < len(text)
    )
    chunks: list[Chunk] = []
    start = 0

    while start < len(text):
        end = min(start + MAX_CHUNK_CHARACTERS, len(text))
        if end < len(text):
            preferred_break = text.rfind("\n", start + PREFERRED_BREAK_SEARCH, end)
            if preferred_break > start:
                end = preferred_break + 1
        content = text[start:end].strip()
        if content:
            start_line = bisect_right(line_starts, start)
            end_line = bisect_right(line_starts, max(start, end - 1))
            chunks.append(
                Chunk(
                    source_path=document.path,
                    start_line=max(1, start_line),
                    end_line=max(1, end_line),
                    text=content,
                )
            )
        if end >= len(text):
            break

        next_start = max(start + 1, end - CHUNK_OVERLAP_CHARACTERS)
        next_break = text.find("\n", next_start, end)
        start = next_break + 1 if next_break >= 0 else next_start

    return chunks
