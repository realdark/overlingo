"""
AUTOMATIC CHECK OF THE FINISHED BUILD:  overlingo --self-test

Run by GitHub Actions after the build (see .github/workflows/build.yml),
without a screen (Qt "offscreen"). Checks what most often breaks unnoticed
in a build: libraries missing from the package, Qt, Tesseract, text
recognition, offline translation and building the main window. Can also
be run manually - changes nothing except the log file.

    overlingo --self-test [--argos-models FOLDER] [--require-argos] [--log FILE]

--argos-models  folder with a downloaded model (CI downloads one beforehand,
                so it doesn't end up in the program archive)
--require-argos without a model the translation check is FAIL, not SKIP

Exit code: 0 - all good, 1 - at least one check failed.
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
        if sys.stdout is not None:  # the Windows build has no console - then only to the file
            print(line, flush=True)

    def run(self, name, check):
        """check() returns text for the log, ("SKIP", reason) or raises an exception."""
        start = time.monotonic()
        try:
            result = check()
        except Exception as e:  # noqa: BLE001 - any exception is a result of the check
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


def _windows_tts(folder):
    """
    Windows reads through SAPI (pywin32) - it must be in the build. The runner
    has no sound card, so the text is "read" into a .wav file instead.
    """
    from core.system_tts import _SapiEngine, sapi_rate
    from win32com.client import dynamic

    engine = _SapiEngine()
    if not engine.voices:
        return ("SKIP", "SAPI works, but this machine has no voices")
    language, name, token = engine.voices[0]
    wav = Path(folder) / "selftest-tts.wav"
    stream = dynamic.Dispatch("SAPI.SpFileStream")
    stream.Open(str(wav), 3)  # SSFMCreateForWrite
    try:
        engine.voice.AudioOutputStream = stream
        engine.voice.Voice = token
        engine.voice.Rate = sapi_rate(1.0)
        engine.voice.Speak("Hello world. This is a test.", 0)  # synchronous
    finally:
        stream.Close()
    size = wav.stat().st_size
    wav.unlink()
    if size < 10_000:
        raise RuntimeError(f"the speech file is almost empty ({size} bytes)")
    voices = ", ".join(f"{n} ({l or '?'})" for l, n, _ in engine.voices[:8])
    return f"SAPI, {len(engine.voices)} voice(s): {voices}; {name} wrote {size} bytes"


def run_self_test(argv):
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # non-UTF-8 console - avoid UnicodeEncodeError
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
            raise RuntimeError("Tesseract not found in the known locations")
        return f"{path} (version {pytesseract.get_tesseract_version()})"

    tesseract_ok = report.run("tesseract", tesseract) is not None

    def ocr():
        if not tesseract_ok:
            return ("SKIP", "no Tesseract")
        import cv2
        import numpy as np
        import pytesseract
        # The text is drawn with OpenCV's built-in font, not with Qt: in
        # "offscreen" mode (no screen) Qt on Windows has no fonts and the
        # image stayed blank.
        array = np.full((180, 1100), 255, np.uint8)
        cv2.putText(array, "Hello world 2026", (30, 120), cv2.FONT_HERSHEY_DUPLEX, 2.6, 0, 5, cv2.LINE_AA)
        text = pytesseract.image_to_string(array, lang="eng").strip()
        if "hello" not in text.lower():
            raise RuntimeError(f"expected 'Hello world 2026', recognized: {text!r}")
        return repr(text)

    report.run("ocr", ocr)

    def argos_libraries():
        import ctranslate2
        import sentencepiece
        return f"ctranslate2 {ctranslate2.__version__}, sentencepiece {sentencepiece.__version__}"

    report.run("argos-libraries", argos_libraries)

    def system_tts():
        if sys.platform == "win32":
            return _windows_tts(report.log_path.parent)
        if "app" not in state:
            return ("SKIP", "no Qt")
        from PyQt5 import QtTextToSpeech  # must be in the build (offline reading)
        engines = list(QtTextToSpeech.QTextToSpeech.availableEngines())
        if not engines:
            return ("SKIP", "Qt TextToSpeech is bundled, but this machine has no speech engine")
        engine = QtTextToSpeech.QTextToSpeech()
        locales = sorted({loc.name() for loc in engine.availableLocales()})
        return f"engines {engines}, {len(locales)} locale(s): {', '.join(locales[:8])}"

    report.run("system-tts", system_tts)

    def argos_translate():
        from core import argos
        pairs = sorted(argos.installed_pairs(models_dir))
        if not pairs:
            if require_argos:
                raise RuntimeError(f"no downloaded model in {models_dir or argos.MODELS_DIR}")
            return ("SKIP", "no downloaded model (--argos-models)")
        source, target = pairs[0]
        result = argos.ArgosTranslator(source, models_dir).translate("Hello world. This is a test.", target)
        if not result.strip():
            raise RuntimeError("empty translation")
        return f"{source} → {target}: {result!r}"

    # After Qt - this is exactly how it crashes on Windows with an old msvcp140.dll (see main.py).
    report.run("argos-translate", argos_translate)

    def main_window():
        if "app" not in state:
            return ("SKIP", "no Qt")
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        # Keep it short (under 300 ms) - otherwise, with Tesseract missing, the modal
        # dialog (QTimer in MainWindow) would pop up and block the check.
        for _ in range(3):
            state["app"].processEvents()
            time.sleep(0.03)
        window.close()
        state["app"].processEvents()
        return "built and closed"

    report.run("main-window", main_window)

    report.add("INFO", "result", "FAILED" if report.failed else "ALL OK")
    report.save()
    return 1 if report.failed else 0
