"""
ЛОГВАНЕ

Заменя разпръснатите print() извиквания с истински Python logging:
пише едновременно в конзолата (ако има такава) и във файл app.log до
settings.json. Важно най-вече за компилирания .exe, където потребителят
няма конзола и всичко, изведено с print(), просто изчезва.
"""

import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from utils.config import BASE_DIR

LOG_FILE = BASE_DIR / "app.log"
# Сривове в C/C++ библиотеките (ctranslate2, OpenCV...) убиват процеса без
# Python грешка - faulthandler записва тук къде е станал сривът.
CRASH_FILE = BASE_DIR / "crash.log"

_LOGGER_NAME = "overlingo"
_configured = False


def setup_logging(level=logging.INFO):
    """Конфигурира и връща споделения logger. Безопасно за многократно извикване."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)

    if _configured:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(module)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler_ok = False
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        file_handler_ok = True
    except Exception as e:
        # Ако не може да пише във файла (напр. read-only директория),
        # продължаваме само с конзолния handler - логването не бива
        # да чупи стартирането на приложението. Но НЕ го гълтаме тихо -
        # иначе няма как потребителят да разбере защо липсва app.log.
        print(f"[overlingo] Не успях да създам лог файл в {LOG_FILE}: {e}")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _configured = True
    _install_crash_handlers(logger)

    if file_handler_ok:
        logger.info(f"Логването стартира. Лог файл: {LOG_FILE}")
    else:
        logger.warning("Логването стартира само в конзолата (без файл - виж грешката по-горе).")

    return logger


def _install_crash_handlers(logger):
    """
    Неприхваната грешка в слот или QThread.run() при PyQt5 спира цялата
    програма без следа, ако няма sys.excepthook - тук я записваме в app.log.
    """
    def log_exception(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Неприхваната грешка", exc_info=(exc_type, exc, tb))

    sys.excepthook = log_exception
    threading.excepthook = lambda args: log_exception(args.exc_type, args.exc_value, args.exc_traceback)
    try:
        # Файлът трябва да остане отворен до края - faulthandler пише в него при срив.
        global _crash_stream
        _crash_stream = open(CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_crash_stream, all_threads=True)
    except Exception as e:
        logger.warning(f"Не успях да включа записа на сривове в {CRASH_FILE}: {e}")


_crash_stream = None

# Импортирай директно: `from utils.logging_setup import logger`
logger = setup_logging()
