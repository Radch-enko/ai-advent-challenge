import hashlib
import hmac
import json
from pathlib import Path

import pytest

from code_assistance.review_state import ReviewJob, ReviewJobStore
from code_assistance.review_webhook import WebhookReceiver

HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40


def _webhook_request(delivery_id: str) -> tuple[dict[str, str], bytes]:
    body = json.dumps(
        {
            "action": "ready_for_review",
            "installation": {"id": 12},
            "repository": {
                "id": 34,
                "full_name": "owner/project",
                "owner": {"login": "owner"},
            },
            "pull_request": {
                "number": 5,
                "draft": False,
                "head": {"sha": HEAD_SHA},
                "base": {"sha": BASE_SHA},
            },
        }
    ).encode()
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    return (
        {
            "x-hub-signature-256": f"sha256={signature}",
            "x-github-event": "pull_request",
            "x-github-delivery": delivery_id,
        },
        body,
    )


def test_reset_allows_redelivery_of_same_delivery_id(tmp_path: Path) -> None:
    store = ReviewJobStore(tmp_path / "review_jobs.sqlite3")
    job = ReviewJob(12, 34, "owner/project", 5, HEAD_SHA, BASE_SHA)
    headers, body = _webhook_request("delivery-1")
    assert WebhookReceiver("test-secret", "owner", store).receive(headers, body) == 202
    assert store.claim() == job
    store.finish(job, "done", review_id=77)

    reset_job, previous_state, previous_review_id = store.prepare_redelivery(
        "owner/project", 5, head_sha=HEAD_SHA, base_sha=BASE_SHA
    )

    assert reset_job == job
    assert previous_state == "done"
    assert previous_review_id == 77
    assert WebhookReceiver("test-secret", "owner", store).receive(headers, body) == 202
    assert store.claim() == job


def test_reset_refuses_running_job_without_recovering_it(tmp_path: Path) -> None:
    database = tmp_path / "review_jobs.sqlite3"
    store = ReviewJobStore(database)
    job = ReviewJob(12, 34, "owner/project", 5, HEAD_SHA, BASE_SHA)
    assert store.enqueue("delivery-1", job)
    assert store.claim() == job

    admin_store = ReviewJobStore(database, recover_interrupted=False)
    with pytest.raises(ValueError, match="is running"):
        admin_store.prepare_redelivery("owner/project", 5, head_sha=HEAD_SHA)
