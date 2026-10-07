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


class AppFoldersTest(unittest.TestCase):
    """Where assets live and where settings are written - different in the macOS .app bundle."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _frozen(self, platform, executable, meipass=None):
        patches = [
            mock.patch.object(config.sys, "frozen", True, create=True),
            mock.patch.object(config.sys, "platform", platform),
            mock.patch.object(config.sys, "executable", str(executable)),
        ]
        if meipass is not None:
            patches.append(mock.patch.object(config.sys, "_MEIPASS", str(meipass), create=True))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_windows_linux_keep_everything_next_to_the_program(self):
        (self.dir / "assets").mkdir()
        self._frozen("win32", self.dir / "overlingo.exe")
        self.assertEqual(config.get_resource_dir(), self.dir)
        self.assertEqual(config.get_data_dir(), self.dir)

    def test_macos_app_reads_bundled_assets_and_writes_to_application_support(self):
        macos = self.dir / "Overlingo.app" / "Contents" / "MacOS"
        frameworks = self.dir / "Overlingo.app" / "Contents" / "Frameworks"
        (frameworks / "assets").mkdir(parents=True)
        macos.mkdir(parents=True)
        self._frozen("darwin", macos / "Overlingo", meipass=frameworks)
        home = self.dir / "home"
        with mock.patch.object(config.Path, "home", return_value=home):
            self.assertEqual(config.get_resource_dir(), frameworks)
            self.assertEqual(config.get_data_dir(), home / "Library" / "Application Support" / "Overlingo")
            self.assertTrue(config.get_data_dir().is_dir())
