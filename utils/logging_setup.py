"""
ЛОГВАНЕ

Заменя разпръснатите print() извиквания с истински Python logging:
пише едновременно в конзолата (ако има такава) и във файл app.log до
settings.json. Важно най-вече за компилирания .exe, където потребителят
няма конзола и всичко, изведено с print(), просто изчезва.
"""

import logging
from logging.handlers import RotatingFileHandler

from utils.config import BASE_DIR

LOG_FILE = BASE_DIR / "app.log"

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

    if file_handler_ok:
        logger.info(f"Логването стартира. Лог файл: {LOG_FILE}")
    else:
        logger.warning("Логването стартира само в конзолата (без файл - виж грешката по-горе).")

    return logger


# Импортирай директно: `from utils.logging_setup import logger`
logger = setup_logging()
