"""
УПРАВЛЕНИЕ НА НАСТРОЙКИТЕ (зареждане / запазване / валидация)

Извадено от ui/main_window.py. Не зависи от Qt widgets - работи само
с обикновени dict-ове, за да може лесно да се тества и преизползва.
"""

from utils.imports import json, os, edge_tts
from utils.config import SETTINGS_FILE, DEFAULT_SETTINGS, OBSOLETE_SETTINGS
from utils.logging_setup import logger
from core.translations import create_translator, OllamaTranslator, NoInternetError
from core.hotkey_manager import combo_error

# Остават непроменени при "Възстанови настройките по подразбиране":
# ключът за платена услуга е досадно да се въвежда пак, а позициите на
# прозорците не са "настройка", която потребителят е избрал съзнателно.
KEPT_ON_RESET = ("translation_api_key", "window_pos", "text_window_geometry")


class SettingsValidationError(Exception):
    """Хвърля се при невалидни настройки. `message_key` е ключ за превод на UI съобщението."""

    def __init__(self, message_key, detail=""):
        self.message_key = message_key
        self.detail = detail
        super().__init__(message_key)


class SettingsManager:
    """Зарежда, валидира и записва настройките на приложението в SETTINGS_FILE."""

    def load(self):
        """Зарежда настройки от файл, допълнени с DEFAULT_SETTINGS за липсващи полета."""
        settings = dict(DEFAULT_SETTINGS)
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings.update(json.load(f))
        except Exception as e:
            logger.error(f"Грешка при зареждане на настройки: {e}", exc_info=True)
        for key in OBSOLETE_SETTINGS:
            settings.pop(key, None)
        return settings

    def defaults_for_reset(self, current):
        """Настройките по подразбиране, като запазва KEPT_ON_RESET от current."""
        settings = dict(DEFAULT_SETTINGS)
        for key in KEPT_ON_RESET:
            if key in current:
                settings[key] = current[key]
        return settings

    def save(self, settings):
        """
        Записва настройките във файл. Първо целият текст, после временен
        файл, който заменя стария наведнъж - ако нещо се провали по средата
        (стойност, която не може да се запише, срив, спиране на тока),
        старият settings.json остава непокътнат, вместо наполовина записан
        (което при следващо стартиране би изтрило всички настройки).
        """
        tmp_path = f"{SETTINGS_FILE}.tmp"
        try:
            text = json.dumps(settings, ensure_ascii=False, indent=4)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, SETTINGS_FILE)
        except Exception as e:
            logger.error(f"Грешка при запазване на настройките: {e}", exc_info=True)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def validate(self, settings):
        """
        Валидира настройки преди прилагане.
        Хвърля SettingsValidationError при проблем; не връща нищо при успех.
        """
        if settings["hide_overlay_enabled"] and not settings["overlay_translation_enabled"]:
            raise SettingsValidationError("overlay_hide_warning")

        api_type = settings["translation_api"]
        api_key = settings["translation_api_key"]
        if api_type in ("deepl", "microsoft") and api_key:
            self._check_translator_key(api_type, api_key, settings["target_lang"])
        elif api_type == "ollama":
            self._check_ollama(settings.get("ollama_model"), settings.get("ollama_url"), settings["target_lang"])

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
            # enable_fallback=False - иначе невалиден ключ би изглеждал
            # валиден, защото Google тихо би поел теста вместо него.
            translator = create_translator(api_type, api_key, enable_fallback=False)
            translator.translate("Test", target_lang)
        except NoInternetError as e:
            raise SettingsValidationError("no_internet") from e
        except Exception as e:
            raise SettingsValidationError("invalid_deepl_key", str(e)) from e

    def _check_ollama(self, model, base_url, target_lang):
        try:
            translator = OllamaTranslator(model=model, base_url=base_url)
            translator.translate("Test", target_lang)
        except Exception as e:
            raise SettingsValidationError("invalid_ollama_config", str(e)) from e

    def _check_audio_lang(self, audio_lang):
        try:
            edge_tts.Communicate("Test", voice=audio_lang)
        except Exception as e:
            raise SettingsValidationError("invalid_audio_lang", str(e)) from e
