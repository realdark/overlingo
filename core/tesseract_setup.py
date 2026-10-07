"""
FINDING AND CONFIGURING TESSERACT

Overlingo only uses a system-installed Tesseract (see the comment at
TESSERACT_PATHS in utils/config.py). This module finds it and provides the
hint on how to install it if missing - the dialog showing it is in ui/dialogs.py.
"""

from utils.imports import os, sys, pytesseract
from utils.config import TESSERACT_PATHS, find_tessdata_dir
from utils.logging_setup import logger


def configure_tesseract():
    """
    Looks for Tesseract in the known locations and configures pytesseract,
    TESSDATA_PREFIX (the language folder, relative to the found installation)
    and PATH. Returns the path to the found tesseract or None. Safe to call
    repeatedly (e.g. from "Check again", after the user has installed it).
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
            f"Tesseract configured: {tesseract_path}"
            + (f" (tessdata: {tessdata_dir})" if tessdata_dir else " (tessdata not found automatically)")
        )
        return tesseract_path

    command, _url = install_hint()
    logger.warning(f"Tesseract not found! Install it with: {command}")
    return None


def install_hint(platform=None):
    """
    (install command, fallback link or None) for the current OS.
    A copyable command everywhere - winget is built into Windows 10/11 and always
    fetches the latest version; Windows also gets a link in case winget is missing.
    """
    platform = platform or sys.platform
    if platform == "win32":
        return "winget install --id UB-Mannheim.TesseractOCR -e", "https://github.com/UB-Mannheim/tesseract/wiki"
    if platform == "darwin":
        return "brew install tesseract", None
    return "sudo apt install tesseract-ocr", None


def terminal_hint_key(platform=None):
    """Key of the "how to open a terminal" text for the current OS."""
    platform = platform or sys.platform
    return {"win32": "terminal_hint_windows", "darwin": "terminal_hint_mac"}.get(platform, "terminal_hint_linux")
