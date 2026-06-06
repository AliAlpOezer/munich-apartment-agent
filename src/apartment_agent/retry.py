"""Shared retry policy for flaky external calls (scraping, LLM APIs).

Transient failures — timeouts, rate limits, 5xx — are common when scraping and when hitting free
LLM tiers. A bounded exponential-with-jitter retry smooths them out without hammering the target.
"""

from __future__ import annotations

import logging

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)


def is_transient(exc: BaseException) -> bool:
    """Worth retrying? Timeouts/connection drops and 429/5xx are; permanent 4xx (e.g. a 400
    'response_format unavailable' from a free model) are not — fail fast so the router escalates.
    Unknown errors (e.g. curl_cffi scraping failures without a status) default to retryable."""
    if isinstance(exc, TimeoutError | ConnectionError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return True


def network_retry(attempts: int = 3, *, max_wait: float = 15.0):
    """Decorator: retry transient failures up to `attempts`, exponential backoff + jitter.

    `reraise=True` so the original exception (not tenacity's RetryError) surfaces to the caller's
    own error handling once retries are exhausted.
    """
    return retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=1.0, max=max_wait),
        retry=retry_if_exception(is_transient),
        before_sleep=before_sleep_log(log, logging.WARNING),
    )
