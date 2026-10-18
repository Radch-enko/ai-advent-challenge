"""Prepare one stored PR review job for webhook redelivery."""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

from code_assistance.review_state import ReviewJobStore


def _sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("SHA must contain exactly 40 hexadecimal characters.")
    return value.lower()


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PR number must be a positive integer.") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("PR number must be a positive integer.")
    return number


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset one stored PR review task so GitHub webhook redelivery can enqueue it."
    )
    parser.add_argument(
        "--repository", required=True, help="Repository full name, for example owner/project"
    )
    parser.add_argument("--pr", required=True, type=_positive_integer, help="Pull request number")
    parser.add_argument("--head-sha", type=_sha, help="Select a specific PR head commit")
    parser.add_argument("--base-sha", type=_sha, help="Select a specific base commit")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", arguments.repository):
        print("Repository must use the owner/name format.", file=sys.stderr)
        raise SystemExit(2)

    data_directory = Path(os.environ.get("REVIEWER_DATA_DIR", "").strip() or "/data")
    try:
        store = ReviewJobStore(data_directory / "review_jobs.sqlite3", recover_interrupted=False)
        job, previous_state, previous_review_id = store.prepare_redelivery(
            arguments.repository,
            arguments.pr,
            head_sha=arguments.head_sha,
            base_sha=arguments.base_sha,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Cannot prepare review task for redelivery: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Prepared {job.repository} PR #{job.number} for webhook redelivery.")
    print(f"Selected head SHA: {job.head_sha}")
    print(f"Selected base SHA: {job.base_sha}")
    print(f"Previous state: {previous_state}; new local state: failed (retryable).")
    if previous_review_id is not None:
        print(
            "A review was previously published for this task. Its GitHub review marker must be "
            "removed before redelivery can produce a new model run."
        )
    print(
        "Now redeliver the matching webhook in GitHub App settings → Advanced → Recent Deliveries."
    )


if __name__ == "__main__":
    main()
