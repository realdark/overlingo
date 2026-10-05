"""
Временна проверка: къде точно се затваря програмата при превод без интернет.
Пусни от папката на Overlingo в cmd (не с двоен клик):

    python argos_crash_test.py qt-first

("qt-first" зарежда PyQt5 и OpenCV ПРЕДИ ctranslate2 - както програмата.)

и прати целия изход. Всяка стъпка се отпечатва ПРЕДИ да се изпълни, така
последният ред показва къде е сривът.
"""

import faulthandler
import os
import sys
import time

faulthandler.enable(all_threads=True)


def step(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


step(f"Python {sys.version.split()[0]}, {sys.platform}")
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "argos-models", "en_bg")
TEXT = ["▁Hello", "▁world", "."]

QT_FIRST = "qt-first" in sys.argv


def import_ct2():
    global ctranslate2, sentencepiece
    step("import ctranslate2 + sentencepiece")
    import ctranslate2
    import sentencepiece
    step(f"   ctranslate2 {ctranslate2.__version__}, sentencepiece {sentencepiece.__version__}")


def import_app_libs():
    global QtCore, QtWidgets
    step("import PyQt5, cv2, numpy, pytesseract, pygame (като в програмата)")
    from PyQt5 import QtCore, QtWidgets
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import pytesseract  # noqa: F401
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame  # noqa: F401


step("1-2. редът на зареждане: " + ("PyQt5/OpenCV първо, после ctranslate2" if QT_FIRST else "ctranslate2 първо"))
if QT_FIRST:
    import_app_libs()
    import_ct2()
else:
    import_ct2()
    import_app_libs()

step(f"3. зареждане на модела от {MODEL}")
translator = ctranslate2.Translator(os.path.join(MODEL, "model"), device="cpu", inter_threads=1,
                                    intra_threads=min(4, os.cpu_count() or 1))
tokenizer = sentencepiece.SentencePieceProcessor(model_file=os.path.join(MODEL, "sentencepiece.model"))
tokens = tokenizer.encode("Hello world. This is a test.", out_type=str)
step(f"   токени: {tokens}")

step("4. превод в главната нишка")
result = translator.translate_batch([tokens], beam_size=4, replace_unknowns=True, max_decoding_length=512)
step(f"   OK: {''.join(result[0].hypotheses[0]).replace(chr(9601), ' ').strip()}")

step("5. превод в QThread (като в програмата)")
app = QtWidgets.QApplication(sys.argv)


class Worker(QtCore.QThread):
    def run(self):
        step("   QThread стартира")
        r = translator.translate_batch([tokens], beam_size=4, replace_unknowns=True, max_decoding_length=512)
        step(f"   OK: {''.join(r[0].hypotheses[0]).replace(chr(9601), ' ').strip()}")


worker = Worker()
worker.finished.connect(app.quit)
worker.start()
app.exec_()

step("6. зареждане на НОВ модел вътре в QThread (точно като в програмата)")


class Loader(QtCore.QThread):
    def run(self):
        t = ctranslate2.Translator(os.path.join(MODEL, "model"), device="cpu", inter_threads=1,
                                   intra_threads=min(4, os.cpu_count() or 1))
        step("   моделът е зареден в QThread")
        r = t.translate_batch([tokens], beam_size=4, replace_unknowns=True, max_decoding_length=512)
        step(f"   OK: {''.join(r[0].hypotheses[0]).replace(chr(9601), ' ').strip()}")


loader = Loader()
loader.finished.connect(app.quit)
loader.start()
app.exec_()
step("ВСИЧКО МИНА - сривът е другаде; прати и crash.log от папката на програмата.")
