"""
RETRY С ЕКСПОНЕНЦИАЛНО ИЗЧАКВАНЕ

Общ helper за временни грешки при превод (rate limit / 429, временен
проблем на сървъра, timeout). НЕ повтаря опити при грешки, за които
нов опит е безсмислен (напр. невалиден API ключ) - виж is_retryable_error.
"""

import time

from utils.logging_setup import logger

RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


def is_retryable_error(exc):
    """
    Евристика: заслужава ли си нов опит за тази грешка.
    - HTTP 429 / 5xx -> да (rate limit или временен проблем на сървъра)
    - timeout / connection грешки -> да
    - всичко друго (напр. невалиден ключ, 4xx различен от 429) -> не
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in RETRYABLE_HTTP_STATUS:
        return True
    text = str(exc).lower()
    return any(hint in text for hint in ("429", "too many requests", "timeout", "timed out", "connection"))


def retry_after_seconds(exc):
    """Ако сървърът е подал Retry-After хедър, връща стойността му в секунди."""
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
    Изпълнява func() до max_attempts пъти. При грешка, за която
    is_retryable_error() каже "не си заслужава", спира веднага и я подава
    нагоре - иначе изчаква (base_delay, base_delay*2, base_delay*4, ...,
    ограничено до max_delay; или Retry-After, ако сървърът го е подал) и
    опитва пак.
    """
    delay = base_delay
    prefix = f"[{label}] " if label else ""

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            if attempt >= max_attempts or not is_retryable_error(e):
                if attempt > 1:
                    logger.error(f"{prefix}Изчерпани опити ({attempt}/{max_attempts}): {e}")
                raise

            wait = retry_after_seconds(e) or delay
            logger.warning(
                f"{prefix}Опит {attempt}/{max_attempts} неуспешен ({e}) - нов опит след {wait:.1f}s"
            )
            time.sleep(min(wait, max_delay))
            delay *= 2
