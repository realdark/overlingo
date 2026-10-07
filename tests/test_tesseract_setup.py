import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import tesseract_setup


class ConfigureTesseractTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        cmd = mock.patch.object(tesseract_setup.pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        cmd.start()
        self.addCleanup(cmd.stop)

    def _paths(self, paths):
        return mock.patch.object(tesseract_setup, "TESSERACT_PATHS", paths)

    def test_not_installed(self):
        with self._paths([self.root / "missing" / "tesseract"]):
            self.assertIsNone(tesseract_setup.configure_tesseract())
        self.assertNotIn("TESSDATA_PREFIX", os.environ)

    def test_found_sets_tessdata_and_path_once(self):
        binary = self.root / "bin" / "tesseract"
        binary.parent.mkdir()
        binary.write_bytes(b"")
        tessdata = self.root / "share" / "tessdata"
        tessdata.mkdir(parents=True)

        with self._paths([self.root / "other" / "tesseract", binary]):
            self.assertEqual(tesseract_setup.configure_tesseract(), binary)
            tesseract_setup.configure_tesseract()  # "Check again" - must not keep growing PATH

        self.assertEqual(os.environ["TESSDATA_PREFIX"], str(tessdata))
        self.assertEqual(os.environ["PATH"].split(os.pathsep).count(str(binary.parent)), 1)
        self.assertEqual(tesseract_setup.pytesseract.pytesseract.tesseract_cmd, str(binary))


class InstallHintTest(unittest.TestCase):
    def test_each_platform_has_a_command(self):
        self.assertIn("winget", tesseract_setup.install_hint("win32")[0])
        self.assertIsNotNone(tesseract_setup.install_hint("win32")[1])
        self.assertIn("brew", tesseract_setup.install_hint("darwin")[0])
        self.assertIn("apt", tesseract_setup.install_hint("linux")[0])

    def test_terminal_hint(self):
        self.assertEqual(tesseract_setup.terminal_hint_key("win32"), "terminal_hint_windows")
        self.assertEqual(tesseract_setup.terminal_hint_key("linux"), "terminal_hint_linux")


if __name__ == "__main__":
    unittest.main()
