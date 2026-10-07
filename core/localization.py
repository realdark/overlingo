"""
USER INTERFACE LOCALIZATION (i18n)

The texts live ONLY in assets/locales/<language>.json - the single source of truth.
(Up to 2.x there was also a copy of all texts here, in Python, which had to be
kept in sync with the JSON files by hand.)

If a file is missing or corrupted, the program does not crash: the error goes to
app.log, and in place of the text the English version is shown or,
if that is missing too, the key itself (e.g. "settings_button_tooltip") - so
it's immediately visible which text is missing.
"""

from utils.imports import json, os
from utils.config import LOCALES_DIR
from utils.logging_setup import logger

FALLBACK_LANGUAGE = "en"


class UiLocalizer:
    def __init__(self):
        self.current_lang = FALLBACK_LANGUAGE
        self.translations = {}
        self.available_languages = []
        self.load_translations()

    def load_translations(self):
        """Loads all .json files from the locales folder."""
        if not os.path.isdir(LOCALES_DIR):
            logger.error(f"UI texts folder is missing: {LOCALES_DIR}")
            return

        for file in sorted(os.listdir(LOCALES_DIR)):
            if not file.endswith(".json"):
                continue
            lang_code = file[: -len(".json")]
            try:
                with open(os.path.join(LOCALES_DIR, file), "r", encoding="utf-8") as f:
                    self.translations[lang_code] = json.load(f)
                self.available_languages.append(lang_code)
            except Exception as e:
                logger.error(f"Error loading {file}: {e}", exc_info=True)

        if not self.available_languages:
            logger.error(f"No valid text files found in {LOCALES_DIR}")

    def set_language(self, lang_code):
        """Changes the current language. Returns False if that language is not loaded."""
        if lang_code in self.translations:
            self.current_lang = lang_code
            return True
        return False

    def tr(self, key):
        """Text for the key: from the current language, then from English, finally the key itself."""
        for lang in (self.current_lang, FALLBACK_LANGUAGE):
            text = self.translations.get(lang, {}).get(key)
            if text is not None:
                return text
        return key
