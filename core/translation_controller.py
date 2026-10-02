"""
ОРКЕСТРАЦИЯ: screenshot → OCR → превод

Извадено от ui/main_window.py (_translate_selection_threaded,
_on_translation_finished). MainWindow вече не знае нищо за mss/OpenCV -
само реагира на translation_finished / translation_failed сигналите.

Има и watchdog: ако цикълът OCR+превод отнеме прекалено дълго (заседнал
мрежов request и т.н.), потребителят получава грешка вместо вечно
въртяща се икона за статус. Ако фоновата нишка все пак завърши по-късно,
резултатът се изхвърля (generation token) - за да не "изскочи" превод,
за който потребителят вече е получил съобщение за timeout.
"""

from utils.imports import QtCore, pyqtSignal
from utils.logging_setup import logger
from core.capture import capture_region_as_gray, CaptureError
from core.translations import TranslationThread

DEFAULT_TIMEOUT_MS = 25_000  # резервна стойност - реално идва от Settings ("Timeout за превод")


class TranslationController(QtCore.QObject):
    # source_text, translated_text, from_cache, used_fallback, font_size (0 = не е мерен), rect
    translation_finished = pyqtSignal(str, str, bool, bool, int, object)
    # error_key (ключ за превод в locales, напр. "screenshot_error",
    # "translation_timeout", "translation_error"), detail (технически детайл
    # или празно), source_text (разпознатият текст, ако OCR е минал)
    translation_failed = pyqtSignal(str, str, str)
    # излъчва се веднага след успешен screenshot (преди OCR+превод) - за да
    # може UI-ят да покаже overlay-я обратно веднага, вместо да чака целия
    # (потенциално продължителен) цикъл OCR+превод да завърши.
    capture_finished = pyqtSignal()

    def __init__(self, translation_cache, timeout_ms=DEFAULT_TIMEOUT_MS):
        super().__init__()
        self.cache = translation_cache
        self.translator = None
        self.ocr_lang = "eng"
        self.target_lang = "BG"
        self.timeout_ms = timeout_ms
        self._thread = None
        self._generation = 0

        self._watchdog = QtCore.QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_timeout)

    def configure(self, translator, ocr_lang, target_lang):
        """Обновява услугата за превод и езиците (извиква се при промяна на настройки)."""
        self.translator = translator
        self.ocr_lang = ocr_lang
        self.target_lang = target_lang

    def translate_region(self, rect, detect_font_size=False):
        """
        Заснема rect и го превежда асинхронно. Извикващият код (MainWindow)
        решава сам дали да скрие overlay-я преди да викне това и го връща
        обратно веднага след capture_finished - контролерът не се занимава
        с overlay видимост, само със самия превод.
        """
        try:
            gray = capture_region_as_gray(rect)
        except CaptureError as e:
            self.translation_failed.emit(str(e), "", "")
            return

        # Screenshot-ът вече е направен - overlay-ят (ако е бил скрит заради
        # застъпване с rect) вече може да се покаже обратно. Не чакаме OCR+
        # превода (може да отнеме секунди), за да не виси излишно скрит.
        self.capture_finished.emit()

        self._generation += 1
        my_generation = self._generation

        self._thread = TranslationThread(
            gray_img=gray,
            ocr_lang=self.ocr_lang,
            translator=self.translator,
            target_lang=self.target_lang,
            translation_cache=self.cache,
            detect_font_size=detect_font_size,
        )
        self._thread.finished_signal.connect(
            lambda source_text, translated_text, from_cache, used_fallback, font_size: self._on_finished(
                my_generation, source_text, translated_text, from_cache, used_fallback, font_size, rect
            )
        )
        self._thread.failed_signal.connect(
            lambda source_text, error_key, detail: self._on_failed(
                my_generation, source_text, error_key, detail
            )
        )
        self._thread.start()
        self._watchdog.start(self.timeout_ms)

    def _on_timeout(self):
        """Изтекло е максималното време за изчакване - освобождаваме UI-а."""
        logger.warning(
            f"Преводът отне повече от {self.timeout_ms / 1000:.0f}s - "
            f"прекратявам изчакването (фоновата нишка може все още да завърши по-късно)."
        )
        self._generation += 1  # обезсилва закъснял резултат от старата нишка
        self.translation_failed.emit("translation_timeout", "", "")

    def _on_failed(self, generation, source_text, error_key, detail):
        if generation != self._generation:
            return
        self._watchdog.stop()
        self.translation_failed.emit(error_key, detail, source_text)

    def _on_finished(self, generation, source_text, translated_text, from_cache, used_fallback,
                      font_size, rect):
        if generation != self._generation:
            logger.info("Резултат от превод пристигна след timeout - игнориран.")
            return

        self._watchdog.stop()
        self.translation_finished.emit(
            source_text, translated_text, from_cache, used_fallback, font_size, rect
        )
