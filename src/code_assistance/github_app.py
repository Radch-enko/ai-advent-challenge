"""Small GitHub App REST adapter. Repository content is never executed."""

import base64
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import jwt

from code_assistance.errors import CodeAssistanceError
from code_assistance.http_retry import RETRYABLE_HTTP_STATUSES, RetryPolicy, call_with_retry

API_ROOT = "https://api.github.com"
LOGGER = logging.getLogger(__name__)


class GitHubAppError(CodeAssistanceError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GitHubAppSettings:
    app_id: str
    private_key_path: Path
    webhook_secret: str
    account_login: str
    data_directory: Path
    port: int
    retry_policy: RetryPolicy = RetryPolicy()

    @classmethod
    def from_environment(cls) -> "GitHubAppSettings":
        app_id = os.environ.get("GITHUB_APP_ID", "").strip()
        key_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
        secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()
        account = os.environ.get("GITHUB_ACCOUNT_LOGIN", "").strip()
        data_path = os.environ.get("REVIEWER_DATA_DIR", "/data").strip()
        raw_port = os.environ.get("REVIEWER_PORT", "8080")
        raw_attempts = os.environ.get("REVIEWER_HTTP_MAX_ATTEMPTS", "5")
        raw_delay = os.environ.get("REVIEWER_RETRY_BASE_SECONDS", "1")
        if not app_id.isdecimal() or not key_path or not secret or not account or not data_path:
            raise GitHubAppError("GitHub App settings are incomplete or invalid.")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise GitHubAppError("REVIEWER_PORT must be an integer.") from exc
        if not 1 <= port <= 65535:
            raise GitHubAppError("REVIEWER_PORT is out of range.")
        try:
            attempts = int(raw_attempts)
            delay = float(raw_delay)
        except ValueError as exc:
            raise GitHubAppError("Reviewer retry settings must be numeric.") from exc
        if not 1 <= attempts <= 10 or not 0.1 <= delay <= 60:
            raise GitHubAppError("Reviewer retry settings are out of range.")
        private_key_path = Path(key_path)
        if not private_key_path.is_absolute() or not private_key_path.is_file():
            raise GitHubAppError("GITHUB_APP_PRIVATE_KEY_PATH must name an existing absolute file.")
        return cls(
            app_id,
            private_key_path,
            secret,
            account,
            Path(data_path),
            port,
            RetryPolicy(max_attempts=attempts, base_delay_seconds=delay),
        )


class GitHubAppClient:
    def __init__(self, settings: GitHubAppSettings, installation_id: int) -> None:
        self.settings = settings
        self.installation_id = installation_id
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = threading.Lock()

    def _jwt(self) -> str:
        try:
            key = self.settings.private_key_path.read_text(encoding="utf-8")
            now = int(time.time())
            return str(
                jwt.encode(
                    {"iat": now - 60, "exp": now + 540, "iss": self.settings.app_id},
                    key,
                    algorithm="RS256",
                )
            )
        except (OSError, ValueError, jwt.PyJWTError) as exc:
            raise GitHubAppError("The GitHub App private key is unavailable or invalid.") from exc

    def _installation_token(self) -> str:
        if self._token is not None and time.time() < self._token_expires - 60:
            return self._token
        with self._token_lock:
            if self._token is not None and time.time() < self._token_expires - 60:
                return self._token
            response = self._request(
                "POST",
                f"/app/installations/{self.installation_id}/access_tokens",
                auth=self._jwt(),
            )
            token = response.get("token")
            if not isinstance(token, str) or not token:
                raise GitHubAppError("GitHub did not return an installation token.")
            self._token = token
            self._token_expires = time.time() + 3500
            return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: str,
        body: Mapping[str, object] | None = None,
        operation: str = "GitHub API",
        reconcile: Callable[[], Any | None] | None = None,
    ) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            API_ROOT + path,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {auth}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "code-assistance-reviewer",
                "Content-Type": "application/json",
            },
        )
        ambiguous = False

        def send() -> Any:
            nonlocal ambiguous
            if ambiguous and reconcile is not None:
                recovered = reconcile()
                if recovered is not None:
                    return recovered
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except Exception as exc:
                if self._is_retryable(exc):
                    ambiguous = True
                raise

        try:
            value = call_with_retry(
                send,
                operation=operation,
                is_retryable=self._is_retryable,
                policy=self.settings.retry_policy,
                logger=LOGGER,
                retry_after=self._retry_after,
            )
        except HTTPError as exc:
            raise GitHubAppError(f"GitHub API returned HTTP {exc.code}.", exc.code) from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise GitHubAppError("GitHub API is unavailable or returned invalid JSON.") from exc
        return value

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        if isinstance(error, HTTPError):
            return error.code in RETRYABLE_HTTP_STATUSES
        return isinstance(error, (URLError, TimeoutError, ConnectionError, OSError))

    @staticmethod
    def _retry_after(error: Exception) -> float | None:
        if not isinstance(error, HTTPError):
            return None
        value = error.headers.get("Retry-After") if error.headers is not None else None
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _get(self, path: str) -> dict[str, Any]:
        value = self._request("GET", path, auth=self._installation_token())
        if not isinstance(value, dict):
            raise GitHubAppError("GitHub API returned an invalid object.")
        return value

    @staticmethod
    def _repo_path(full_name: str) -> str:
        parts = full_name.split("/")
        if len(parts) != 2 or not all(parts) or any(part in {".", ".."} for part in parts):
            raise GitHubAppError("GitHub returned an invalid repository name.")
        return "/repos/" + "/".join(quote(part, safe="") for part in parts)

    def pull_request(self, full_name: str, number: int) -> dict[str, Any]:
        return self._get(f"{self._repo_path(full_name)}/pulls/{number}")

    def pull_files(self, full_name: str, number: int, expected_count: int) -> list[dict[str, Any]]:
        if expected_count > 3000:
            raise GitHubAppError("GitHub limits PR file listings to 3000 files.")
        files: list[dict[str, Any]] = []
        for page in range(1, 32):
            value = self._request(
                "GET",
                f"{self._repo_path(full_name)}/pulls/{number}/files?per_page=100&page={page}",
                auth=self._installation_token(),
            )
            # The list endpoint returns an array, unlike other GitHub endpoints.
            if not isinstance(value, list):
                raise GitHubAppError("GitHub returned an invalid PR file list.")
            if any(not isinstance(item, dict) for item in value):
                raise GitHubAppError("GitHub returned an invalid PR file entry.")
            files.extend(value)
            if len(value) < 100:
                break
        if len(files) != expected_count:
            raise GitHubAppError("GitHub returned an incomplete PR file list.")
        return files

    def tree(self, full_name: str, ref: str) -> list[dict[str, Any]]:
        value = self._get(
            f"{self._repo_path(full_name)}/git/trees/{quote(ref, safe='')}?recursive=1"
        )
        entries = value.get("tree")
        if value.get("truncated") is not False or not isinstance(entries, list):
            raise GitHubAppError("GitHub returned an incomplete repository tree.")
        return entries

    def commit_tree_sha(self, full_name: str, commit_sha: str) -> str:
        value = self._get(f"{self._repo_path(full_name)}/git/commits/{quote(commit_sha, safe='')}")
        tree = value.get("tree")
        sha = tree.get("sha") if isinstance(tree, dict) else None
        if not isinstance(sha, str):
            raise GitHubAppError("GitHub returned a commit without a tree SHA.")
        return sha

    def blob(self, full_name: str, sha: str, max_bytes: int) -> bytes:
        value = self._get(f"{self._repo_path(full_name)}/git/blobs/{quote(sha, safe='')}")
        size = value.get("size")
        content = value.get("content")
        if not isinstance(size, int) or not isinstance(content, str):
            raise GitHubAppError("GitHub returned an invalid blob.")
        if size > max_bytes:
            raise GitHubAppError("A repository blob exceeds the snapshot limit.")
        try:
            data = base64.b64decode(content, validate=False)
        except ValueError as exc:
            raise GitHubAppError("GitHub returned invalid blob encoding.") from exc
        if len(data) != size:
            raise GitHubAppError("GitHub returned a truncated blob.")
        return data

    def create_review(self, full_name: str, number: int, payload: Mapping[str, object]) -> int:
        review_body = payload.get("body")
        marker = self._review_marker(review_body) if isinstance(review_body, str) else None

        def reconcile() -> dict[str, int] | None:
            if marker is None:
                return None
            review_id = self.review_id_for_marker(full_name, number, marker)
            return {"id": review_id} if review_id is not None else None

        value = self._request(
            "POST",
            f"{self._repo_path(full_name)}/pulls/{number}/reviews",
            auth=self._installation_token(),
            body=payload,
            operation="GitHub publish review",
            reconcile=reconcile,
        )
        if not isinstance(value, dict):
            raise GitHubAppError("GitHub API returned an invalid object.")
        review_id = value.get("id")
        if not isinstance(review_id, int):
            raise GitHubAppError("GitHub did not confirm creation of the review.")
        return review_id

    @staticmethod
    def _review_marker(body: str) -> str | None:
        start = body.rfind("<!-- code-assistance-reviewer:")
        end = body.find("-->", start)
        if start < 0 or end < 0:
            return None
        return body[start : end + 3]

    def review_id_for_marker(self, full_name: str, number: int, marker: str) -> int | None:
        for page in range(1, 32):
            value = self._request(
                "GET",
                f"{self._repo_path(full_name)}/pulls/{number}/reviews?per_page=100&page={page}",
                auth=self._installation_token(),
            )
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise GitHubAppError("GitHub returned an invalid review list.")
            for item in value:
                review_id = item.get("id")
                if marker in str(item.get("body", "")) and isinstance(review_id, int):
                    return review_id
            if len(value) < 100:
                return None
        raise GitHubAppError("GitHub review history exceeds the safety limit.")

    def review_exists(self, full_name: str, number: int, marker: str) -> bool:
        return self.review_id_for_marker(full_name, number, marker) is not None
