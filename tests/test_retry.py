import unittest
from unittest import mock

from core import retry


class _Response:
    def __init__(self, status_code=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _HttpError(Exception):
    def __init__(self, status_code, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.response = _Response(status_code, headers)


class IsRetryableErrorTest(unittest.TestCase):
    def test_rate_limit_and_server_errors_are_retryable(self):
        for status in (429, 500, 502, 503, 504):
            self.assertTrue(retry.is_retryable_error(_HttpError(status)), status)

    def test_client_errors_are_not_retryable(self):
        for status in (400, 401, 403, 404):
            self.assertFalse(retry.is_retryable_error(_HttpError(status)), status)

    def test_timeout_and_connection_messages_are_retryable(self):
        self.assertTrue(retry.is_retryable_error(Exception("Read timed out")))
        self.assertTrue(retry.is_retryable_error(Exception("Connection reset")))

    def test_unrelated_error_is_not_retryable(self):
        self.assertFalse(retry.is_retryable_error(ValueError("invalid key")))


class RetryAfterTest(unittest.TestCase):
    def test_reads_retry_after_header(self):
        self.assertEqual(retry.retry_after_seconds(_HttpError(429, {"Retry-After": "3"})), 3.0)

    def test_missing_or_invalid_header_gives_none(self):
        self.assertIsNone(retry.retry_after_seconds(_HttpError(429)))
        self.assertIsNone(retry.retry_after_seconds(_HttpError(429, {"Retry-After": "soon"})))
        self.assertIsNone(retry.retry_after_seconds(Exception("no response")))


@mock.patch("core.retry.time.sleep")
class RetryWithBackoffTest(unittest.TestCase):
    def test_returns_result_without_retry(self, sleep):
        self.assertEqual(retry.retry_with_backoff(lambda: "ok"), "ok")
        sleep.assert_not_called()

    def test_retries_temporary_error_then_succeeds(self, sleep):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise _HttpError(503)
            return "ok"

        self.assertEqual(retry.retry_with_backoff(flaky, max_attempts=3), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_stops_immediately_on_permanent_error(self, sleep):
        calls = []

        def broken():
            calls.append(1)
            raise _HttpError(401)

        with self.assertRaises(_HttpError):
            retry.retry_with_backoff(broken, max_attempts=3)
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_gives_up_after_max_attempts(self, sleep):
        calls = []

        def always_busy():
            calls.append(1)
            raise _HttpError(429)

        with self.assertRaises(_HttpError):
            retry.retry_with_backoff(always_busy, max_attempts=3)
        self.assertEqual(len(calls), 3)

    def test_wait_is_capped_by_max_delay(self, sleep):
        def busy():
            raise _HttpError(429, {"Retry-After": "100"})

        with self.assertRaises(_HttpError):
            retry.retry_with_backoff(busy, max_attempts=2, max_delay=5)
        sleep.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
