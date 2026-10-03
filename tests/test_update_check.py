import unittest
from unittest import mock

from core import update_check
from core.update_check import (
    STATUS_ERROR, STATUS_LATEST, STATUS_NEWER, check_for_update, is_newer, parse_version,
)


class VersionTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_version("v3.1"), (3, 1))
        self.assertEqual(parse_version("3.0.1"), (3, 0, 1))
        self.assertEqual(parse_version(" V4 "), (4,))
        self.assertIsNone(parse_version("v3.1-beta"))
        self.assertIsNone(parse_version(""))
        self.assertIsNone(parse_version(None))

    def test_numeric_comparison(self):
        self.assertTrue(is_newer("v3.1", "3.0"))
        self.assertTrue(is_newer("3.0.1", "3.0"))
        self.assertTrue(is_newer("3.10", "3.9"))  # не като текст
        self.assertFalse(is_newer("3.0", "3.0"))
        self.assertFalse(is_newer("3.0.0", "3.0"))
        self.assertFalse(is_newer("2.9", "3.0"))
        self.assertFalse(is_newer("v3.1-beta", "3.0"))


class _Response:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class CheckForUpdateTest(unittest.TestCase):
    def _check(self, response=None, error=None, current="3.0"):
        with mock.patch.object(update_check.requests, "get",
                               return_value=response, side_effect=error) as get:
            result = check_for_update(current)
        return result, get

    def test_newer_version(self):
        result, get = self._check(_Response(data={
            "tag_name": "v3.1", "html_url": "https://github.com/realdark/overlingo/releases/tag/v3.1"}))
        self.assertEqual(result.status, STATUS_NEWER)
        self.assertEqual(result.latest_version, "3.1")
        self.assertTrue(result.url.endswith("/tag/v3.1"))
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
        self.assertTrue(get.call_args.kwargs["timeout"])

    def test_same_version(self):
        result, _ = self._check(_Response(data={"tag_name": "v3.0"}))
        self.assertEqual(result.status, STATUS_LATEST)

    def test_older_release_is_not_offered(self):
        result, _ = self._check(_Response(data={"tag_name": "v2.9"}))
        self.assertEqual(result.status, STATUS_LATEST)

    def test_non_numeric_tag_is_not_offered(self):
        result, _ = self._check(_Response(data={"tag_name": "v3.1-beta"}))
        self.assertEqual(result.status, STATUS_LATEST)

    def test_no_release_yet(self):
        result, _ = self._check(_Response(status_code=404))
        self.assertEqual(result.status, STATUS_LATEST)

    def test_server_error(self):
        result, _ = self._check(_Response(status_code=503))
        self.assertEqual(result.status, STATUS_ERROR)

    def test_no_internet(self):
        result, _ = self._check(error=update_check.requests.exceptions.ConnectionError("offline"))
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.current_version, "3.0")


if __name__ == "__main__":
    unittest.main()
