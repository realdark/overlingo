"""
ORCHESTRATION: screenshot → OCR → translation

Extracted from ui/main_window.py (_translate_selection_threaded,
_on_translation_finished). MainWindow no longer knows anything about mss/OpenCV -
it only reacts to the translation_finished / translation_failed signals.

There is also a watchdog: if the OCR+translation cycle takes too long (a stuck
network request, etc.), the user gets an error instead of a forever
spinning status icon. If the background thread still finishes later,
its result is discarded (generation token) - so that no translation "pops up"
after the user has already been told about the timeout.
"""

from utils.imports import QtCore, pyqtSignal
from utils.logging_setup import logger
from core.capture import capture_region_as_gray, CaptureError
from core.translations import TranslationThread


class TranslationController(QtCore.QObject):
    # source_text, translated_text, from_cache, fallback_used (""/"google"/"offline"), font_size (0 = not measured), rect
    translation_finished = pyqtSignal(str, str, bool, str, int, object)
    # error_key (translation key in locales, e.g. "screenshot_error",
    # "translation_timeout", "translation_error"), detail (technical detail
    # or empty), source_text (the recognized text, if OCR succeeded)
    translation_failed = pyqtSignal(str, str, str)
    # emitted right after a successful screenshot (before OCR+translation) - so
    # the UI can show the overlay again immediately instead of waiting for the whole
    # (potentially lengthy) OCR+translation cycle to finish.
    capture_finished = pyqtSignal()

    def __init__(self, translation_cache, timeout_ms):
        super().__init__()
        self.cache = translation_cache
        # Filled in by configure() right after creation.
        self.translator = None
        self.ocr_lang = None
        self.target_lang = None
        self.timeout_ms = timeout_ms
        self._thread = None
        self._generation = 0

        self._watchdog = QtCore.QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_timeout)

    def configure(self, translator, ocr_lang, target_lang):
        """Updates the translation service and languages (called when settings change)."""
        self.translator = translator
        self.ocr_lang = ocr_lang
        self.target_lang = target_lang

    def translate_region(self, rect, detect_font_size=False):
        """
        Captures rect and translates it asynchronously. The calling code (MainWindow)
        decides itself whether to hide the overlay before calling this and shows it
        again right after capture_finished - the controller doesn't deal with
        overlay visibility, only with the translation itself.
        """
        try:
            gray = capture_region_as_gray(rect)
        except CaptureError as e:
            self.translation_failed.emit(str(e), "", "")
            return

        # The screenshot is already taken - the overlay (if it was hidden because it
        # overlapped rect) can be shown again now. We don't wait for OCR+
        # translation (it may take seconds), so it isn't hidden needlessly.
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
            lambda source_text, translated_text, from_cache, fallback_used, font_size: self._on_finished(
                my_generation, source_text, translated_text, from_cache, fallback_used, font_size, rect
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
        """The maximum wait time has elapsed - release the UI."""
        logger.warning(
            f"Translation took longer than {self.timeout_ms / 1000:.0f}s - "
            f"giving up waiting (the background thread may still finish later)."
        )
        self._generation += 1  # invalidates a late result from the old thread
        self.translation_failed.emit("translation_timeout", "", "")

    def _on_failed(self, generation, source_text, error_key, detail):
        if generation != self._generation:
            return
        self._watchdog.stop()
        self.translation_failed.emit(error_key, detail, source_text)

    def _on_finished(self, generation, source_text, translated_text, from_cache, fallback_used,
                      font_size, rect):
        if generation != self._generation:
            logger.info("Translation result arrived after timeout - ignored.")
            return

        self._watchdog.stop()
        self.translation_finished.emit(
            source_text, translated_text, from_cache, fallback_used, font_size, rect
        )
