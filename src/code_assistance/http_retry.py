"""Bounded retry support for transient HTTP failures."""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 15.0


Result = TypeVar("Result")


def call_with_retry(
    request: Callable[[], Result],
    *,
    operation: str,
    is_retryable: Callable[[Exception], bool],
    policy: RetryPolicy,
    logger: logging.Logger,
    retry_after: Callable[[Exception], float | None] | None = None,
    failure_details: Callable[[Exception], str | None] | None = None,
) -> Result:
    """Run a request with bounded exponential backoff and sanitized retry logs."""

    for attempt in range(1, policy.max_attempts + 1):
        attempt_started = time.monotonic()
        try:
            return request()
        except Exception as exc:
            elapsed = time.monotonic() - attempt_started
            details = failure_details(exc) if failure_details is not None else None
            if attempt >= policy.max_attempts:
                if details:
                    logger.error(
                        "HTTP operation exhausted retries operation=%s attempts=%d "
                        "attempt_duration=%.2fs error=%s %s",
                        operation,
                        attempt,
                        elapsed,
                        type(exc).__name__,
                        details,
                    )
                raise
            if not is_retryable(exc):
                raise
            server_delay = retry_after(exc) if retry_after is not None else None
            exponential = min(
                policy.max_delay_seconds,
                policy.base_delay_seconds * (2 ** (attempt - 1)),
            )
            delay = (
                min(policy.max_delay_seconds, max(0.0, server_delay))
                if server_delay is not None
                else min(
                    policy.max_delay_seconds,
                    exponential + random.uniform(0.0, min(1.0, exponential * 0.25)),
                )
            )
            logger.warning(
                "Transient HTTP failure operation=%s error=%s attempt_duration=%.2fs%s; "
                "retry=%d/%d delay=%.2fs",
                operation,
                type(exc).__name__,
                elapsed,
                f" {details}" if details else "",
                attempt + 1,
                policy.max_attempts,
                delay,
            )
            time.sleep(delay)
    raise AssertionError("retry loop did not return or raise")
