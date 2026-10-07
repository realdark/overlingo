"""
RETRY WITH EXPONENTIAL BACKOFF

Shared helper for transient translation errors (rate limit / 429, temporary
server problem, timeout). Does NOT retry errors for which a new attempt
is pointless (e.g. an invalid API key) - see is_retryable_error.
"""

import time

from utils.logging_setup import logger

RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


def is_retryable_error(exc):
    """
    Heuristic: is this error worth retrying?
    - HTTP 429 / 5xx -> yes (rate limit or temporary server problem)
    - timeout / connection errors -> yes
    - everything else (e.g. invalid key, 4xx other than 429) -> no
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in RETRYABLE_HTTP_STATUS:
        return True
    text = str(exc).lower()
    return any(hint in text for hint in ("429", "too many requests", "timeout", "timed out", "connection"))


def retry_after_seconds(exc):
    """If the server sent a Retry-After header, returns its value in seconds."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    value = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def retry_with_backoff(func, max_attempts=3, base_delay=1.0, max_delay=8.0, label=""):
    """
    Runs func() up to max_attempts times. On an error that
    is_retryable_error() deems "not worth it", stops immediately and re-raises
    it - otherwise waits (base_delay, base_delay*2, base_delay*4, ...,
    capped at max_delay; or Retry-After, if the server sent one) and
    tries again.
    """
    delay = base_delay
    prefix = f"[{label}] " if label else ""

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            if attempt >= max_attempts or not is_retryable_error(e):
                if attempt > 1:
                    logger.error(f"{prefix}Attempts exhausted ({attempt}/{max_attempts}): {e}")
                raise

            wait = retry_after_seconds(e) or delay
            logger.warning(
                f"{prefix}Attempt {attempt}/{max_attempts} failed ({e}) - retrying in {wait:.1f}s"
            )
            time.sleep(min(wait, max_delay))
            delay *= 2
