"""Identify repository Markdown that defines review requirements."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from code_assistance.models import Document

RULE_DIRECTORIES = frozenset(
    {
        ".agents",
        "architecture",
        "conventions",
        "guidelines",
        "instructions",
        "policies",
        "rules",
        "skills",
        "style",
        "code-style",
        "coding-style",
        "standards",
    }
)
RULE_FILENAMES = frozenset(
    {
        "agents.md",
        "architecture.md",
        "code-review.md",
        "code-style.md",
        "coding-guidelines.md",
        "coding-standards.md",
        "coding-style.md",
        "contributing.md",
        "copilot-instructions.md",
        "development-guidelines.md",
        "engineering-guidelines.md",
        "repository-rules.md",
        "review-guidelines.md",
        "style-guide.md",
    }
)
RULE_NAME_PATTERN = re.compile(
    r"(?i)(?:^|[-_ ])(?:architecture|code[-_ ]?style|coding[-_ ]?style|"
    r"conventions|guidelines|instructions|policies|review|rules|standards|"
    r"style[-_ ]?guide)(?:$|[-_ ])"
)
RULE_HEADING_PATTERN = re.compile(
    r"(?i)^#{1,6}\s+.*(?:code[- ]review|code[- ]style|coding|architecture|"
    r"conventions|guidelines|instructions|policies|repository rules|"
    r"security policy|testing policy|test strategy|error handling|quality gates)"
)


def prioritized_review_rule_paths(documents: Sequence[Document]) -> frozenset[str]:
    """Return Markdown paths likely to contain repository-specific review rules."""
    prioritized: set[str] = set()
    for document in documents:
        path = PurePosixPath(document.path)
        parts = {part.casefold() for part in path.parts[:-1]}
        filename = path.name.casefold()
        stem = path.stem.casefold().replace("_", "-").replace(" ", "-")
        has_rule_heading = any(
            RULE_HEADING_PATTERN.match(line.strip()) for line in document.text.splitlines()
        )
        if (
            filename in RULE_FILENAMES
            or bool(parts.intersection(RULE_DIRECTORIES))
            or RULE_NAME_PATTERN.search(stem) is not None
            or has_rule_heading
        ):
            prioritized.add(document.path)
    return frozenset(prioritized)
