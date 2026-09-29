from __future__ import annotations

from collections.abc import Iterable


class PromptBuilder:
    """Build a system prompt from named, optional sections in insertion order."""

    def __init__(self) -> None:
        self._sections: list[tuple[str, str]] = []

    def add(self, name: str, content: str | None) -> PromptBuilder:
        if content and content.strip():
            self._sections.append((name, content))
        return self

    def extend(self, sections: Iterable[tuple[str, str | None]]) -> PromptBuilder:
        for name, content in sections:
            self.add(name, content)
        return self

    def build(self) -> str:
        return "\n\n".join(self.section_contents)

    @property
    def section_contents(self) -> tuple[str, ...]:
        return tuple(content for _, content in self._sections)

    @property
    def section_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._sections)
