"""
PROJECT CONFIGURATION
"""

from utils.imports import Path, sys, os

def get_base_dir():
    """Returns the correct base directory for compiled and non-compiled versions"""
    if getattr(sys, 'frozen', False):
        # Compiled version - use the exe file's folder
        return Path(sys.executable).parent
    else:
        # Non-compiled version - use the normal path
        return Path(__file__).resolve().parent.parent

def get_resource_dir():
    """
    The folder containing "assets". Usually next to the program (build.sh/build.bat
    copy it there). In the macOS .app bundle it is inside the bundle (PyInstaller
    puts it there with --add-data) - found via sys._MEIPASS.
    """
    base = get_base_dir()
    if (base / "assets").is_dir():
        return base
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled and (Path(bundled) / "assets").is_dir():
        return Path(bundled)
    return base


def get_data_dir():
    """
    Where settings, logs and offline translation models are written.
    Next to the program (as it has always been on Windows/Linux - everything in one folder).
    Exception: the compiled macOS version - the .app bundle must not be
    modified (it is often in /Applications without write permission, and its
    signature breaks), so there it is ~/Library/Application Support/Overlingo.
    """
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        data = Path.home() / "Library" / "Application Support" / "Overlingo"
        try:
            data.mkdir(parents=True, exist_ok=True)
            return data
        except OSError:
            pass
    return get_base_dir()


# Dynamic paths
BASE_DIR = get_base_dir()
RESOURCE_DIR = get_resource_dir()
DATA_DIR = get_data_dir()
SETTINGS_FILE = DATA_DIR / "settings.json"
LOCALES_DIR = RESOURCE_DIR / "assets" / "locales"
THEME_FILE = RESOURCE_DIR / "assets" / "theme.qss"
ICON_DIR = RESOURCE_DIR / "assets" / "icons"
IMAGES_DIR = RESOURCE_DIR / "assets" / "images"


def image_path(filename):
    """
    Absolute path to an image from assets/images, as str (for QIcon/QPixmap).

    We don't use relative paths ("assets/images/...") - they depend on the
    current working directory. From a terminal in the program folder it works,
    but when launched from the applications menu/a shortcut the working
    directory is different (usually $HOME) and the button icons disappear.
    """
    return str(IMAGES_DIR / filename)

# Icons for different operating systems ✅
APP_ICON_WINDOWS = ICON_DIR / "app_icon.ico"    # .ico for Windows
APP_ICON_MAC = ICON_DIR / "app_icon.icns"       # .icns for macOS  
APP_ICON_LINUX = ICON_DIR / "app_icon.png"      # .png for Linux

# ✅ AUTOMATIC TESSERACT PATHS FOR ALL OS
#
# System installation only, deliberately, on all three platforms - no bundled
# "Local" copy anywhere. Reasons:
# - macOS never had a bundled option (it requires dylibbundler on a real
#   Mac machine to make a portable bundle).
# - Linux AppImage bundling was dropped - the AppImage hard-codes its own
#   TESSDATA_PREFIX at build time, so the "Download language" button
#   cannot add new languages to it (confirmed by the AppImageBuilder.yml
#   of the actual AppImage build).
# - A Windows bundled copy is now an unnecessary complication given a
#   system installation, which is available and easier to maintain everywhere.
#
# If Tesseract is missing from the system, we show a clear dialog with
# instructions (see ui/dialogs.py, show_tesseract_missing) - "install it
# yourself" is a deliberate, consistent policy on all three platforms.
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
    Derives the tessdata folder RELATIVE to the found tesseract binary - instead
    of guessing separate absolute system paths (fragile - must be maintained
    by hand for every new version/distribution), we follow the ACTUAL
    installation. Checks the known relative locations:
      - next to the binary itself (Windows UB Mannheim)
      - ../share/tessdata (Homebrew: bin/tesseract -> share/tessdata)
      - ../share/tesseract-ocr/<version>/tessdata (Linux system packages -
        the version varies by distribution/year, hence a glob, not a fixed number)
    Returns a Path, or None if nothing matches.
    """
    binary_dir = tesseract_binary_path.parent

    candidates = [
        binary_dir / "tessdata",
        binary_dir.parent / "share" / "tessdata",
    ]

    share_root = binary_dir.parent / "share" / "tesseract-ocr"
    if share_root.exists():
        # reverse=True - newer versions usually sort later
        # ("5" after "4.00"), so we try them first.
        candidates.extend(sorted(share_root.glob("*/tessdata"), reverse=True))

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def get_tessdata_dir():
    """
    The system Tesseract's language folder (TESSDATA_PREFIX, which
    configure_tesseract() in core/tesseract_setup.py sets based on the found installation), or None if
    not found. New languages from "Download language" are also saved there.

    System paths (/usr/share/tesseract-ocr/...) usually require root
    permissions to write - then "Download language" shows an error with an explanation.
    """
    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix and Path(env_prefix).is_dir():
        return Path(env_prefix)
    return None


def get_available_ocr_languages():
    """
    The available OCR languages - the names of the .traineddata files in the
    tessdata folder (without the extension, e.g. "eng", "bul"). "osd" is excluded -
    it is not a language but a helper file for detecting page orientation.
    """
    folder = get_tessdata_dir()
    if folder:
        langs = sorted(p.stem for p in folder.glob("*.traineddata") if p.stem.lower() != "osd")
        if langs:
            return langs
    return ["eng"]  # sensible default if the tessdata folder is not found


# Default settings
DEFAULT_SETTINGS = {
    "text_size": 14, 
    "font_color": "#FFFFFF", 
    "window_pos": None, 
    "translation_api": "argos",  # offline on this computer; languages are downloaded on first use
    "translation_api_key": "",
    "ocr_lang": "eng",
    "target_lang": "",
    "overlay_translation_enabled": True,
    "preserve_font_size": True,
    "auto_refresh_enabled": False,
    "overlay_opacity": 200,
    "audio_lang": "",
    "audio_speed": 1.0,
    "tts_engine": "system",  # "system" - the computer's voices (offline) / "edge" - Microsoft Edge (online)
    "interface_language": "en",
    "auto_refresh_interval": 5000,
    "hide_overlay_enabled": True,
    "hotkey_enabled": False,
    "hotkey_combo": "<ctrl>+<alt>+t",
    "hotkey_retranslate_combo": "<ctrl>+<alt>+r",
    "translation_timeout": 25,  # seconds
    "text_window_geometry": None,  # [x, y, width, height] of the text translation window
    "text_auto_translate": True,  # the "Auto translate" checkbox in the text translation window
}

# Settings from old versions that are no longer used. They are removed on
# load so they don't stay in settings.json forever.
OBSOLETE_SETTINGS = (
    "mark_translate_enabled",  # up to 2.x: separate "Mark" and "Translate" buttons
    "ollama_model",  # up to 3.1: Ollama, replaced by offline translation (Argos)
    "ollama_url",
)