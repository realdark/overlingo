"""
НАМИРАНЕ И НАСТРОЙВАНЕ НА TESSERACT

Overlingo ползва само системно инсталиран Tesseract (виж коментара при
TESSERACT_PATHS в utils/config.py). Тук е търсенето му и подсказката как
да се инсталира, ако липсва - диалогът с нея е в ui/dialogs.py.
"""

from utils.imports import os, sys, pytesseract
from utils.config import TESSERACT_PATHS, find_tessdata_dir
from utils.logging_setup import logger


def configure_tesseract():
    """
    Търси Tesseract на познатите места и настройва pytesseract, TESSDATA_PREFIX
    (папката с езиците, спрямо намерената инсталация) и PATH. Връща пътя до
    намерения tesseract или None. Безопасно за повторно извикване (напр. от
    "Провери отново", след като потребителят го е инсталирал).
    """
    for tesseract_path in TESSERACT_PATHS:
        if not tesseract_path.exists():
            continue

        pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)

        tessdata_dir = find_tessdata_dir(tesseract_path)
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

        tesseract_dir = str(tesseract_path.parent)
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if tesseract_dir not in path_entries:
            os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")

        logger.info(
            f"Tesseract настроен: {tesseract_path}"
            + (f" (tessdata: {tessdata_dir})" if tessdata_dir else " (tessdata не намерена автоматично)")
        )
        return tesseract_path

    command, _url = install_hint()
    logger.warning(f"Tesseract не е намерен! Инсталирайте: {command}")
    return None


def install_hint(platform=None):
    """
    (команда за инсталиране, резервен линк или None) за текущата ОС.
    Копираема команда навсякъде - winget е вграден в Windows 10/11 и винаги
    тегли последната версия; за Windows има и линк, ако winget липсва.
    """
    platform = platform or sys.platform
    if platform == "win32":
        return "winget install --id UB-Mannheim.TesseractOCR -e", "https://github.com/UB-Mannheim/tesseract/wiki"
    if platform == "darwin":
        return "brew install tesseract", None
    return "sudo apt install tesseract-ocr", None


def terminal_hint_key(platform=None):
    """Ключ на текста "как се отваря терминал" за текущата ОС."""
    platform = platform or sys.platform
    return {"win32": "terminal_hint_windows", "darwin": "terminal_hint_mac"}.get(platform, "terminal_hint_linux")
