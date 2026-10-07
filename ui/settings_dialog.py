"""
SETTINGS DIALOG

The form fields are defined declaratively in _field_specs(), and
values are read by NAME (widgets dict), not by position.
"""

from utils.imports import QtWidgets, QtCore
from utils.config import get_available_ocr_languages, get_tessdata_dir
from core.settings_manager import SettingsValidationError
from core.argos_download import ArgosDownloadThread
from core import argos
from core.tessdata_download import TessdataDownloadThread
from core.audio_handler import EdgeVoicesThread
from core.hotkey_manager import HOTKEY_SUPPORTED
from utils.logging_setup import logger

TEXT_COLOR_CHOICES = {
    "Бял": "#FFFFFF",
    "Жълт": "#FFFF00",
    "Зелен": "#00FF00",
    "Червен": "#FF0000",
}


class SettingsDialog(QtWidgets.QDialog):
    """
    settings_manager: core.settings_manager.SettingsManager
    i18n:             core.localization.UiLocalizer (for texts)
    current_settings: dict with the values the form starts from
    on_opacity_preview: callback(value:int), called while the slider is moving
                        (so the change is visible on the overlay immediately)
    on_save:          callback(settings:dict), called only after successful validation
    """

    def __init__(self, parent, settings_manager, i18n, current_settings,
                 on_opacity_preview=None, on_save=None):
        super().__init__(parent, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        self.settings_manager = settings_manager
        self.i18n = i18n
        self.current = current_settings
        self.on_opacity_preview = on_opacity_preview
        self.on_save = on_save
        self.widgets = {}

        self.setWindowTitle(self.i18n.tr("settings_title"))
        self.setMinimumWidth(520)
        self._build_ui()
        # No explicit centering on the screen - by default Qt
        # positions the dialog relative to its parent (the small toolbar), just like
        # the About/Help/Tesseract dialogs. If the dialog ends up outside
        # the visible screen area for certain toolbar positions,
        # that is the trade-off for consistency with the other windows.

    # ------------------------------------------------------------------
    # Building the form
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        self._argos_thread = None

        # Fields are grouped by tab (see the "tab" key in _field_specs) -
        # each tab gets its own grid, so we don't end up with
        # one endless scrolling list of ~20 rows at once.
        tabs = QtWidgets.QTabWidget()
        tab_order = [
            ("interface", "settings_tab_interface"),
            ("translation", "settings_tab_translation"),
            ("audio", "settings_tab_audio"),
            ("hotkey", "settings_tab_hotkey"),
        ]
        specs_by_tab = {}
        for spec in self._field_specs():
            specs_by_tab.setdefault(spec["tab"], []).append(spec)

        for tab_key, tab_label_key in tab_order:
            tab_specs = specs_by_tab.get(tab_key)
            if not tab_specs:
                continue  # e.g. "hotkey" is absent where global hotkeys aren't supported

            tab_page = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab_page)
            row = 0

            for spec in tab_specs:
                widget = spec["make"]()
                widget.setObjectName(spec["name"])
                self.widgets[spec["name"]] = widget
                grid.addWidget(QtWidgets.QLabel(self.i18n.tr(spec["label_key"])), row, 0)
                grid.addWidget(widget, row, 1)
                row += 1

                if spec["name"] == "ocr_combo":
                    # Row for downloading a new OCR language - straight from the official
                    # tesseract-ocr GitHub repository (tessdata_fast), without
                    # the user going to a browser. Separate from the declarative
                    # schema above because it starts a background streaming task.
                    self._tessdata_thread = None
                    lang_row = QtWidgets.QHBoxLayout()
                    self.tessdata_lang_edit = QtWidgets.QLineEdit()
                    self.tessdata_lang_edit.setPlaceholderText(self.i18n.tr("tessdata_lang_placeholder"))
                    self.tessdata_download_btn = QtWidgets.QPushButton(self.i18n.tr("download_tessdata_button"))
                    self.tessdata_download_btn.clicked.connect(self._handle_download_tessdata)
                    lang_row.addWidget(self.tessdata_lang_edit)
                    lang_row.addWidget(self.tessdata_download_btn)
                    grid.addLayout(lang_row, row, 1)
                    row += 1

                    self.tessdata_download_status = QtWidgets.QLabel("")
                    grid.addWidget(self.tessdata_download_status, row, 1)
                    row += 1

                    tessdata_link = QtWidgets.QLabel(
                        f'<a href="https://github.com/tesseract-ocr/tessdata_fast" '
                        f'style="color:#60a5fa;">{self.i18n.tr("tessdata_list_link_text")}</a>'
                    )
                    tessdata_link.setOpenExternalLinks(True)
                    grid.addWidget(tessdata_link, row, 1)
                    row += 1

                if spec["name"] == "target_edit":
                    # Offline translation (Argos): models are per language pair
                    # (source language -> target language) and are downloaded here. They also
                    # serve as a fallback for the online services when there is no internet.
                    self.argos_download_btn = QtWidgets.QPushButton(self.i18n.tr("argos_download_button"))
                    self.argos_download_btn.clicked.connect(self._handle_download_argos)
                    self.argos_download_btn.setToolTip(self.i18n.tr("argos_download_tooltip"))
                    self.argos_download_status = QtWidgets.QLabel("")
                    if ArgosDownloadThread.is_busy():
                        self.argos_download_btn.setEnabled(False)
                        self.argos_download_status.setText(self.i18n.tr("argos_downloading"))
                    argos_row = QtWidgets.QHBoxLayout()
                    argos_row.addWidget(self.argos_download_btn)
                    argos_row.addWidget(self.argos_download_status, stretch=1)
                    grid.addLayout(argos_row, row, 1)
                    row += 1

                    self.argos_installed_label = QtWidgets.QLabel("")
                    self.argos_installed_label.setObjectName("muted_label")
                    self.argos_installed_label.setWordWrap(True)
                    grid.addWidget(self.argos_installed_label, row, 1)
                    row += 1
                    self._refresh_argos_installed()
                    self.widgets["api_combo"].currentIndexChanged.connect(self._refresh_argos_installed)

            grid.setRowStretch(row, 1)  # pushes the content up if the tab is shorter than the others
            tabs.addTab(tab_page, self.i18n.tr(tab_label_key))

        main_layout.addWidget(tabs)
        self._start_voices_fetch()

        self._wire_dependencies()

        reset_btn = QtWidgets.QPushButton(self.i18n.tr("reset_defaults_button"))
        reset_btn.setObjectName("secondary_dialog_btn")
        reset_btn.clicked.connect(self._handle_reset)
        save_btn = QtWidgets.QPushButton(self.i18n.tr("save_button"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._handle_save)
        save_row = QtWidgets.QHBoxLayout()
        save_row.addWidget(reset_btn)
        save_row.addStretch()
        save_row.addWidget(save_btn)
        main_layout.addLayout(save_row)

    def _field_specs(self):
        """Declarative list: the single source for both the form and the widgets dict."""
        s = self.current

        def language_combo():
            w = QtWidgets.QComboBox()
            for code in self.i18n.available_languages:
                w.addItem(code.upper(), code)
            w.setCurrentIndex(max(0, w.findData(self.i18n.current_lang)))
            return w

        def text_size_spin():
            w = QtWidgets.QSpinBox()
            w.setRange(8, 64)
            w.setValue(s["text_size"])
            return w

        def color_combo():
            w = QtWidgets.QComboBox()
            for name, code in TEXT_COLOR_CHOICES.items():
                w.addItem(self.i18n.tr(name), code)
            values = list(TEXT_COLOR_CHOICES.values())
            w.setCurrentIndex(values.index(s["font_color"]) if s["font_color"] in values else 0)
            return w

        def opacity_slider():
            w = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            w.setRange(50, 255)
            w.setValue(s.get("overlay_opacity", 200))
            if self.on_opacity_preview:
                w.valueChanged.connect(self.on_opacity_preview)
            return w

        def checkbox(key):
            def make():
                w = QtWidgets.QCheckBox(self.i18n.tr("enabled"))
                w.setChecked(bool(s.get(key, False)))
                return w
            return make

        def refresh_interval_spin():
            w = QtWidgets.QSpinBox()
            w.setRange(1, 60)
            w.setValue(s.get("auto_refresh_interval", 5000) // 1000)
            return w

        def timeout_spin():
            w = QtWidgets.QSpinBox()
            w.setRange(5, 120)
            w.setSuffix(" " + self.i18n.tr("seconds_suffix"))
            w.setValue(s.get("translation_timeout", 25))
            return w

        def api_combo():
            w = QtWidgets.QComboBox()
            w.addItem(self.i18n.tr("translation_api_google"), "google")
            w.addItem(self.i18n.tr("translation_api_deepl"), "deepl")
            w.addItem(self.i18n.tr("translation_api_microsoft"), "microsoft")
            w.addItem(self.i18n.tr("translation_api_argos"), "argos")
            idx = w.findData(s.get("translation_api"))
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w

        def line_edit(key, default="", placeholder_key=None):
            def make():
                w = QtWidgets.QLineEdit(s.get(key, default))
                if placeholder_key:
                    w.setPlaceholderText(self.i18n.tr(placeholder_key))
                return w
            return make

        def audio_lang_combo():
            # Editable - works immediately, even offline (as if it were
            # a text field). The voice list arrives later, asynchronously
            # (see _start_voices_fetch) - it needs network access for the Microsoft
            # endpoint, so we don't block opening the dialog on it.
            w = QtWidgets.QComboBox()
            w.setEditable(True)
            current = s.get("audio_lang", "")
            if current:
                w.addItem(current)
            w.setCurrentText(current)
            w.lineEdit().setPlaceholderText(self.i18n.tr("audio_lang_placeholder"))
            self._configure_combo_completer(w)
            return w

        def audio_speed_combo():
            # Preset values like on YouTube (0.5x-2x), instead of raw
            # percentages - easier for the user to understand. Converted to
            # the edge-tts "rate" format (+N%/-N%) only when playback starts
            # (see core/audio_handler.py).
            w = QtWidgets.QComboBox()
            speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
            current = s.get("audio_speed", 1.0)
            for speed in speeds:
                label = f"{speed}x" if speed != 1.0 else f"{speed}x ({self.i18n.tr('normal_speed')})"
                w.addItem(label, speed)
            idx = w.findData(current)
            w.setCurrentIndex(idx if idx >= 0 else speeds.index(1.0))
            return w

        def ocr_lang_combo():
            w = QtWidgets.QComboBox()
            available = get_available_ocr_languages()
            current = s.get("ocr_lang", "eng")
            # If the currently saved language is for some reason not among
            # the .traineddata files found (e.g. the tessdata folder is
            # different now), add it anyway - so the user's choice doesn't
            # silently disappear just because tessdata changed.
            if current and current not in available:
                available = sorted(available + [current])
            for lang in available:
                w.addItem(lang, lang)
            idx = w.findData(current)
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w

        specs = [
            {"name": "language_combo", "label_key": "language_label", "make": language_combo, "tab": "interface"},
            {"name": "text_size_spin", "label_key": "text_size_label", "make": text_size_spin, "tab": "interface"},
            {"name": "color_combo", "label_key": "text_color_label", "make": color_combo, "tab": "interface"},
            {"name": "opacity_slider", "label_key": "opacity_label", "make": opacity_slider, "tab": "interface"},
            {"name": "hide_overlay_checkbox", "label_key": "hide_overlay_label", "make": checkbox("hide_overlay_enabled"), "tab": "interface"},
            {"name": "overlay_checkbox", "label_key": "overlay_translation_label", "make": checkbox("overlay_translation_enabled"), "tab": "interface"},
            {"name": "preserve_font_checkbox", "label_key": "preserve_font_label", "make": checkbox("preserve_font_size"), "tab": "interface"},
            {"name": "auto_refresh_checkbox", "label_key": "auto_refresh_label", "make": checkbox("auto_refresh_enabled"), "tab": "interface"},
            {"name": "refresh_interval_spin", "label_key": "refresh_interval_label", "make": refresh_interval_spin, "tab": "interface"},
            {"name": "api_combo", "label_key": "translation_api_label", "make": api_combo, "tab": "translation"},
            {"name": "translation_edit", "label_key": "translation_api_key_label", "make": line_edit("translation_api_key"), "tab": "translation"},
            {"name": "ocr_combo", "label_key": "ocr_lang_label", "make": ocr_lang_combo, "tab": "translation"},
            {"name": "target_edit", "label_key": "target_lang_label", "make": line_edit("target_lang", "", "target_lang_placeholder"), "tab": "translation"},
            {"name": "timeout_spin", "label_key": "translation_timeout_label", "make": timeout_spin, "tab": "translation"},
            {"name": "audio_combo", "label_key": "audio_lang_label", "make": audio_lang_combo, "tab": "audio"},
            {"name": "audio_speed_combo", "label_key": "audio_speed_label", "make": audio_speed_combo, "tab": "audio"},
        ]

        # Global hotkey - Windows and Linux/X11 (see core/hotkey_manager.py
        # for why Wayland/macOS stay disabled). On unsupported
        # platforms these fields don't appear in Settings at all, instead of
        # being shown disabled - clearer for the user.
        if HOTKEY_SUPPORTED:
            specs.append({
                "name": "hotkey_checkbox", "label_key": "hotkey_enabled_label",
                "make": checkbox("hotkey_enabled"), "tab": "hotkey",
            })
            specs.append({
                "name": "hotkey_edit", "label_key": "hotkey_combo_label",
                "make": line_edit("hotkey_combo", "<ctrl>+<alt>+t"), "tab": "hotkey",
            })
            specs.append({
                "name": "hotkey_retranslate_edit", "label_key": "hotkey_retranslate_label",
                "make": line_edit("hotkey_retranslate_combo", "", "hotkey_retranslate_placeholder"),
                "tab": "hotkey",
            })

        return specs

    def _wire_dependencies(self):
        """Overlay off → disables the dependent settings (preserve font / auto refresh / API key)."""
        w = self.widgets

        def update():
            overlay_enabled = w["overlay_checkbox"].isChecked()
            w["preserve_font_checkbox"].setEnabled(overlay_enabled)
            w["auto_refresh_checkbox"].setEnabled(overlay_enabled)
            w["refresh_interval_spin"].setEnabled(overlay_enabled and w["auto_refresh_checkbox"].isChecked())
            if not overlay_enabled:
                w["preserve_font_checkbox"].setChecked(False)
                w["auto_refresh_checkbox"].setChecked(False)

            selected_api = w["api_combo"].currentData()
            w["translation_edit"].setEnabled(selected_api in ("deepl", "microsoft"))

            if HOTKEY_SUPPORTED:
                hotkeys_on = w["hotkey_checkbox"].isChecked()
                w["hotkey_edit"].setEnabled(hotkeys_on)
                w["hotkey_retranslate_edit"].setEnabled(hotkeys_on)

        w["overlay_checkbox"].stateChanged.connect(update)
        w["auto_refresh_checkbox"].stateChanged.connect(update)
        w["api_combo"].currentIndexChanged.connect(update)
        if HOTKEY_SUPPORTED:
            w["hotkey_checkbox"].stateChanged.connect(update)
        update()

    # ------------------------------------------------------------------
    # Reading values / saving
    # ------------------------------------------------------------------

    def values(self):
        """Reads the current form values by widget NAME."""
        w = self.widgets
        result = {
            "text_size": w["text_size_spin"].value(),
            "font_color": w["color_combo"].currentData(),
            "translation_api_key": w["translation_edit"].text().strip(),
            "audio_lang": w["audio_combo"].currentText().strip(),
            "audio_speed": w["audio_speed_combo"].currentData(),
            "ocr_lang": w["ocr_combo"].currentData() or "eng",
            "target_lang": w["target_edit"].text().strip() or "BG",
            "translation_timeout": w["timeout_spin"].value(),
            "overlay_translation_enabled": w["overlay_checkbox"].isChecked(),
            "preserve_font_size": w["preserve_font_checkbox"].isChecked(),
            "auto_refresh_enabled": w["auto_refresh_checkbox"].isChecked(),
            "auto_refresh_interval": w["refresh_interval_spin"].value() * 1000,
            "overlay_opacity": w["opacity_slider"].value(),
            "interface_language": w["language_combo"].currentData(),
            "translation_api": w["api_combo"].currentData(),
            "hide_overlay_enabled": w["hide_overlay_checkbox"].isChecked(),
        }
        # hotkey_* fields exist only on Windows and Linux/X11 (see _field_specs) -
        # on other platforms we simply leave the existing values untouched.
        if HOTKEY_SUPPORTED:
            result["hotkey_enabled"] = w["hotkey_checkbox"].isChecked()
            result["hotkey_combo"] = w["hotkey_edit"].text().strip() or "<ctrl>+<alt>+t"
            # empty = no hotkey for "Translate again"
            result["hotkey_retranslate_combo"] = w["hotkey_retranslate_edit"].text().strip()
        return result

    def _start_voices_fetch(self):
        """Fetches the edge-tts voice list in the background (doesn't block the dialog)."""
        self._voices_thread = EdgeVoicesThread()
        self._voices_thread.voices_ready.connect(self._on_voices_ready)
        self._voices_thread.failed.connect(
            lambda e: logger.warning(f"Could not load the voice list (no network?): {e}")
        )
        self._voices_thread.start()

    def _on_voices_ready(self, voice_names):
        """Fills the audio language dropdown without changing what the user has already typed."""
        combo = self.widgets["audio_combo"]
        current_text = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(voice_names)
        combo.setCurrentText(current_text)
        combo.blockSignals(False)
        self._configure_combo_completer(combo)

    def _configure_combo_completer(self, combo):
        """
        By default an editable QComboBox puts the completer in inline
        mode (it only autocompletes the text) - without this the popup list of
        suggestions never shows up while you type.
        """
        completer = combo.completer()
        if completer:
            completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def _start_download(self, thread, status_label, download_btn, downloading_key):
        """
        Common start for the 'download and track progress' flows (tessdata language /
        offline translation models) - disables the button, shows the initial
        status, starts the thread. The progress signals themselves stay separate
        below because they have different signatures, but start and finish are
        identical.
        """
        download_btn.setEnabled(False)
        status_label.setText(self.i18n.tr(downloading_key))
        thread.start()

    def _finish_download(self, status_label, download_btn, success, message_key, params, done_key,
                          on_success=None):
        """
        Common finish - see _start_download for why it is separate from
        progress. On success params["name"] is what was downloaded (language/model), on
        failure the message is tr(message_key) with params filled in.
        """
        download_btn.setEnabled(True)
        message = params.get("name", "") if success else self.i18n.tr(message_key).format(**params)
        if success:
            status_label.setText(f"✅ {self.i18n.tr(done_key)}: {message}")
            if on_success:
                on_success(message)
        else:
            # Pop-up instead of inline text - same style as the other
            # errors in the dialog.
            status_label.setText("")
            QtWidgets.QMessageBox.critical(self, self.i18n.tr("warning_title"), message)

    def _handle_download_tessdata(self):
        """Downloads .traineddata from tessdata_fast and refreshes the OCR language list on success."""
        lang_code = self.tessdata_lang_edit.text().strip().lower()
        if not lang_code:
            return

        tessdata_dir = get_tessdata_dir()
        if tessdata_dir is None:
            QtWidgets.QMessageBox.critical(
                self, self.i18n.tr("warning_title"), self.i18n.tr("tessdata_dir_not_found")
            )
            return
        dest = tessdata_dir / f"{lang_code}.traineddata"
        self._tessdata_thread = TessdataDownloadThread(lang_code, dest)
        self._tessdata_thread.progress.connect(self._on_tessdata_progress)
        self._tessdata_thread.finished_download.connect(self._on_tessdata_finished)
        self._start_download(
            self._tessdata_thread, self.tessdata_download_status,
            self.tessdata_download_btn, "downloading_tessdata"
        )

    @staticmethod
    def _progress_text(downloaded, total):
        """"42%", or "3.5 MB" if the server didn't report the size."""
        if total > 0:
            return f"{int(downloaded * 100 / total)}%"
        return f"{downloaded / (1024 * 1024):.1f} MB"

    def _on_tessdata_progress(self, downloaded, total):
        self.tessdata_download_status.setText(
            f"{self.i18n.tr('downloading_tessdata')} ({self._progress_text(downloaded, total)})")

    def _on_tessdata_finished(self, success, message_key, params):
        self._finish_download(
            self.tessdata_download_status, self.tessdata_download_btn,
            success, message_key, params, "tessdata_downloaded", on_success=self._refresh_ocr_lang_combo
        )

    def _refresh_ocr_lang_combo(self, select=None):
        """Reloads the OCR language dropdown after a successful download."""
        combo = self.widgets["ocr_combo"]
        combo.blockSignals(True)
        combo.clear()
        for lang in get_available_ocr_languages():
            combo.addItem(lang, lang)
        target = select or self.current.get("ocr_lang", "eng")
        idx = combo.findData(target)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _argos_languages(self):
        """(source language, target language) per the current form selection."""
        source = argos.source_language(self.widgets["ocr_combo"].currentData() or "eng")
        target = (self.widgets["target_edit"].text().strip() or "BG").lower()[:2]
        return source, target

    def _refresh_argos_installed(self, _name=None):
        """Shows the downloaded language pairs for offline translation."""
        pairs = sorted(argos.installed_pairs())
        text = ", ".join(argos.pair_label(p) for p in pairs) if pairs else self.i18n.tr("argos_none_installed")
        if pairs and self.widgets["api_combo"].currentData() != "argos":
            # With an online service the models are used only when there is no internet.
            text = f"{text} {self.i18n.tr('argos_fallback_hint')}"
        self.argos_installed_label.setText(f"{self.i18n.tr('argos_installed_label')} {text}")

    def _handle_download_argos(self):
        """Downloads the offline translation models for the current languages (direct or via English)."""
        if not argos.libraries_available():
            QtWidgets.QMessageBox.critical(
                self, self.i18n.tr("warning_title"), self.i18n.tr("argos_not_installed")
            )
            return
        if ArgosDownloadThread.is_busy():
            # A download started from a previous opening of Settings is still running.
            self.argos_download_btn.setEnabled(False)
            self.argos_download_status.setText(self.i18n.tr("argos_downloading"))
            return
        source, target = self._argos_languages()
        if source == target:
            QtWidgets.QMessageBox.information(
                self, self.i18n.tr("warning_title"), self.i18n.tr("argos_same_language")
            )
            return
        self._argos_thread = ArgosDownloadThread(source, target)
        self._argos_thread.progress.connect(self._on_argos_progress)
        self._argos_thread.finished_download.connect(self._on_argos_finished)
        self._start_download(
            self._argos_thread, self.argos_download_status,
            self.argos_download_btn, "argos_downloading"
        )

    def _on_argos_progress(self, pair, downloaded, total):
        self.argos_download_status.setText(
            f"{self.i18n.tr('argos_downloading')} {pair} ({self._progress_text(downloaded, total)})")

    def _on_argos_finished(self, success, message_key, params):
        self._finish_download(
            self.argos_download_status, self.argos_download_btn,
            success, message_key, params, "argos_downloaded", on_success=self._refresh_argos_installed
        )

    def _handle_reset(self):
        """Resets all settings to their defaults (except the API key) and closes the dialog."""
        # Custom buttons instead of the standard Yes/No - the standard ones'
        # text comes from Qt's own translations, which we don't load,
        # so they showed up in English even with the Bulgarian UI.
        msg = QtWidgets.QMessageBox(self)
        msg.setIcon(QtWidgets.QMessageBox.Question)
        msg.setWindowTitle(self.i18n.tr("reset_defaults_button"))
        msg.setText(self.i18n.tr("reset_defaults_confirm"))
        yes_btn = msg.addButton(self.i18n.tr("yes_button"), QtWidgets.QMessageBox.YesRole)
        no_btn = msg.addButton(self.i18n.tr("no_button"), QtWidgets.QMessageBox.NoRole)
        msg.setDefaultButton(no_btn)
        msg.exec_()
        if msg.clickedButton() != yes_btn:
            return
        if self.on_save:
            self.on_save(self.settings_manager.defaults_for_reset(self.current))
        self.accept()

    def _handle_save(self):
        new_settings = dict(self.current)
        new_settings.update(self.values())

        try:
            self.settings_manager.validate(new_settings)
        except SettingsValidationError as e:
            detail = f"\n{e.detail}" if e.detail else ""
            QtWidgets.QMessageBox.critical(
                self, self.i18n.tr("warning_title"), f"{self.i18n.tr(e.message_key)}{detail}"
            )
            return

        if self.on_save:
            self.on_save(new_settings)
        self.accept()
