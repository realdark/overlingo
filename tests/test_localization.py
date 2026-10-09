import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import localization
from core.localization import UiLocalizer
from utils.config import LOCALES_DIR


class LocaleFilesTest(unittest.TestCase):
    """Both languages must have the same keys - otherwise part of the
    UI stays untranslated in one of them."""

    def _load(self, lang):
        with open(LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
            return json.load(f)

    def test_bg_and_en_have_same_keys(self):
        bg, en = self._load("bg"), self._load("en")
        self.assertEqual(sorted(set(bg) - set(en)), [], "ключове само в bg.json")
        self.assertEqual(sorted(set(en) - set(bg)), [], "ключове само в en.json")

    def test_same_placeholders_in_both_languages(self):
        """{folder}, {error} etc. must match - otherwise .format() crashes in the error dialog."""
        bg, en = self._load("bg"), self._load("en")
        field = re.compile(r"\{(\w*)\}")
        diff = {k: (field.findall(bg[k]), field.findall(en[k]))
                for k in en if sorted(field.findall(bg[k])) != sorted(field.findall(en[k]))}
        self.assertEqual(diff, {})

    def test_no_empty_texts(self):
        for lang in ("bg", "en"):
            empty = [k for k, v in self._load(lang).items() if not str(v).strip()]
            self.assertEqual(empty, [], f"празни текстове в {lang}.json")


PROJECT_DIR = Path(__file__).resolve().parent.parent

# tr("key") / t("key"), errors from threads and from settings validation
_KEY_PATTERNS = [
    re.compile(r"""\btr?\(\s*["']([a-z][a-z0-9_]*)["']"""),
    re.compile(r"""\.emit\([^)]*?["']([a-z][a-z0-9_]*)["'](?!\s*:)"""),  # excluding dict keys
    re.compile(r"""translation_failed\.emit\(\s*["']([a-z][a-z0-9_]*)["']"""),
    re.compile(r"""SettingsValidationError\(\s*["']([a-z][a-z0-9_]*)["']"""),
    re.compile(r"""CaptureError\(\s*["']([a-z][a-z0-9_]*)["']"""),
]


def keys_used_in_code():
    used = set()
    for folder in ("core", "ui", "utils"):
        for path in (PROJECT_DIR / folder).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in _KEY_PATTERNS:
                used.update(pattern.findall(text))
    main = (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
    for pattern in _KEY_PATTERNS:
        used.update(pattern.findall(main))
    return used


class KeysUsedInCodeTest(unittest.TestCase):
    def test_every_key_used_in_code_exists(self):
        with open(LOCALES_DIR / "en.json", encoding="utf-8") as f:
            known = set(json.load(f))
        missing = sorted(keys_used_in_code() - known)
        self.assertEqual(missing, [], "ключове, използвани в кода, но липсващи в JSON")

    def test_every_json_key_is_used_somewhere(self):
        """The reverse direction: text that is never referenced in the code is unused."""
        code = "\n".join(
            p.read_text(encoding="utf-8")
            for folder in ("core", "ui", "utils") for p in (PROJECT_DIR / folder).glob("*.py")
        ) + (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
        with open(LOCALES_DIR / "en.json", encoding="utf-8") as f:
            keys = json.load(f)
        unused = [k for k in keys if not re.search(r"""["']""" + re.escape(k) + r"""["']""", code)]
        self.assertEqual(unused, [], "ключове в JSON, които не се ползват никъде")


class UiLocalizerTest(unittest.TestCase):
    def test_switching_language(self):
        i18n = UiLocalizer()
        self.assertTrue(i18n.set_language("en"))
        self.assertEqual(i18n.tr("save_button"), "Save")
        self.assertTrue(i18n.set_language("bg"))
        self.assertEqual(i18n.tr("save_button"), "Запази")

    def test_unknown_language_is_rejected(self):
        i18n = UiLocalizer()
        i18n.set_language("en")
        self.assertFalse(i18n.set_language("xx"))
        self.assertEqual(i18n.current_lang, "en")

    def test_unknown_key_returns_key(self):
        self.assertEqual(UiLocalizer().tr("no_such_key"), "no_such_key")


class UiLocalizerRobustnessTest(unittest.TestCase):
    def _localizer_with_files(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, content in files.items():
            (Path(tmp.name) / name).write_text(content, encoding="utf-8")
        with mock.patch.object(localization, "LOCALES_DIR", Path(tmp.name)):
            return UiLocalizer()

    def test_missing_text_falls_back_to_english(self):
        i18n = self._localizer_with_files({
            "en.json": json.dumps({"hello": "Hello", "only_en": "English only"}),
            "bg.json": json.dumps({"hello": "Здравей"}),
        })
        i18n.set_language("bg")
        self.assertEqual(i18n.tr("hello"), "Здравей")
        self.assertEqual(i18n.tr("only_en"), "English only")

    def test_corrupted_file_is_skipped(self):
        i18n = self._localizer_with_files({
            "en.json": json.dumps({"hello": "Hello"}),
            "bg.json": "{ broken",
        })
        self.assertEqual(i18n.available_languages, ["en"])
        self.assertFalse(i18n.set_language("bg"))
        self.assertEqual(i18n.tr("hello"), "Hello")

    def test_missing_folder_does_not_crash(self):
        with mock.patch.object(localization, "LOCALES_DIR", Path("/no/such/folder")):
            i18n = UiLocalizer()
        self.assertEqual(i18n.available_languages, [])
        self.assertEqual(i18n.tr("save_button"), "save_button")


class VersionTest(unittest.TestCase):
    def test_about_text_shows_version(self):
        from utils.version import APP_VERSION
        for lang in ("bg", "en"):
            with open(LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
                text = json.load(f)["about_version"]
            self.assertIn(APP_VERSION, text.format(version=APP_VERSION))
        self.assertRegex(APP_VERSION, r"^\d+\.\d+")


if __name__ == "__main__":
    unittest.main()


class HelpSectionTest(unittest.TestCase):
    def test_lines_become_bullets_and_are_escaped(self):
        from ui.dialogs import help_section_html
        html = help_section_html("Audio", "First line\n\nSecond <b>line</b>\n")
        self.assertIn("<h3>Audio</h3>", html)
        self.assertEqual(html.count("<li"), 2)
        self.assertIn("&lt;b&gt;", html)


class NoUntranslatedButtonsTest(unittest.TestCase):
    """Qt's standard buttons (OK, Close, Yes...) stay in English - we don't load Qt's translations."""

    def test_no_standard_message_box_buttons(self):
        pattern = re.compile(
            r"QMessageBox\.(information|warning|critical|question)\(|setStandardButtons|"
            r"QMessageBox\.(Ok|Close|Yes|No|Cancel)\b|QDialogButtonBox\.(Ok|Close|Cancel|Save)\b"
        )
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for path in sorted((root / "ui").glob("*.py")) + sorted((root / "core").glob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "use ui.dialogs.show_message / addButton(i18n text) instead")
