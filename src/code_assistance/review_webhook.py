"""Local GitHub App webhook receiver and single review worker."""

import hashlib
import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from code_assistance.config import load_config
from code_assistance.errors import CodeAssistanceError
from code_assistance.github_app import GitHubAppClient, GitHubAppError, GitHubAppSettings
from code_assistance.providers import OpenAIProvider, OpenAIStructuredGenerator
from code_assistance.review_analysis import REVIEW_RESPONSE_SCHEMA, ReviewAnalyzer
from code_assistance.review_service import ReviewService, _sha
from code_assistance.review_state import ReviewJob, ReviewJobStore

LOGGER = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1_000_000
PULL_ACTIONS = frozenset({"opened", "reopened", "synchronize", "ready_for_review"})


class WebhookReceiver:
    def __init__(self, secret: str, account_login: str, store: ReviewJobStore) -> None:
        self.secret = secret.encode("utf-8")
        self.account_login = account_login.casefold()
        self.store = store

    def receive(self, headers: dict[str, str], body: bytes) -> int:
        headers = {name.casefold(): value for name, value in headers.items()}
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return 401
        if headers.get("x-github-event") != "pull_request":
            return 202
        delivery_id = headers.get("x-github-delivery", "")
        if not delivery_id or len(delivery_id) > 100 or any(ord(char) < 33 for char in delivery_id):
            return 400
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400
        if not isinstance(payload, dict) or payload.get("action") not in PULL_ACTIONS:
            return 202
        pull = payload.get("pull_request")
        repository = payload.get("repository")
        installation = payload.get("installation")
        if not all(isinstance(item, dict) for item in (pull, repository, installation)):
            return 400
        assert isinstance(pull, dict)
        assert isinstance(repository, dict)
        assert isinstance(installation, dict)
        owner = repository.get("owner")
        owner_login = owner.get("login") if isinstance(owner, dict) else None
        if not isinstance(owner_login, str) or owner_login.casefold() != self.account_login:
            return 202
        if not isinstance(pull.get("draft"), bool):
            return 400
        if pull["draft"]:
            return 202
        full_name = repository.get("full_name")
        repository_id = repository.get("id")
        installation_id = installation.get("id")
        number = pull.get("number")
        head = pull.get("head")
        base = pull.get("base")
        if (
            not isinstance(full_name, str)
            or full_name.casefold().split("/")[0] != self.account_login
            or isinstance(repository_id, bool)
            or not isinstance(repository_id, int)
            or isinstance(installation_id, bool)
            or not isinstance(installation_id, int)
            or isinstance(number, bool)
            or not isinstance(number, int)
            or not isinstance(head, dict)
            or not isinstance(base, dict)
        ):
            return 400
        try:
            job = ReviewJob(
                installation_id,
                repository_id,
                full_name,
                number,
                _sha(head.get("sha")),
                _sha(base.get("sha")),
            )
        except GitHubAppError:
            return 400
        self.store.enqueue(delivery_id, job)
        return 202


def _handler(receiver: WebhookReceiver) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")

        def do_POST(self) -> None:
            if self.path != "/webhook":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if size < 1 or size > MAX_WEBHOOK_BYTES:
                self.send_error(413)
                return
            body = self.rfile.read(size)
            if len(body) != size:
                self.send_error(400)
                return
            status = receiver.receive(dict(self.headers.items()), body)
            self.send_response(status)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("webhook HTTP %s", args[1] if len(args) > 1 else "request")

    return Handler


def _worker(service: ReviewService, store: ReviewJobStore, stop: threading.Event) -> None:
    while not stop.is_set():
        job = store.claim()
        if job is None:
            stop.wait(2)
            continue
        try:
            service.process(job)
        except CodeAssistanceError as exc:
            store.fail(job, str(exc))
            LOGGER.error("Review failed for %s PR #%d: %s", job.repository, job.number, exc)
        except Exception:
            store.fail(job, "Unexpected reviewer error.")
            LOGGER.exception("Unexpected review failure for %s PR #%d", job.repository, job.number)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = GitHubAppSettings.from_environment()
    config = load_config()
    LOGGER.warning(
        "GitHub API endpoint: https://api.github.com; OpenAI endpoint: %s. "
        "PR diffs, eligible repository text and retrieved excerpts may be sent to OpenAI.",
        config.base_url,
    )
    store = ReviewJobStore(settings.data_directory / "review_jobs.sqlite3")
    provider = OpenAIProvider(config, max_retries=settings.retry_policy.max_attempts - 1)
    reviewer_chat = OpenAIStructuredGenerator(provider, "code_review", REVIEW_RESPONSE_SCHEMA)
    analyzer = ReviewAnalyzer(config, provider, reviewer_chat, settings.data_directory / "indexes")
    service = ReviewService(
        lambda installation_id: GitHubAppClient(settings, installation_id),
        analyzer,
        store,
        config.max_file_bytes,
        connection_check=provider.check_connection,
    )
    receiver = WebhookReceiver(settings.webhook_secret, settings.account_login, store)
    stop = threading.Event()
    worker = threading.Thread(target=_worker, args=(service, store, stop), daemon=True)
    worker.start()
    server = ThreadingHTTPServer(("0.0.0.0", settings.port), _handler(receiver))
    try:
        LOGGER.info("Review webhook listening on port %d", settings.port)
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
