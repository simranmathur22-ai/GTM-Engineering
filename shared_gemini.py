"""Shared Gemini request retry helper for sibling local applications."""

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from google.genai import errors

logger = logging.getLogger(__name__)
T = TypeVar("T")
_request_lock = threading.Lock()
_last_request_started = 0.0


def _wait_for_request_slot() -> None:
    global _last_request_started

    interval = float(os.getenv("GEMINI_MIN_REQUEST_INTERVAL_SECONDS", "12.5"))
    if interval < 0:
        raise ValueError("GEMINI_MIN_REQUEST_INTERVAL_SECONDS cannot be negative.")

    with _request_lock:
        elapsed = time.monotonic() - _last_request_started
        delay = interval - elapsed
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


def generate_content_with_retry(
    generate: Callable[..., T],
    *,
    max_attempts: int = 3,
    **kwargs,
) -> T:
    """Retry temporary Gemini service failures with bounded exponential backoff."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    base_delay = float(os.getenv("GEMINI_TRANSIENT_RETRY_BASE_SECONDS", "2"))
    if base_delay < 0:
        raise ValueError("GEMINI_TRANSIENT_RETRY_BASE_SECONDS cannot be negative.")

    for attempt in range(max_attempts):
        _wait_for_request_slot()
        try:
            return generate(**kwargs)
        except errors.APIError as exc:
            if exc.code not in (500, 502, 503, 504) or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "Gemini returned temporary HTTP %s; retrying in %.1f seconds (%s/%s).",
                exc.code,
                delay,
                attempt + 1,
                max_attempts - 1,
            )
            time.sleep(delay)

    raise RuntimeError("Gemini retry loop exited without a response.")
