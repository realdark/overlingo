"""
КОНФИГУРАЦИЯ НА ПРОЕКТА
"""

from utils.imports import Path, sys, os

def get_base_dir():
    """Връща правилната базова директория за компилирани и некомпилирани версии"""
    if getattr(sys, 'frozen', False):
        # Компилирана версия - използваме папката на exe файла
        return Path(sys.executable).parent
    else:
        # Некомпилирана версия - използваме нормалния път
        return Path(__file__).resolve().parent.parent

# Динамични пътища
BASE_DIR = get_base_dir()
SETTINGS_FILE = BASE_DIR / "settings.json"
LOCALES_DIR = BASE_DIR / "assets" / "locales"
THEME_FILE = BASE_DIR / "assets" / "theme.qss"
ICON_DIR = BASE_DIR / "assets" / "icons"
IMAGES_DIR = BASE_DIR / "assets" / "images"


def image_path(filename):
    """
    Абсолютен път до картинка от assets/images, като str (за QIcon/QPixmap).

    Не ползваме относителни пътища ("assets/images/...") - те зависят от
    текущата работна папка. От терминал в папката на програмата работи,
    но при стартиране от менюто с приложения/пряк път работната папка е
    друга (обикновено $HOME) и иконите на бутоните изчезват.
    """
    return str(IMAGES_DIR / filename)

# Икони за различни операционни системи ✅
APP_ICON_WINDOWS = ICON_DIR / "app_icon.ico"    # .ico за Windows
APP_ICON_MAC = ICON_DIR / "app_icon.icns"       # .icns за macOS  
APP_ICON_LINUX = ICON_DIR / "app_icon.png"      # .png за Linux

# ✅ AUTOMATIC TESSERACT PATHS FOR ALL OS
#
# Само системна инсталация, съзнателно, на трите платформи - без bundled
# "Local" копие никъде. Причини:
# - macOS никога не е имал bundled опция (изисква dylibbundler на реална
#   Mac машина, за да стане преносим bundle).
# - Linux AppImage bundling се отказа - AppImage-ът твърдо задава
#   собствения си TESSDATA_PREFIX при build-ване, така че бутонът
#   "Свали език" не може да добавя нови езици към него (потвърдено от
#   AppImageBuilder.yml на конкретния AppImage build).
# - Windows bundled копие вече е излишно усложнение при систематична
#   инсталация, която е налична и по-удобна за поддръжка навсякъде.
#
# Ако Tesseract липсва системно, показваме ясен диалог с инструкции
# (виж ui/dialogs.py, show_tesseract_missing) - "инсталирай сам"
# е съзнателна, консистентна политика на трите платформи.
if sys.platform == "win32":
    TESSERACT_PATHS = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),  # System
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),  # 32-bit
    ]
elif sys.platform == "darwin":
    TESSERACT_PATHS = [
        Path("/usr/local/bin/tesseract"),  # Homebrew
        Path("/opt/homebrew/bin/tesseract"),  # Apple Silicon Homebrew
        Path("/usr/bin/tesseract")  # System
    ]
else:
    TESSERACT_PATHS = [
        Path("/usr/bin/tesseract"),  # System
        Path("/usr/local/bin/tesseract"),  # Custom install
        Path("/snap/bin/tesseract"),  # Snap package
    ]

def find_tessdata_dir(tesseract_binary_path):
    """
    Извлича tessdata папката СПРЯМО намерения tesseract binary - вместо да
    се гадаят отделни абсолютни системни пътища (крехко - трябва да се
    поддържа ръчно при всяка нова версия/дистрибуция), следваме РЕАЛНАТА
    инсталация. Проверява познатите относителни разположения:
      - до самия binary (Windows UB Mannheim)
      - ../share/tessdata (Homebrew: bin/tesseract -> share/tessdata)
      - ../share/tesseract-ocr/<версия>/tessdata (Linux система пакети -
        версията варира по дистрибуция/година, затова glob, не твърдо число)
    Връща Path, или None ако нищо не съвпадне.
    """
    binary_dir = tesseract_binary_path.parent

    candidates = [
        binary_dir / "tessdata",
        binary_dir.parent / "share" / "tessdata",
    ]

    share_root = binary_dir.parent / "share" / "tesseract-ocr"
    if share_root.exists():
        # reverse=True - по-новите версии обикновено сортират по-накрая
        # ("5" след "4.00"), пробваме тях първо.
        candidates.extend(sorted(share_root.glob("*/tessdata"), reverse=True))

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def get_tessdata_dir():
    """
    Папката с езиците на системния Tesseract (TESSDATA_PREFIX, който
    configure_tesseract() в core/tesseract_setup.py задава спрямо намерената инсталация), или None, ако
    не е открита. Там се записват и новите езици от "Свали език".

    Системните пътища (/usr/share/tesseract-ocr/...) обикновено изискват
    root права за писане - тогава "Свали език" показва грешка с обяснение.
    """
    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix and Path(env_prefix).is_dir():
        return Path(env_prefix)
    return None


def get_available_ocr_languages():
    """
    Наличните OCR езици - имената на .traineddata файловете в tessdata
    папката (без разширението, напр. "eng", "bul"). "osd" се изключва - не
    е език, а помощен файл за откриване на ориентация на страницата.
    """
    folder = get_tessdata_dir()
    if folder:
        langs = sorted(p.stem for p in folder.glob("*.traineddata") if p.stem.lower() != "osd")
        if langs:
            return langs
    return ["eng"]  # разумна стойност, ако tessdata папката не е намерена


# Настройки по подразбиране
DEFAULT_SETTINGS = {
    "text_size": 14, 
    "font_color": "#FFFFFF", 
    "window_pos": None, 
    "translation_api": "google",
    "translation_api_key": "",
    "ocr_lang": "eng",
    "target_lang": "",
    "overlay_translation_enabled": True,
    "preserve_font_size": True,
    "auto_refresh_enabled": False,
    "overlay_opacity": 200,
    "audio_lang": "",
    "audio_speed": 1.0,
    "interface_language": "en",
    "auto_refresh_interval": 5000,
    "hide_overlay_enabled": True,
    "hotkey_enabled": False,
    "hotkey_combo": "<ctrl>+<alt>+t",
    "hotkey_retranslate_combo": "<ctrl>+<alt>+r",
    "translation_timeout": 25,  # секунди
    "text_window_geometry": None,  # [x, y, ширина, височина] на прозореца за превод на текст
    "text_auto_translate": True,  # отметката "Автоматичен превод" в прозореца за превод на текст
}

# Настройки от стари версии, които вече не се ползват. Махат се при
# зареждане, за да не остават завинаги в settings.json.
OBSOLETE_SETTINGS = (
    "mark_translate_enabled",  # до 2.x: отделни бутони "Маркиране" и "Превод"
    "ollama_model",  # до 3.1: Ollama, заменена от превода без интернет (Argos)
    "ollama_url",
)