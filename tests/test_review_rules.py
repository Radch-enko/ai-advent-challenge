import json
from pathlib import Path

from code_assistance.config import load_config
from code_assistance.models import Document
from code_assistance.review_analysis import REVIEW_TOP_K, ReviewAnalyzer
from code_assistance.review_rules import prioritized_review_rule_paths
from tests.conftest import FakeEmbeddings


class CapturingChat:
    def __init__(self) -> None:
        self.instructions = ""
        self.prompt = ""

    def generate(self, instructions: str, prompt: str) -> str:
        self.instructions = instructions
        self.prompt = prompt
        return json.dumps({"summary": "Проблем не найдено.", "findings": []})


def test_rule_documents_are_detected_by_paths_names_and_headings() -> None:
    documents = [
        Document(".agents/skills/python/SKILL.md", "Instructions", "a"),
        Document(".github/instructions/review.md", "Review guidance", "b"),
        Document("CONTRIBUTING.md", "Project setup", "c"),
        Document("docs/overview.md", "## Architecture\nKeep modules focused.", "d"),
        Document("docs/notes.md", "A general project overview.", "e"),
        Document("docs/typescript-code-style.md", "Use explicit types.", "f"),
    ]

    assert prioritized_review_rule_paths(documents) == frozenset(
        {
            ".agents/skills/python/SKILL.md",
            ".github/instructions/review.md",
            "CONTRIBUTING.md",
            "docs/overview.md",
            "docs/typescript-code-style.md",
        }
    )


def test_review_retrieval_uses_thirty_results_and_prioritizes_repository_rules(
    git_repository: Path, tmp_path: Path
) -> None:
    (git_repository / "payment.py").write_text("def payment(): return 1\n", encoding="utf-8")
    (git_repository / "README.md").write_text("Payment is important.\n", encoding="utf-8")
    rules_directory = git_repository / ".agents" / "skills" / "architecture"
    rules_directory.mkdir(parents=True)
    for index in range(32):
        (rules_directory / f"rule-{index:02}.md").write_text(
            f"Payment rule {index}.\n", encoding="utf-8"
        )

    patch = "@@ -1 +1 @@\n-def payment(): return 1\n+def payment(): return 2\n"
    chat = CapturingChat()
    config = load_config(tmp_path / "missing-config.toml")
    analyzer = ReviewAnalyzer(config, FakeEmbeddings(), chat, tmp_path / "indexes")

    analyzer.analyze(
        repository_id=1,
        base_sha="base-sha",
        head_sha="head-sha",
        base_root=git_repository,
        head_root=git_repository,
        files=[{"filename": "payment.py", "patch": patch}],
    )

    rule_excerpts = [line for line in chat.prompt.splitlines() if line.startswith("rule ")]
    assert REVIEW_TOP_K == 30
    assert "senior software engineer reviewing a GitHub pull request" in chat.instructions
    assert "Do not write generic checklists" in chat.instructions
    assert len(rule_excerpts) == 30
    assert all(".agents/skills/architecture/rule-" in line for line in rule_excerpts)
    assert "rule README.md:" not in chat.prompt
