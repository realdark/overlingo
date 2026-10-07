"""
SETTINGS MANAGEMENT (load / save / validation)

Extracted from ui/main_window.py. Does not depend on Qt widgets - works only
with plain dicts, so it is easy to test and reuse.
"""

from utils.imports import json, os, edge_tts
from utils.config import SETTINGS_FILE, DEFAULT_SETTINGS, OBSOLETE_SETTINGS
from utils.logging_setup import logger
from core.translations import create_translator, NoInternetError
from core import argos
from core.hotkey_manager import combo_error

# Left unchanged by "Restore default settings":
# the paid-service key is tedious to enter again, and the window
# positions are not a "setting" the user chose deliberately.
KEPT_ON_RESET = ("translation_api_key", "window_pos", "text_window_geometry")


class SettingsValidationError(Exception):
    """Raised on invalid settings. `message_key` is the translation key for the UI message."""

    def __init__(self, message_key, detail=""):
        self.message_key = message_key
        self.detail = detail
        super().__init__(message_key)


class SettingsManager:
    """Loads, validates and saves the application settings in SETTINGS_FILE."""

    def load(self):
        """Loads settings from the file, filled in with DEFAULT_SETTINGS for missing fields."""
        settings = dict(DEFAULT_SETTINGS)
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings.update(json.load(f))
        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
        for key in OBSOLETE_SETTINGS:
            settings.pop(key, None)
        # Up to 3.1 there was Ollama - it's gone now; Google works right away, with no setup.
        if settings.get("translation_api") == "ollama":
            settings["translation_api"] = "google"
        return settings

    def defaults_for_reset(self, current):
        """The default settings, keeping KEPT_ON_RESET from current."""
        settings = dict(DEFAULT_SETTINGS)
        for key in KEPT_ON_RESET:
            if key in current:
                settings[key] = current[key]
        return settings

    def save(self, settings):
        """
        Saves the settings to the file. First the whole text, then a temporary
        file that replaces the old one in one step - if something fails midway
        (a value that can't be serialized, a crash, a power cut),
        the old settings.json stays intact instead of half-written
        (which on the next start would wipe all settings).
        """
        tmp_path = f"{SETTINGS_FILE}.tmp"
        try:
            text = json.dumps(settings, ensure_ascii=False, indent=4)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, SETTINGS_FILE)
        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def validate(self, settings, previous=None):
        """
        Validates settings before applying them.
        Raises SettingsValidationError on a problem; returns nothing on success.
        previous - the settings before the change (to check the offline models only
        when the user switches to offline translation - see _check_argos).
        """
        if settings["hide_overlay_enabled"] and not settings["overlay_translation_enabled"]:
            raise SettingsValidationError("overlay_hide_warning")

        api_type = settings["translation_api"]
        api_key = settings["translation_api_key"]
        if api_type in ("deepl", "microsoft") and api_key:
            self._check_translator_key(api_type, api_key, settings["target_lang"])
        elif api_type == "argos":
            # Missing models block saving only when switching to offline translation
            # just now. It is the default, so otherwise every save (e.g. a font
            # change) would be refused until the languages are downloaded - they
            # are offered for download on the first translation anyway.
            switched = previous is None or previous.get("translation_api") != "argos"
            self._check_argos(settings["ocr_lang"], settings["target_lang"], check_models=switched)

        if settings["audio_lang"]:
            self._check_audio_lang(settings["audio_lang"])

        if settings.get("hotkey_enabled"):
            self._check_hotkeys(settings.get("hotkey_combo"), settings.get("hotkey_retranslate_combo"))

    def _check_hotkeys(self, mark_combo, retranslate_combo):
        if not mark_combo:
            raise SettingsValidationError("hotkey_invalid", "")
        for combo in (mark_combo, retranslate_combo):
            if combo:
                error = combo_error(combo)
                if error:
                    raise SettingsValidationError("hotkey_invalid", f"{combo}: {error}")
        if retranslate_combo and retranslate_combo.replace(" ", "").lower() == mark_combo.replace(" ", "").lower():
            raise SettingsValidationError("hotkey_duplicate")

    def _check_translator_key(self, api_type, api_key, target_lang):
        try:
            # enable_fallback=False - otherwise an invalid key would look
            # valid, because Google would silently take over the test instead.
            translator = create_translator(api_type, api_key, enable_fallback=False)
            translator.translate("Test", target_lang)
        except NoInternetError as e:
            raise SettingsValidationError("no_internet") from e
        except Exception as e:
            raise SettingsValidationError("invalid_deepl_key", str(e)) from e

    def _check_argos(self, ocr_lang, target_lang, check_models=True):
        """Offline translation needs the libraries and downloaded models for the languages."""
        if not argos.libraries_available():
            raise SettingsValidationError("argos_not_installed")
        if not check_models:
            return
        source = argos.source_language(ocr_lang)
        target = (target_lang or "").strip().lower()[:2]
        if argos.find_route(source, target, argos.installed_pairs()) is None:
            raise SettingsValidationError("argos_models_needed", argos.pair_label((source, target)))

    def _check_audio_lang(self, audio_lang):
        try:
            edge_tts.Communicate("Test", voice=audio_lang)
        except Exception as e:
            raise SettingsValidationError("invalid_audio_lang", str(e)) from e
