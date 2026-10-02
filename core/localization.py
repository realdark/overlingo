"""
ЛОКАЛИЗАЦИЯ НА ПОТРЕБИТЕЛСКИЯ ИНТЕРФЕЙС (i18n)

Текстовете са САМО в assets/locales/<език>.json - единствен източник.
(До 2.x имаше и копие на всички текстове тук, в Python, което трябваше да
се поддържа ръчно в синхрон с JSON файловете.)

Ако файл липсва или е повреден, програмата не се срива: грешката отива в
app.log, а на мястото на текста се показва английският вариант или,
ако и него няма, самият ключ (напр. "settings_button_tooltip") - така
веднага се вижда кой текст липсва.
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
        """Зарежда всички .json файлове от папката locales."""
        if not os.path.isdir(LOCALES_DIR):
            logger.error(f"Липсва папката с текстове на интерфейса: {LOCALES_DIR}")
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
                logger.error(f"Грешка при зареждане на {file}: {e}", exc_info=True)

        if not self.available_languages:
            logger.error(f"Няма нито един валиден файл с текстове в {LOCALES_DIR}")

    def set_language(self, lang_code):
        """Променя текущия език. Връща False, ако такъв език не е зареден."""
        if lang_code in self.translations:
            self.current_lang = lang_code
            return True
        return False

    def tr(self, key):
        """Текстът за ключа: от текущия език, после от английския, накрая самият ключ."""
        for lang in (self.current_lang, FALLBACK_LANGUAGE):
            text = self.translations.get(lang, {}).get(key)
            if text is not None:
                return text
        return key
