"""
TEXT TRANSLATION WINDOW

Text is typed or pasted at the top, the translation appears below. With the
"Auto translate" checkbox it translates on its own about a second after you stop typing
(not on every keystroke - otherwise every letter is a separate request); without it - only
via the button / Ctrl+Enter. The checkbox matters for paid services (DeepL,
Microsoft) that count characters: every pause resends the whole text. Uses the same
translator, target language and cache as screen translation.

Non-modal; closing it only hides it - the text is still there if you
open it again. Size and position are saved in the settings.
"""

from utils.imports import QtWidgets, QtCore, QtGui
from core.translations import TextTranslationThread, fallback_notice_key
from ui.components import AudioButton, CopyButton

AUTO_TRANSLATE_DELAY_MS = 1000


class TextTranslateWindow(QtWidgets.QDialog):
    """
    get_translator:     callback() -> the current translator (may be None)
    get_target_lang:    callback() -> target language from the settings
    cache:              core.translations.TranslationCache (shared with screen translation)
    get_audio_settings: callback() -> (voice, rate)
    on_translated:      callback(source, translation, from_cache) - for history and statistics
    on_geometry:        callback([x, y, w, h]) - on hide, so it gets saved
    on_auto_changed:    callback(bool) - the "Auto translate" checkbox, so it gets saved
    """

    def __init__(self, parent, i18n, get_translator, get_target_lang, cache,
                 get_audio_settings, on_translated, on_geometry, geometry=None,
                 auto_translate=True, on_auto_changed=None):
        super().__init__(parent, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        self.i18n = i18n
        self._get_translator = get_translator
        self._get_target_lang = get_target_lang
        self._cache = cache
        self._on_translated = on_translated
        self._on_geometry = on_geometry

        self._request_id = 0
        self._threads = set()  # keep references while the threads are running

        self.setMinimumSize(420, 380)
        self.resize(560, 460)
        if geometry and len(geometry) == 4:
            self._restore_geometry(geometry)

        layout = QtWidgets.QVBoxLayout(self)

        self.input_label = QtWidgets.QLabel()
        layout.addWidget(self.input_label)
        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.input_edit, stretch=1)

        row = QtWidgets.QHBoxLayout()
        self.translate_btn = QtWidgets.QPushButton()
        self.translate_btn.clicked.connect(self.translate_now)
        self.auto_checkbox = QtWidgets.QCheckBox()
        self.auto_checkbox.setChecked(auto_translate)
        self.auto_checkbox.toggled.connect(self._on_auto_toggled)
        self._on_auto_changed = on_auto_changed
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        row.addWidget(self.translate_btn)
        row.addWidget(self.auto_checkbox)
        row.addWidget(self.status_label, stretch=1)
        layout.addLayout(row)

        self.output_label = QtWidgets.QLabel()
        layout.addWidget(self.output_label)
        self.output_edit = QtWidgets.QPlainTextEdit()
        self.output_edit.setReadOnly(True)  # read-only, but can still be selected and copied
        layout.addWidget(self.output_edit, stretch=1)

        buttons = QtWidgets.QHBoxLayout()
        self.copy_btn = CopyButton(i18n, self.output_edit.toPlainText)
        self.audio_btn = AudioButton(i18n, self.output_edit.toPlainText, get_audio_settings)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.audio_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(AUTO_TRANSLATE_DELAY_MS)
        self._debounce.timeout.connect(self.translate_now)

        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(keys), self)
            shortcut.activated.connect(self.translate_now)

        self.update_texts()
        self._update_output_buttons()

    def update_texts(self):
        """UI texts (also called when the language changes)."""
        self.setWindowTitle(self.i18n.tr("text_window_title"))
        self.input_label.setText(self.i18n.tr("text_input_label"))
        self.input_edit.setPlaceholderText(self.i18n.tr("text_input_placeholder"))
        self.translate_btn.setText(self.i18n.tr("translate_now_button"))
        self.auto_checkbox.setText(self.i18n.tr("text_auto_translate_label"))
        self.auto_checkbox.setToolTip(self.i18n.tr("text_auto_translate_tooltip"))
        self.output_label.setText(self.i18n.tr("text_output_label"))
        self.copy_btn.update_text()
        self.audio_btn.update_text()

    def bring_up(self):
        """Shows the window (or raises it to the top if it is already open)."""
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_edit.setFocus()

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def _on_text_changed(self):
        if self.auto_checkbox.isChecked():
            self._debounce.start()  # restarts the countdown on every keystroke

    def set_auto_translate(self, enabled):
        """From outside (e.g. "Restore defaults"), without triggering a translation."""
        self.auto_checkbox.blockSignals(True)
        self.auto_checkbox.setChecked(enabled)
        self.auto_checkbox.blockSignals(False)
        if not enabled:
            self._debounce.stop()

    def _on_auto_toggled(self, enabled):
        if enabled:
            self._debounce.start()  # in case there is already untranslated text
        else:
            self._debounce.stop()
        if self._on_auto_changed:
            self._on_auto_changed(enabled)

    def translate_now(self):
        self._debounce.stop()
        text = self.input_edit.toPlainText().strip()
        self._request_id += 1  # older requests still in flight will be ignored
        if not text:
            self.output_edit.clear()
            self.status_label.clear()
            self._update_output_buttons()
            return

        self.status_label.setText(self.i18n.tr("translating_status"))
        self.status_label.setToolTip("")
        thread = TextTranslationThread(
            self._request_id, text, self._get_translator(), self._get_target_lang(), self._cache
        )
        thread.finished_signal.connect(self._on_finished)
        thread.failed_signal.connect(self._on_failed)
        thread.finished.connect(lambda t=thread: self._threads.discard(t))
        self._threads.add(thread)
        thread.start()

    def _on_finished(self, request_id, source, translation, from_cache, fallback_used):
        if request_id != self._request_id:
            return  # the text changed while we were waiting - this result is stale
        self.output_edit.setPlainText(translation)
        self.status_label.setText(f"⚠ {self.i18n.tr(fallback_notice_key(fallback_used))}" if fallback_used else "")
        self._update_output_buttons()
        self._on_translated(source, translation, from_cache)

    def _on_failed(self, request_id, error_key, detail):
        if request_id != self._request_id:
            return
        message = f"❌ {self.i18n.tr(error_key)}"
        if error_key == "argos_model_missing" and detail:
            # The text ends with "...for" - without the pair ("en → bg") it is incomplete.
            message = f"{message} {detail}"
        self.status_label.setText(message)
        self.status_label.setToolTip(detail)

    def _update_output_buttons(self):
        has_output = bool(self.output_edit.toPlainText())
        self.copy_btn.setEnabled(has_output)
        self.audio_btn.setEnabled(has_output)

    # ------------------------------------------------------------------
    # Size and position
    # ------------------------------------------------------------------

    def _restore_geometry(self, geometry):
        x, y, w, h = geometry
        # If the screen setup changed (e.g. a second monitor was unplugged), don't open
        # the window outside the visible area - let Qt position it.
        screen = QtWidgets.QApplication.screenAt(QtCore.QPoint(x + 40, y + 20))
        self.resize(w, h)
        if screen is not None:
            self.move(x, y)

    def hideEvent(self, event):
        # hideEvent, not closeEvent - Escape closes the dialog without a closeEvent.
        self.audio_btn.stop()
        # The position is the frame's (move() also moves the frame), the size is
        # the content's (resize() is also for the content). Otherwise the window
        # drifts down by the title bar height on every open.
        pos, size = self.frameGeometry().topLeft(), self.size()
        self._on_geometry([pos.x(), pos.y(), size.width(), size.height()])
        super().hideEvent(event)

    def wait_for_threads(self, timeout_ms=2000):
        """Called on app exit - so a thread isn't destroyed while it is running."""
        for thread in list(self._threads):
            thread.wait(timeout_ms)
