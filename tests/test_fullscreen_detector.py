import unittest
from unittest import mock

from core import fullscreen_detector as fd
from core.fullscreen_detector import FullscreenDetector


class _Completed:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.returncode = stdout, returncode


class FullscreenCheckTest(unittest.TestCase):
    def setUp(self):
        # each test starts with an empty cache and xprop available
        for attr, value in (("_cached_at", 0.0), ("_cached_active", False), ("_xprop_available", True)):
            patcher = mock.patch.object(FullscreenDetector, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        linux = mock.patch.object(fd, "IS_LINUX", True)
        linux.start()
        self.addCleanup(linux.stop)

    def _xprop(self, fullscreen):
        def run(args, **kwargs):
            if "-root" in args:
                return _Completed("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3a00007")
            return _Completed("_NET_WM_STATE(ATOM) = _NET_WM_STATE_FULLSCREEN" if fullscreen else "_NET_WM_STATE(ATOM) =")
        return mock.patch.object(fd.subprocess, "run", side_effect=run)

    def test_detects_fullscreen_window(self):
        with self._xprop(True):
            self.assertTrue(FullscreenDetector.is_fullscreen_application_active())

    def test_normal_window(self):
        with self._xprop(False):
            self.assertFalse(FullscreenDetector.is_fullscreen_application_active())

    def test_result_is_shared_and_cached(self):
        """Several windows within the same second - xprop runs only once (2 calls)."""
        with self._xprop(True) as run:
            for _ in range(5):
                FullscreenDetector.is_fullscreen_application_active()
        self.assertEqual(run.call_count, 2)

    def test_missing_xprop_is_not_retried(self):
        with mock.patch.object(fd.subprocess, "run", side_effect=FileNotFoundError("xprop")) as run, \
             mock.patch.object(fd.time, "monotonic", side_effect=[100.0, 200.0, 300.0]):
            for _ in range(3):
                self.assertFalse(FullscreenDetector.is_fullscreen_application_active())
        self.assertEqual(run.call_count, 1)

    def test_not_linux(self):
        with mock.patch.object(fd, "IS_LINUX", False), self._xprop(True) as run:
            self.assertFalse(FullscreenDetector.is_fullscreen_application_active())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
