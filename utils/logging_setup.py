"""
LOGGING

Replaces the scattered print() calls with real Python logging:
writes both to the console (if there is one) and to an app.log file next
to settings.json. Important mainly for the compiled .exe, where the user
has no console and everything printed with print() simply disappears.
"""

import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from utils.config import DATA_DIR

LOG_FILE = DATA_DIR / "app.log"
# Crashes in C/C++ libraries (ctranslate2, OpenCV...) kill the process without
# a Python error - faulthandler records here where the crash happened.
CRASH_FILE = DATA_DIR / "crash.log"

_LOGGER_NAME = "overlingo"
_configured = False


def setup_logging(level=logging.INFO):
    """Configures and returns the shared logger. Safe to call multiple times."""
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
        # If the file cannot be written (e.g. read-only directory), continue
        # with the console handler only - logging must not break application
        # startup. But do NOT swallow it silently - otherwise the user has no
        # way of knowing why app.log is missing.
        print(f"[overlingo] Could not create log file in {LOG_FILE}: {e}")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _configured = True
    _install_crash_handlers(logger)

    if file_handler_ok:
        logger.info(f"Logging started. Log file: {LOG_FILE}")
    else:
        logger.warning("Logging started in the console only (no file - see the error above).")

    return logger


def _install_crash_handlers(logger):
    """
    An uncaught exception in a slot or QThread.run() under PyQt5 stops the whole
    program without a trace if there is no sys.excepthook - here we log it to app.log.
    """
    def log_exception(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = log_exception
    threading.excepthook = lambda args: log_exception(args.exc_type, args.exc_value, args.exc_traceback)
    try:
        # The file must stay open until the end - faulthandler writes to it on a crash.
        global _crash_stream
        _crash_stream = open(CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_crash_stream, all_threads=True)
    except Exception as e:
        logger.warning(f"Could not enable crash logging to {CRASH_FILE}: {e}")


_crash_stream = None

# Import directly: `from utils.logging_setup import logger`
logger = setup_logging()
