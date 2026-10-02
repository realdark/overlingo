import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import config


class TessdataTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _env(self, value):
        env = dict(os.environ)
        env.pop("TESSDATA_PREFIX", None)
        if value is not None:
            env["TESSDATA_PREFIX"] = str(value)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_languages_come_from_tessdata_prefix(self):
        for name in ("eng", "bul", "osd"):
            (self.dir / f"{name}.traineddata").write_bytes(b"")
        with self._env(self.dir):
            self.assertEqual(config.get_tessdata_dir(), self.dir)
            self.assertEqual(config.get_available_ocr_languages(), ["bul", "eng"])

    def test_without_tessdata_there_is_no_download_folder(self):
        with self._env(None):
            self.assertIsNone(config.get_tessdata_dir())
            self.assertEqual(config.get_available_ocr_languages(), ["eng"])

    def test_missing_folder_is_ignored(self):
        with self._env(self.dir / "missing"):
            self.assertIsNone(config.get_tessdata_dir())


class FindTessdataDirTest(unittest.TestCase):
    def test_linux_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            tessdata = root / "share" / "tesseract-ocr" / "5" / "tessdata"
            tessdata.mkdir(parents=True)
            self.assertEqual(config.find_tessdata_dir(root / "bin" / "tesseract"), tessdata)

    def test_windows_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tessdata").mkdir()
            self.assertEqual(config.find_tessdata_dir(root / "tesseract.exe"), root / "tessdata")


class DefaultSettingsTest(unittest.TestCase):
    def test_obsolete_keys_are_not_defaults(self):
        for key in config.OBSOLETE_SETTINGS:
            self.assertNotIn(key, config.DEFAULT_SETTINGS)

    def test_image_path_is_absolute(self):
        self.assertTrue(Path(config.image_path("play_button.png")).is_absolute())

    def test_all_toolbar_icons_exist(self):
        for name in ("retranslate_button_white.png", "history_button_white.png",
                     "text_translate_button_white.png", "stop_button_white.png",
                     "play_button_white.png", "copy_button_white.png"):
            self.assertTrue(Path(config.image_path(name)).exists(), name)


if __name__ == "__main__":
    unittest.main()
