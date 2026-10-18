"""Coordinate a review without letting model output choose GitHub API operations."""

import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from code_assistance.github_app import GitHubAppClient, GitHubAppError
from code_assistance.review_analysis import ReviewAnalyzer, patches_from_files
from code_assistance.review_snapshot import _safe_relative, materialize_snapshot
from code_assistance.review_state import ReviewJob, ReviewJobStore

LOGGER = logging.getLogger(__name__)


def _sha(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise GitHubAppError("GitHub returned an invalid commit SHA.")
    return value.lower()


def _optional_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _pull_shas(pull: dict[str, Any]) -> tuple[str, str]:
    head = pull.get("head")
    base = pull.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise GitHubAppError("GitHub returned an invalid PR.")
    return _sha(head.get("sha")), _sha(base.get("sha"))


class ReviewService:
    def __init__(
        self,
        github_factory: Callable[[int], GitHubAppClient],
        analyzer: ReviewAnalyzer,
        store: ReviewJobStore,
        max_file_bytes: int,
        connection_check: Callable[[], None] | None = None,
    ) -> None:
        self.github_factory = github_factory
        self.analyzer = analyzer
        self.store = store
        self.max_file_bytes = max_file_bytes
        self.connection_check = connection_check

    def process(self, job: ReviewJob) -> None:
        def progress(stage: str, done: int = 0, total: int = 0) -> None:
            if total:
                LOGGER.info(
                    "Review %s PR #%d stage=%s files=%d/%d",
                    job.repository,
                    job.number,
                    stage,
                    done,
                    total,
                )
            else:
                LOGGER.info("Review %s PR #%d stage=%s", job.repository, job.number, stage)

        if self.connection_check is not None:
            progress("checking_openai_connection")
            self.connection_check()
        progress("fetching_diff")
        client = self.github_factory(job.installation_id)
        pull = client.pull_request(job.repository, job.number)
        head_sha, base_sha = _pull_shas(pull)
        if pull.get("draft") is not False or head_sha != job.head_sha or base_sha != job.base_sha:
            self.store.finish(job, "stale")
            return
        marker = f"<!-- code-assistance-reviewer:{job.key} -->"
        if client.review_exists(job.repository, job.number, marker):
            self.store.finish(job, "done")
            return
        changed_count = pull.get("changed_files")
        if not isinstance(changed_count, int) or changed_count < 0:
            raise GitHubAppError("GitHub did not return the number of changed files.")
        files = client.pull_files(job.repository, job.number, changed_count)
        if not files:
            raise GitHubAppError("The PR has no changed files to review.")
        for item in files:
            name = item.get("filename")
            if not isinstance(name, str) or _safe_relative(name) is None:
                raise GitHubAppError("The PR changes a path excluded by the safety policy.")
        patches_from_files(files)

        with tempfile.TemporaryDirectory(prefix="code-assistance-review-") as directory:
            root = Path(directory)
            progress("snapshot_rules")
            base_snapshot = materialize_snapshot(
                client,
                job.repository,
                base_sha,
                root / "base",
                self.max_file_bytes,
                markdown_only=True,
                progress=lambda done, total: progress("snapshot_rules", done, total),
            )
            try:
                progress("snapshot_code")
                head_snapshot = materialize_snapshot(
                    client,
                    job.repository,
                    head_sha,
                    root / "head",
                    self.max_file_bytes,
                    markdown_only=False,
                    progress=lambda done, total: progress("snapshot_code", done, total),
                )
            except GitHubAppError as exc:
                head_repository = pull["head"].get("repo")
                fork_name = (
                    head_repository.get("full_name") if isinstance(head_repository, dict) else None
                )
                if exc.status != 404 or not isinstance(fork_name, str):
                    raise
                head_snapshot = materialize_snapshot(
                    client,
                    fork_name,
                    head_sha,
                    root / "head_fork",
                    self.max_file_bytes,
                    markdown_only=False,
                    progress=lambda done, total: progress("snapshot_code", done, total),
                )
            for item in files:
                name = str(item["filename"])
                if item.get("status") == "removed" or name.endswith((".md", ".markdown", ".mdx")):
                    continue
                if name not in head_snapshot.included:
                    raise GitHubAppError("A changed text file is missing from the PR snapshot.")
            draft = self.analyzer.analyze(
                job.repository_id,
                base_sha,
                head_sha,
                base_snapshot.root,
                head_snapshot.root,
                files,
                progress=progress,
                pull_request_title=_optional_text(pull.get("title")),
                pull_request_description=_optional_text(pull.get("body")),
            )

        progress("checking_sha")
        current = client.pull_request(job.repository, job.number)
        current_head, current_base = _pull_shas(current)
        if current.get("draft") is not False or (current_head, current_base) != (
            head_sha,
            base_sha,
        ):
            self.store.finish(job, "stale")
            return
        if client.review_exists(job.repository, job.number, marker):
            self.store.finish(job, "done")
            return
        comments = [
            {
                "path": finding.path,
                "line": finding.line,
                "side": finding.side,
                "body": (
                    f"**{finding.category}"
                    f"{' · blocking' if finding.blocking else ''}**\n\n{finding.body}"
                ),
            }
            for finding in draft.findings
        ]
        sections = [
            "## Code Assistance review",
            f"**Verdict: {draft.event}**",
            draft.summary,
        ]
        for category, heading in (
            ("bug", "Потенциальные баги"),
            ("architecture", "Архитектурные проблемы"),
            ("recommendation", "Рекомендации"),
        ):
            selected = [item for item in draft.findings if item.category == category]
            lines = [f"- `{item.path}:{item.line}` — {item.body}" for item in selected] or [
                "- Не выявлены."
            ]
            sections.append(f"### {heading}\n" + "\n".join(lines))
        sections.append(marker)
        body = "\n\n".join(sections)
        progress("publishing")
        review_id = client.create_review(
            job.repository,
            job.number,
            {"commit_id": head_sha, "event": draft.event, "body": body, "comments": comments},
        )
        self.store.finish(job, "done", review_id)
        LOGGER.info("Published %s review for %s PR #%d", draft.event, job.repository, job.number)
        if draft.audit is not None:
            audit_json = json.dumps(
                draft.audit.log_payload(job.repository, job.number, draft),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            LOGGER.info("REVIEW_AUDIT %s", audit_json)
