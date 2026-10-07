"""
АВТОМАТИЧНА ПРОВЕРКА НА ГОТОВИЯ БИЛД:  overlingo --self-test

Пуска се от GitHub Actions след билда (виж .github/workflows/build.yml),
без екран (Qt "offscreen"). Проверява това, което при билд най-често се
чупи незабелязано: липсващи библиотеки в пакета, Qt, Tesseract,
разпознаване на текст, превод без интернет и построяването на главния
прозорец. Може да се пусне и ръчно - не променя нищо освен лог файла.

    overlingo --self-test [--argos-models ПАПКА] [--require-argos] [--log ФАЙЛ]

--argos-models  папка със свален модел (CI сваля един предварително, за
                да не влиза в архива на програмата)
--require-argos без модел проверката на превода е FAIL, а не SKIP

Изход: 0 - всичко е наред, 1 - поне една проверка е неуспешна.
"""

import os
import sys
import time
import traceback
from pathlib import Path


class _Report:
    def __init__(self, log_path):
        self.lines = []
        self.failed = False
        self.log_path = Path(log_path)

    def add(self, status, name, detail=""):
        line = f"{status:4} {name}" + (f": {detail}" if detail else "")
        self.lines.append(line)
        if status == "FAIL":
            self.failed = True
        if sys.stdout is not None:  # Windows билдът е без конзола - тогава само във файла
            print(line, flush=True)

    def run(self, name, check):
        """check() връща текст за лога, ("SKIP", причина) или хвърля грешка."""
        start = time.monotonic()
        try:
            result = check()
        except Exception as e:  # noqa: BLE001 - всяка грешка е резултат от проверката
            self.add("FAIL", name, f"{type(e).__name__}: {e}")
            detail = traceback.format_exc()
            self.lines.append(detail)
            if sys.stdout is not None:
                print(detail, flush=True)
            return None
        if isinstance(result, tuple) and result and result[0] == "SKIP":
            self.add("SKIP", name, result[1])
            return None
        self.add("OK", name, f"{result} ({time.monotonic() - start:.1f} s)" if result else "")
        return result

    def save(self):
        try:
            self.log_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def _arg_value(argv, name):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def run_self_test(argv):
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # конзола без UTF-8 - без UnicodeEncodeError
    from utils.config import DATA_DIR

    report = _Report(_arg_value(argv, "--log") or DATA_DIR / "selftest.log")
    models_dir = _arg_value(argv, "--argos-models")
    require_argos = "--require-argos" in argv
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    report.add("INFO", "platform", f"{sys.platform}, Python {sys.version.split()[0]}, frozen={getattr(sys, 'frozen', False)}")

    def libraries():
        import cv2
        import numpy
        import pytesseract  # noqa: F401
        import mss  # noqa: F401
        import edge_tts  # noqa: F401
        import deepl  # noqa: F401
        import requests  # noqa: F401
        import pygame  # noqa: F401
        return f"numpy {numpy.__version__}, OpenCV {cv2.__version__}"

    report.run("libraries", libraries)

    state = {}

    def qt():
        from PyQt5 import QtWidgets, QtCore
        state["app"] = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
        return f"Qt {QtCore.QT_VERSION_STR}, platform {state['app'].platformName()}"

    report.run("qt", qt)

    def tesseract():
        from core.tesseract_setup import configure_tesseract
        import pytesseract
        path = configure_tesseract()
        if path is None:
            raise RuntimeError("Tesseract не е намерен на познатите места")
        return f"{path} (версия {pytesseract.get_tesseract_version()})"

    tesseract_ok = report.run("tesseract", tesseract) is not None

    def ocr():
        if not tesseract_ok:
            return ("SKIP", "няма Tesseract")
        import cv2
        import numpy as np
        import pytesseract
        # Текстът се рисува с вградения шрифт на OpenCV, не с Qt: в режим
        # "offscreen" (без екран) Qt на Windows няма шрифтове и картинката
        # оставаше празна.
        array = np.full((180, 1100), 255, np.uint8)
        cv2.putText(array, "Hello world 2026", (30, 120), cv2.FONT_HERSHEY_DUPLEX, 2.6, 0, 5, cv2.LINE_AA)
        text = pytesseract.image_to_string(array, lang="eng").strip()
        if "hello" not in text.lower():
            raise RuntimeError(f"очаквах 'Hello world 2026', разпознато: {text!r}")
        return repr(text)

    report.run("ocr", ocr)

    def argos_libraries():
        import ctranslate2
        import sentencepiece
        return f"ctranslate2 {ctranslate2.__version__}, sentencepiece {sentencepiece.__version__}"

    report.run("argos-libraries", argos_libraries)

    def argos_translate():
        from core import argos
        pairs = sorted(argos.installed_pairs(models_dir))
        if not pairs:
            if require_argos:
                raise RuntimeError(f"няма свален модел в {models_dir or argos.MODELS_DIR}")
            return ("SKIP", "няма свален модел (--argos-models)")
        source, target = pairs[0]
        result = argos.ArgosTranslator(source, models_dir).translate("Hello world. This is a test.", target)
        if not result.strip():
            raise RuntimeError("празен превод")
        return f"{source} → {target}: {result!r}"

    # След Qt - точно така се срива на Windows при стар msvcp140.dll (виж main.py).
    report.run("argos-translate", argos_translate)

    def main_window():
        if "app" not in state:
            return ("SKIP", "няма Qt")
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        # Кратко (под 300 ms) - иначе при липсващ Tesseract би изскочил модалният
        # диалог (QTimer в MainWindow) и би блокирал проверката.
        for _ in range(3):
            state["app"].processEvents()
            time.sleep(0.03)
        window.close()
        state["app"].processEvents()
        return "построен и затворен"

    report.run("main-window", main_window)

    report.add("INFO", "result", "FAILED" if report.failed else "ALL OK")
    report.save()
    return 1 if report.failed else 0
