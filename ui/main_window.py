"""
MAIN APPLICATION WINDOW

Only the UI layout, the buttons and the connections between them remain here.
Settings, screenshot+OCR+translation, the translators and localization now
live in separate modules (see core/).
"""

from utils.imports import QtWidgets, QtCore, QtGui, QTimer, sys, threading
from utils.logging_setup import logger
from utils.config import image_path
from core.translations import TranslationCache, create_translator, fallback_notice_key
from core import argos
from core.argos_download import ArgosDownloadThread
from core.translation_controller import TranslationController
from core.settings_manager import SettingsManager
from core.localization import UiLocalizer
from core.audio_playback import AudioPlaybackToggle, AudioOptions
from core.capture import capture_full_screen_qimage, warm_up
from ui.components import SelectionWindow, WindowDragFilter, SecondaryOverlay, OverlayPanel
from ui.settings_dialog import SettingsDialog
from ui.history_window import HistoryWindow
from ui.dialogs import show_about, show_help, show_message, show_tesseract_missing, show_update_result
from core.tesseract_setup import configure_tesseract
from core.update_check import UpdateCheckThread
from ui.text_translate_window import TextTranslateWindow
from core.fullscreen_detector import FullscreenDetector
from core.hotkey_manager import (
    HotkeyManager, HOTKEY_SUPPORTED, ACTION_MARK_TRANSLATE, ACTION_RETRANSLATE, format_combo,
)
from core.history import TranslationHistory, SessionStats


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.set_window_icon()
        # Not shown anywhere else (the window is frameless, with no title
        # bar), but it matters for the taskbar/Alt-Tab - especially now, after
        # adding "minimize" (showMinimized()).
        self.setWindowTitle("Overlingo")
        self._tesseract_found = configure_tesseract() is not None

        self.i18n = UiLocalizer()
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()

        self._load_settings_into_fields(self.settings)

        self.stats = SessionStats()  # shown in the history window
        self.translation_cache = TranslationCache()
        self._current_translated_text = None

        self.translation_controller = TranslationController(
            self.translation_cache, timeout_ms=self.translation_timeout * 1000
        )
        self._reconfigure_translator()
        self.translation_controller.translation_finished.connect(self._on_translation_finished)
        self.translation_controller.translation_failed.connect(self._on_translation_failed)
        self.translation_controller.capture_finished.connect(self._on_capture_finished)
        self._overlay_pending_reshow = False

        self.fullscreen_detector = FullscreenDetector(self)

        self.audio = AudioPlaybackToggle(set_icon=self._set_play_button_icon, on_notice=self._on_audio_notice)
        self._refresh_in_progress = False
        self.selection_rect = None
        self.selection_window = None
        self.translation_overlay = None

        self.history = TranslationHistory()
        self.history_window = None   # created on first open
        self._update_thread = None   # update check (the "?" menu)
        self.text_window = None
        self._argos_download_thread = None  # offered download of offline languages (see offer_argos_download)
        self._argos_offer_open = False      # the question is on screen - don't ask again on top of it
        self._argos_offer_declined = set()  # "No" for a pair - don't ask again this session

        self.setup_ui()
        self.setup_connections()

        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(self.refresh_interval_ms)
        self.refresh_timer.timeout.connect(self.translate_selection)

        # Global hotkey - Windows and Linux/X11 (see core/hotkey_manager.py
        # for why Wayland/macOS stay disabled for now).
        self.hotkey_manager = HotkeyManager(self)
        self.hotkey_manager.triggered.connect(self._on_hotkey_triggered)
        self.hotkey_manager.failed.connect(self._on_hotkey_failed)
        self._reconfigure_hotkey()

        # "Warm up" mss in a background thread - otherwise the first real selection
        # (start_selection, synchronous on the main thread) freezes for 1-2s
        # due to mss's one-time initialization (see core/capture.py).
        threading.Thread(target=warm_up, daemon=True).start()

        # Deferred (not immediate) - so the dialog appears AFTER the main
        # window is already visible, not before/in the middle of constructing it.
        QtCore.QTimer.singleShot(300, self._show_tesseract_missing_warning)

    def _load_settings_into_fields(self, settings):
        """Unpacks the settings dict into window attributes."""
        self.text_size = settings["text_size"]
        self.font_color = settings["font_color"]
        self.overlay_opacity = settings["overlay_opacity"]
        self.translation_api = settings["translation_api"]
        self.translation_api_key = settings["translation_api_key"]
        self.audio_lang = settings["audio_lang"]
        self.audio_speed = settings["audio_speed"]
        self.tts_engine = settings["tts_engine"]
        self.ocr_lang = settings["ocr_lang"]
        self.target_lang = settings["target_lang"] or "BG"
        self.overlay_translation_enabled = settings["overlay_translation_enabled"]
        self.preserve_font_size = settings["preserve_font_size"]
        self.auto_refresh_enabled = settings["auto_refresh_enabled"]
        self.refresh_interval_ms = settings["auto_refresh_interval"]
        self.hide_overlay_enabled = settings["hide_overlay_enabled"]
        self.hotkey_enabled = settings["hotkey_enabled"]
        self.hotkey_combo = settings["hotkey_combo"]
        self.hotkey_retranslate_combo = settings["hotkey_retranslate_combo"]
        self.translation_timeout = settings["translation_timeout"]

    def _reconfigure_translator(self):
        """Recreates the translator from the current settings and hands it to the controller."""
        translator = create_translator(
            self.translation_api, self.translation_api_key,
            source_lang=argos.source_language(self.ocr_lang),
        )
        self.translation_controller.configure(translator, self.ocr_lang, self.target_lang)

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------

    def setup_ui(self):
        """User interface setup"""
        base_flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        self.fullscreen_detector.apply_window_flags(self, base_flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.i18n.set_language(self.settings.get("interface_language", "en"))

        screen = QtWidgets.QApplication.primaryScreen().geometry()
        window_width, window_height = 800, 200
        self._full_window_height = window_height
        self._toolbar_only_height = 55  # just the button toolbar, without the overlay panel
        x, y = (screen.width() - window_width) // 2, screen.height() - window_height - 10

        if self.settings.get("window_pos"):
            x, y = self.settings["window_pos"]

        self.setGeometry(x, y, window_width, window_height)

        self.setup_buttons_background()
        self.setup_buttons()
        self.setup_text_display()
        self.apply_overlay_visibility()

    def setup_buttons_background(self):
        """
        Rounded semi-transparent background for the button toolbar - and at the same time
        the area you can press and drag to move the whole app
        (see WindowDragFilter). The buttons are created afterwards and lie
        on top of it (bg_widget.lower()), so clicks on them
        work normally - dragging only catches the empty space.
        """
        self.bg_widget = QtWidgets.QWidget(self)
        self.bg_widget.setGeometry(10, 5, 780, 40)
        self.bg_widget.setStyleSheet("""
            QWidget {
                background: rgba(45, 45, 45, 210);
                border-radius: 8px;
                border: 1px solid rgba(90, 90, 90, 150);
            }
        """)
        self.bg_widget.lower()

        self._drag_filter = WindowDragFilter(self)
        self.bg_widget.installEventFilter(self._drag_filter)

    def setup_connections(self):
        """Connects signals to slots"""
        self.mark_translate_btn.clicked.connect(self.mark_and_translate)
        self.retranslate_btn.clicked.connect(self.translate_selection)
        self.clear_btn.clicked.connect(self.clear_overlay)
        self.play_btn.clicked.connect(self.start_play)
        self.text_translate_btn.clicked.connect(self.show_text_window)
        self.history_btn.clicked.connect(self.show_history)
        self.toggle_overlay_btn.clicked.connect(self.toggle_overlay_visibility)
        self.exit_btn.clicked.connect(self.close)
        self.minimize_btn.clicked.connect(self._minimize_window)
        self.settings_btn.clicked.connect(self.show_settings)
        self.help_action.triggered.connect(self.show_help)
        self.check_updates_action.triggered.connect(self.check_for_updates)
        self.about_action.triggered.connect(self.show_about)

    def _position_translation_status(self):
        """
        The spinner sits inside the "Select and translate" button, a short distance
        after the text (not stuck to the edge - the text is centered and then
        it almost touched it). Also called when the language changes, because
        the text length differs.
        """
        icon_size = 22
        gap_after_text = 10
        btn = self.mark_translate_btn
        btn_geo = btn.geometry()
        btn.ensurePolished()  # the font size comes from theme.qss
        text_width = QtGui.QFontMetrics(btn.font()).horizontalAdvance(btn.text())
        text_right = btn_geo.center().x() + text_width // 2
        x = min(text_right + gap_after_text, btn_geo.right() - icon_size - 2)
        y = btn_geo.top() + (btn_geo.height() - icon_size) // 2
        self.translation_status.setGeometry(x, y, icon_size, icon_size)
        self.translation_status.raise_()

    def setup_buttons(self):
        """
        Creates and positions the buttons. The left side is in three groups with slightly
        larger spacing between them:
          screen translation: [Select and translate] [⟳] [Clear] [▶]
          other ways:         [Aa] [history]
          view:               [eye]
        On the right: [?] (help / about), settings, minimize, exit.
        """
        y, h = 10, 30
        gap, group_gap = 15, 30
        x = self.bg_widget.x() + 5

        # --- screen translation ---
        self.mark_translate_btn = QtWidgets.QPushButton(self)
        self.mark_translate_btn.setObjectName("primary_btn")
        self.mark_translate_btn.setGeometry(x, y, 230, h)  # room for the spinner after the text too
        x += 230 + gap

        self.retranslate_btn = self._make_icon_button(
            "retranslate_button_white.png", x, object_name="secondary_icon_btn"
        )
        self.retranslate_btn.setEnabled(False)  # until an area has been selected
        x += h + gap

        self.clear_btn = QtWidgets.QPushButton(self)
        self.clear_btn.setObjectName("secondary_btn")
        self.clear_btn.setGeometry(x, y, 90, h)
        x += 90 + gap

        self.play_btn = self._make_icon_button(
            "play_button_white.png", x, width=40, object_name="secondary_icon_btn"
        )
        self.play_btn.setEnabled(False)  # enabled only once there is a translation to read
        x += 40 + group_gap

        # --- other ways to translate ---
        self.text_translate_btn = self._make_icon_button(
            "text_translate_button_white.png", x, object_name="secondary_icon_btn"
        )
        x += h + gap
        self.history_btn = self._make_icon_button(
            "history_button_white.png", x, object_name="secondary_icon_btn"
        )
        x += h + group_gap

        # --- view ---
        self.toggle_overlay_btn = self._make_icon_button(
            "show_button_white.png", x, object_name="secondary_icon_btn"
        )

        self.translation_status = QtWidgets.QLabel(self)
        self.translation_status.setAlignment(QtCore.Qt.AlignCenter)
        # Lies over the translate button - without this, clicks right on
        # the spinner wouldn't reach the button underneath.
        self.translation_status.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.translation_status.hide()  # visible only while a translation is running

        # White version of spinner.png - contrasts well with the blue button.
        self.status_icon = QtGui.QPixmap(image_path("spinner_white.png"))
        self.scaled_icon = self.status_icon.scaled(18, 18, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.translation_status.setPixmap(self.scaled_icon)

        self.animation = QtCore.QVariantAnimation(self)
        self.animation.setDuration(1000)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self.rotate_icon)

        # --- right side, right to left ---
        step = 35
        right_x = self.bg_widget.x() + self.bg_widget.width() - 35
        self.exit_btn = self._make_icon_button("close_button_white.png", right_x)
        right_x -= step
        self.minimize_btn = self._make_icon_button("minimize_button_white.png", right_x)
        right_x -= step
        self.settings_btn = self._make_icon_button("settings_button_white.png", right_x)
        right_x -= step

        # "Help" and "About" share one menu - they are used less often,
        # and this frees up room for the new buttons on the left.
        self.help_btn = self._make_icon_button("help_button_white.png", right_x)
        self.help_btn.setObjectName("menu_icon_btn")
        self.help_menu = QtWidgets.QMenu(self)
        self.help_action = self.help_menu.addAction("")
        self.check_updates_action = self.help_menu.addAction("")
        self.about_action = self.help_menu.addAction("")
        self.help_btn.setMenu(self.help_menu)
        self.help_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        self.update_ui_texts()

    def _make_icon_button(self, icon_file, x, width=None, object_name=None):
        """
        Helper: replaces the repeated code for creating a 30x30 icon
        button. width (wider button) and object_name also cover
        non-standard cases (e.g. play_btn - wider, with a gray box style).
        """
        btn = QtWidgets.QToolButton(self)
        btn.setGeometry(x, 10, width or 30, 30)
        btn.setIcon(QtGui.QIcon(image_path(icon_file)))
        btn.setIconSize(QtCore.QSize(15, 15))
        btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        if object_name:
            btn.setObjectName(object_name)
        return btn

    def setup_text_display(self):
        self.overlay_panel = OverlayPanel(alpha=self.overlay_opacity, parent=self)
        self.overlay_panel.setGeometry(10, 50, 780, 140)

        self.text_display = QtWidgets.QTextEdit(self.overlay_panel)
        self.text_display.setGeometry(0, 0, self.overlay_panel.width(), self.overlay_panel.height())
        self.text_display.setReadOnly(True)
        self.text_display.setFrameStyle(QtWidgets.QFrame.NoFrame)
        # "Clear" is enabled only when there is something to clear
        self.text_display.textChanged.connect(self._update_clear_button)
        self._update_clear_button()

        self.text_display.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.text_display.setAutoFillBackground(False)
        self.text_display.viewport().setAutoFillBackground(False)
        pal = self.text_display.viewport().palette()
        pal.setBrush(QtGui.QPalette.Base, QtCore.Qt.transparent)
        self.text_display.viewport().setPalette(pal)

        self.text_display.setStyleSheet(
            f"background: transparent; color: {self.font_color}; font-size:{self.text_size}px;"
        )

    def update_ui_texts(self):
        """The toolbar texts (at startup and when the language changes)."""
        t = self.i18n.tr
        self.mark_translate_btn.setText(t("mark_translate_button"))
        self._position_translation_status()
        self.clear_btn.setText(t("clear_button"))
        self.clear_btn.setToolTip(t("clear_button_tooltip"))
        self.play_btn.setToolTip(t("play_stop_audio"))
        self.text_translate_btn.setToolTip(t("text_translate_tooltip"))
        self.history_btn.setToolTip(t("history_tooltip"))
        self.toggle_overlay_btn.setToolTip(t("toggle_overlay_tooltip"))
        self.exit_btn.setToolTip(t("exit_button_tooltip"))
        self.minimize_btn.setToolTip(t("minimize_button_tooltip"))
        self.settings_btn.setToolTip(t("settings_button_tooltip"))
        self.help_btn.setToolTip(t("help_menu_tooltip"))
        self.help_action.setText(t("help_menu_help"))
        self.check_updates_action.setText(t("check_updates_menu"))
        self.about_action.setText(t("help_menu_about"))
        self._update_hotkey_tooltips()
        for window in (self.history_window, self.text_window):
            if window:
                window.update_texts()

    def _update_hotkey_tooltips(self):
        """The tooltips of both translate buttons also show the hotkey, if enabled."""
        hotkeys_on = HOTKEY_SUPPORTED and self.hotkey_enabled

        def with_hotkey(text, combo):
            return f"{text} ({format_combo(combo)})" if hotkeys_on and combo else text

        self.mark_translate_btn.setToolTip(
            with_hotkey(self.i18n.tr("mark_translate_tooltip"), self.hotkey_combo))
        self.retranslate_btn.setToolTip(
            with_hotkey(self.i18n.tr("retranslate_tooltip"), self.hotkey_retranslate_combo))

    def toggle_overlay_visibility(self):
        """Toggles the overlay panel's visibility (the eye button)"""
        self._set_overlay_panel_visible(not self.overlay_panel.isVisible())

    def _set_overlay_panel_visible(self, visible):
        """
        Shows/hides the overlay panel AND resizes the window itself.

        The panel is a child of the main window - just hiding it is not
        enough, because the window (frameless, always-on-top) still takes up
        its full height and keeps "catching" clicks over the
        programs beneath it, even when nothing is visible there. We shrink
        the window to the height of the button toolbar alone when the panel
        is hidden, and restore it when the panel is shown.
        """
        if visible:
            self.overlay_panel.show()
            self.toggle_overlay_btn.setIcon(QtGui.QIcon(image_path("show_button_white.png")))
            self.resize(self.width(), self._full_window_height)
        else:
            self.overlay_panel.hide()
            self.toggle_overlay_btn.setIcon(QtGui.QIcon(image_path("hide_button_white.png")))
            self.resize(self.width(), self._toolbar_only_height)

    def rotate_icon(self, angle):
        transform = QtGui.QTransform()
        transform.rotate(angle)
        rotated_pixmap = self.scaled_icon.transformed(transform, QtCore.Qt.SmoothTransformation)
        self.translation_status.setPixmap(rotated_pixmap)

    def set_translation_status(self, busy: bool):
        if busy:
            self.translation_status.show()
            self.translation_status.raise_()
            self.animation.start()
        else:
            self.animation.stop()
            self.translation_status.setPixmap(self.scaled_icon)
            self.translation_status.hide()

    def mark_and_translate(self):
        """Select and translate in one go"""
        self.start_selection(callback=self.on_selection_complete_for_translate)

    def on_selection_complete_for_translate(self, rect):
        # Close the previous overlay immediately - otherwise it stays with the text of
        # the previous translation while we wait for the new OCR+translation (or, if the new
        # area is elsewhere on the screen, it doesn't move there at all).
        self._close_translation_overlay()
        self.save_selection(rect)
        QtCore.QTimer.singleShot(100, self.translate_selection)

    def _close_translation_overlay(self):
        """Closes the current overlay (if any) right away, not only once the new translation is ready."""
        if self.translation_overlay:
            self.translation_overlay.close()

    def show_about(self):
        show_about(self, self.i18n)

    def show_help(self):
        show_help(self, self.i18n)

    def check_for_updates(self):
        """
        "Check for updates" from the "?" menu. The request to GitHub runs in a
        background thread; while it runs, the menu item is disabled so that
        two checks can't be started at once.
        """
        if self._update_thread and self._update_thread.isRunning():
            return
        self.check_updates_action.setEnabled(False)
        self._update_thread = UpdateCheckThread()
        self._update_thread.result_ready.connect(self._on_update_result)
        self._update_thread.start()

    def _on_update_result(self, result):
        self.check_updates_action.setEnabled(True)
        show_update_result(self, self.i18n, result)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def show_settings(self):
        """Shows the settings dialog (see ui/settings_dialog.py)"""
        dialog = SettingsDialog(
            self,
            self.settings_manager,
            self.i18n,
            current_settings=self._collect_current_settings(),
            on_opacity_preview=self._preview_opacity,
            on_save=self.apply_settings,
        )
        dialog.exec_()

    def _preview_opacity(self, value):
        """Reacts to the opacity slider immediately, before Save is pressed."""
        self.overlay_panel.set_alpha(value)

    def _collect_current_settings(self):
        """The current window state as a dict (for SettingsDialog)."""
        return {
            "text_size": self.text_size,
            "font_color": self.font_color,
            "overlay_opacity": self.overlay_opacity,
            "translation_api": self.translation_api,
            "translation_api_key": self.translation_api_key,
            "audio_lang": self.audio_lang,
            "audio_speed": self.audio_speed,
            "tts_engine": self.tts_engine,
            "ocr_lang": self.ocr_lang,
            "target_lang": self.target_lang,
            "overlay_translation_enabled": self.overlay_translation_enabled,
            "preserve_font_size": self.preserve_font_size,
            "auto_refresh_enabled": self.auto_refresh_enabled,
            "auto_refresh_interval": self.refresh_interval_ms,
            "hide_overlay_enabled": self.hide_overlay_enabled,
            "hotkey_enabled": self.hotkey_enabled,
            "hotkey_combo": self.hotkey_combo,
            "hotkey_retranslate_combo": self.hotkey_retranslate_combo,
            "translation_timeout": self.translation_timeout,
        }

    def apply_settings(self, settings):
        """Applies already validated settings (called from SettingsDialog.on_save)."""
        self._load_settings_into_fields(settings)
        # The "Auto translate" checkbox isn't in the settings dialog, but
        # "Restore defaults" must reset it too.
        if "text_auto_translate" in settings:
            self.settings["text_auto_translate"] = settings["text_auto_translate"]
            if self.text_window:
                self.text_window.set_auto_translate(settings["text_auto_translate"])
        self._reconfigure_hotkey()
        self.translation_controller.timeout_ms = self.translation_timeout * 1000

        self.overlay_panel.set_alpha(self.overlay_opacity)

        self.text_display.setStyleSheet(
            f"background: transparent; color: {self.font_color}; font-size:{self.text_size}px;"
        )

        self.refresh_timer.setInterval(self.refresh_interval_ms)
        self._reconfigure_translator()

        if settings["interface_language"] != self.i18n.current_lang:
            self.i18n.set_language(settings["interface_language"])
            self.update_ui_texts()

        if self.translation_overlay and self.translation_overlay.isVisible() and self.auto_refresh_enabled:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

        self.apply_overlay_visibility()
        self.save_settings_to_file()

    def save_settings_to_file(self):
        """Saves the current settings to file via SettingsManager."""
        self.settings.update(self._collect_current_settings())
        self.settings["window_pos"] = [self.x(), self.y()]
        self.settings["interface_language"] = self.i18n.current_lang
        self.settings_manager.save(self.settings)

    def apply_overlay_visibility(self):
        self._set_overlay_panel_visible(not self.hide_overlay_enabled)

    # ------------------------------------------------------------------
    # Area selection
    # ------------------------------------------------------------------

    def start_selection(self, callback):
        """Starts selecting an area of the screen."""
        if self.selection_window and self.selection_window.isVisible():
            return  # already selecting (e.g. the hotkey was pressed twice)
        screenshot_qt = capture_full_screen_qimage()
        self.selection_window = SelectionWindow(screenshot_qt, hint_text=self.i18n.tr("selection_hint"))
        self.selection_window.selection_made.connect(callback)
        self.selection_window.show()

    def save_selection(self, rect):
        self.selection_rect = rect
        self.retranslate_btn.setEnabled(True)
        self._update_clear_button()
        self.text_display.append(
            f"{self.i18n.tr('area_marked')}: {rect.left()}, {rect.top()}, {rect.right()}, {rect.bottom()}"
        )

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def _set_play_button_icon(self, icon_filename):
        # play_button.png/stop_button.png are black - on the solid gray background of
        # the play button (secondary_icon_btn) we want the white version so it
        # matches the other toolbar icons.
        white_filename = icon_filename.replace(".png", "_white.png")
        self.play_btn.setIcon(QtGui.QIcon(image_path(white_filename)))

    def _set_current_translation(self, text):
        """Remembers the last translation and enables/disables the play button accordingly."""
        self._current_translated_text = text or None
        self.play_btn.setEnabled(bool(self._current_translated_text))

    def _on_audio_notice(self, key):
        """Messages from the playback (no voice, no internet, online fallback) - in the text panel."""
        icon = "ℹ" if key == "tts_fallback_online" else "❌"
        self.text_display.append(f"{icon} {self.i18n.tr(key)}\n")

    def start_play(self):
        self.audio.toggle(self._current_translated_text, self._audio_settings())

    # ------------------------------------------------------------------
    # Translation (delegated to TranslationController - see core/translation_controller.py)
    # ------------------------------------------------------------------

    def translate_selection(self):
        """Starts translating the selected area."""
        if not self.selection_rect:
            self.text_display.append(f"❌ {self.i18n.tr('no_area_selected')}\n")
            return
        if self._refresh_in_progress:
            return

        self._refresh_in_progress = True
        self.set_translation_status(True)
        QTimer.singleShot(0, self._start_translation)

    def _start_translation(self):
        self._overlay_pending_reshow = False
        if self.translation_overlay and self.translation_overlay.isVisible():
            if self.translation_overlay.geometry().intersects(self.selection_rect):
                self._overlay_pending_reshow = True
                self.translation_overlay.hide()
                # .hide() only marks the window to be hidden - actually
                # disappearing from the screen (window manager/compositor)
                # takes a fraction of a second. processEvents() only flushes
                # Qt's queue, but doesn't guarantee the compositor has
                # actually redrawn the screen without the overlay - hence the short
                # (non-blocking, via the event loop) wait after it,
                # before the screenshot is taken.
                QtWidgets.QApplication.processEvents()
                QtCore.QTimer.singleShot(80, self._capture_and_translate)
                return

        self._capture_and_translate()

    def _capture_and_translate(self):
        # The font size is needed only for a new overlay - on auto-refresh and
        # "Translate again" over an already open overlay a second OCR pass
        # would be redundant.
        detect_font_size = (
            self.preserve_font_size and self.overlay_translation_enabled and self.translation_overlay is None
        )
        self.translation_controller.translate_region(self.selection_rect, detect_font_size=detect_font_size)

    def _reshow_overlay_if_pending(self):
        """
        Shows the overlay again if we hid it for the current cycle.
        Called right after the screenshot (capture_finished) and on
        error/timeout - never waits for the whole OCR+translation to finish,
        so the overlay doesn't stay hidden for seconds for no reason.
        """
        if self._overlay_pending_reshow and self.translation_overlay:
            self.translation_overlay.show()
        self._overlay_pending_reshow = False

    def _on_capture_finished(self):
        """The screenshot is ready - the overlay can be shown again without waiting for the translation."""
        self._reshow_overlay_if_pending()

    def _on_translation_failed(self, error_key, detail, source_text):
        self._refresh_in_progress = False
        self.set_translation_status(False)
        if source_text:
            self.text_display.append(self.i18n.tr("detected_text"))
            self.text_display.append(source_text)
        message = f"❌ {self.i18n.tr(error_key)}"
        self.text_display.append(f"{message}: {detail}\n" if detail else f"{message}\n")
        if error_key == "argos_model_missing":
            # Offline translation is the default - the first translation offers the download.
            self.offer_argos_download(detail, then=self.translate_selection)
        if error_key == "translation_timeout":
            # A separate visible pop-up only for timeouts - unlike
            # the other errors, here the user probably wants to know
            # right away (not just a line in the text panel), because the fix
            # is usually "increase the timeout in Settings", not just "try again".
            show_message(self, self.i18n, self.i18n.tr("warning_title"), self.i18n.tr("translation_timeout"))
        self._reshow_overlay_if_pending()

    def offer_argos_download(self, pair_text, then=None, parent=None):
        """
        The models for offline translation are not downloaded yet - asks whether to
        download them now (once, ~70 MB per language pair) and, when done, calls
        then() (translates again). Progress goes to the text panel.
        """
        if ArgosDownloadThread.is_busy() or self._argos_offer_open or pair_text in self._argos_offer_declined:
            return
        if not argos.libraries_available():
            return
        msg = QtWidgets.QMessageBox(parent or self)
        msg.setIcon(QtWidgets.QMessageBox.Question)
        msg.setWindowTitle(self.i18n.tr("argos_offer_title"))
        msg.setText(self.i18n.tr("argos_offer_text").format(pair=pair_text))
        yes_btn = msg.addButton(self.i18n.tr("argos_offer_download"), QtWidgets.QMessageBox.YesRole)
        no_btn = msg.addButton(self.i18n.tr("no_button"), QtWidgets.QMessageBox.NoRole)
        msg.setDefaultButton(yes_btn)
        self._argos_offer_open = True
        try:
            msg.exec_()
        finally:
            self._argos_offer_open = False
        if msg.clickedButton() != yes_btn:
            self._argos_offer_declined.add(pair_text)
            return

        source = argos.source_language(self.ocr_lang)
        target = (self.target_lang or "BG").strip().lower()[:2]
        thread = ArgosDownloadThread(source, target)
        reported = set()  # progress at 25% steps - not a line per chunk

        def on_progress(pair, downloaded, total):
            step = int(downloaded * 4 / total) * 25 if total > 0 else None
            if step is not None and (pair, step) not in reported:
                reported.add((pair, step))
                self.text_display.append(f"{self.i18n.tr('argos_downloading')} {pair} ({step}%)")

        def on_finished(success, message_key, params):
            self._argos_download_thread = None
            if success:
                self.text_display.append(f"✅ {self.i18n.tr('argos_downloaded')}: {params.get('name', '')}\n")
                self._reconfigure_translator()
                if then:
                    then()
            else:
                self.text_display.append(f"❌ {self.i18n.tr(message_key).format(**params)}\n")

        thread.progress.connect(on_progress)
        thread.finished_download.connect(on_finished)
        self._argos_download_thread = thread
        self.text_display.append(f"{self.i18n.tr('argos_downloading')} {pair_text}")
        self._restore_window()
        self._set_overlay_panel_visible(True)
        thread.start()

    def _on_translation_finished(self, source_text, translated_text, from_cache, fallback_used,
                                  font_size, rect):
        """Handles translation completion (signal from TranslationController)."""
        self.set_translation_status(False)
        self._refresh_in_progress = False

        self.stats.record(from_cache)

        label = "detected_text_cash" if from_cache else "detected_text"
        self.text_display.append(f"{self.i18n.tr(label)}")
        self.text_display.append(source_text)
        if fallback_used:
            self.text_display.append(f"⚠ {self.i18n.tr(fallback_notice_key(fallback_used))}")
        self.text_display.append(f"{self.i18n.tr('translation')}")
        self.text_display.append(translated_text + "\n")
        self._set_current_translation(translated_text)
        self._add_to_history(source_text, translated_text)

        if self.overlay_translation_enabled and translated_text:
            self._show_or_update_overlay(translated_text, font_size, rect)

        self._maybe_start_refresh()

    def _show_or_update_overlay(self, translated_text, font_size, rect):
        # font_size was measured in the background thread (see _capture_and_translate);
        # 0 - not measured (font size isn't preserved, or the overlay is already open).
        overlay_font_size = font_size or self.text_size

        if self.translation_overlay is None:
            self.translation_overlay = SecondaryOverlay(
                translated_text,
                QtCore.QRect(rect.left(), rect.top(), rect.width(), rect.height()),
                font_size=overlay_font_size,
                font_color=self.font_color,
                background_opacity=self.overlay_opacity,
                get_audio_settings=self._audio_settings,
                i18n=self.i18n,
            )
            self.translation_overlay.closed.connect(self._on_overlay_closed)
            self._update_clear_button()
        elif translated_text != self.translation_overlay.text_label.text():
            self.translation_overlay.setText(translated_text)

    def _on_overlay_closed(self):
        self.refresh_timer.stop()
        self.translation_overlay = None
        self._update_clear_button()
        # Do NOT call self.show() here - if the user minimized
        # the main window themselves (or the overlay appeared while it was already
        # minimized), closing the overlay must not force it to
        # restore. The minimized state only changes manually.

    def _maybe_start_refresh(self):
        should_refresh = (
            self.auto_refresh_enabled and self.overlay_translation_enabled
            and self.translation_overlay and self.translation_overlay.isVisible()
            and self.selection_rect
        )
        if should_refresh:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def clear_overlay(self):
        self.selection_rect = None
        self.retranslate_btn.setEnabled(False)
        self.audio.stop()  # nothing left to read
        self._set_current_translation(None)
        self.text_display.clear()
        self.refresh_timer.stop()
        self.translation_cache.clear()
        self._close_translation_overlay()  # if there is an active overlay - "Clear" means everything
        self._update_clear_button()

    def _update_clear_button(self):
        """Enabled if there is text in the panel, a selected area or an open overlay."""
        has_something = bool(
            self.text_display.toPlainText().strip()
            or self.selection_rect
            or self.translation_overlay
        )
        self.clear_btn.setEnabled(has_something)

    # ------------------------------------------------------------------
    # Global hotkey (Windows and Linux/X11)
    # ------------------------------------------------------------------

    def _minimize_window(self):
        """Plain minimize to the taskbar - called from minimize_btn."""
        self.showMinimized()

    def _restore_window(self):
        """Restores the window from the minimized state (taskbar) - called from the hotkey."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def bring_to_front(self):
        """Launching the app a second time shows the already open one (see core/single_instance.py)."""
        self._restore_window()

    def _reconfigure_hotkey(self):
        """Starts/stops the global hotkeys per the current settings (Windows/Linux X11)."""
        if HOTKEY_SUPPORTED and self.hotkey_enabled and self.hotkey_combo:
            self.hotkey_manager.start({
                ACTION_MARK_TRANSLATE: self.hotkey_combo,
                ACTION_RETRANSLATE: self.hotkey_retranslate_combo,
            })
        else:
            self.hotkey_manager.stop()
        self._update_hotkey_tooltips()

    def _on_hotkey_triggered(self, action):
        """
        We show the window again ONLY if overlay display is off -
        otherwise the result appears directly over the text anyway
        (SecondaryOverlay), not in the window itself - bringing it back here would
        only add a pointless flicker.
        """
        if not self.overlay_translation_enabled:
            self._restore_window()
        if action == ACTION_RETRANSLATE:
            self.translate_selection()
        else:
            self.mark_and_translate()

    def _on_hotkey_failed(self, error):
        """
        A visible message, not just a log entry - otherwise the hotkey simply
        "doesn't work" with no explanation. Deferred, because it may arrive while
        the window is still being created.
        """
        logger.warning(f"Hotkey could not be activated: {error}")
        QtCore.QTimer.singleShot(0, lambda: show_message(
            self, self.i18n, self.i18n.tr("warning_title"), f"{self.i18n.tr('hotkey_failed')}\n\n{error}"
        ))

    # ------------------------------------------------------------------
    # History and text translation
    # ------------------------------------------------------------------

    def _add_to_history(self, source, translation):
        self.history.add(source, translation)
        if self.history_window and self.history_window.isVisible():
            self.history_window.refresh()

    def _on_text_translated(self, source, translation, from_cache):
        """Translation from the "Translate text" window - counted and added to the history."""
        self.stats.record(from_cache)
        self._add_to_history(source, translation)

    def _audio_settings(self):
        """What to read with - engine, voice, speed and the language of the translation."""
        return AudioOptions(self.tts_engine, self.audio_lang, self.audio_speed, self.target_lang)

    def show_history(self):
        if self.history_window is None:
            self.history_window = HistoryWindow(
                self, self.i18n, self.history,
                on_show=self._show_history_entry,
                get_audio_settings=self._audio_settings,
                stats=self.stats,
            )
        self.history_window.refresh()
        self.history_window.show()
        self.history_window.raise_()
        self.history_window.activateWindow()

    def _show_history_entry(self, entry):
        """"Show" from the history - the translation appears in the toolbar's text panel."""
        self._restore_window()
        self._set_overlay_panel_visible(True)
        self.text_display.append(self.i18n.tr("detected_text"))
        self.text_display.append(entry.source)
        self.text_display.append(self.i18n.tr("translation"))
        self.text_display.append(entry.translation + "\n")
        self._set_current_translation(entry.translation)

    def show_text_window(self):
        if self.text_window is None:
            self.text_window = TextTranslateWindow(
                self, self.i18n,
                get_translator=lambda: self.translation_controller.translator,
                get_target_lang=lambda: self.target_lang,
                cache=self.translation_cache,
                get_audio_settings=self._audio_settings,
                on_translated=self._on_text_translated,
                on_argos_missing=lambda pair: self.offer_argos_download(
                    pair, then=self.text_window.translate_now, parent=self.text_window),
                on_geometry=self._save_text_window_geometry,
                geometry=self.settings.get("text_window_geometry"),
                auto_translate=self.settings.get("text_auto_translate", True),
                on_auto_changed=self._save_text_auto_translate,
            )
        self.text_window.bring_up()

    def _save_text_auto_translate(self, enabled):
        self.settings["text_auto_translate"] = enabled

    def _save_text_window_geometry(self, geometry):
        self.settings["text_window_geometry"] = geometry

    # ------------------------------------------------------------------
    # Startup / shutdown
    # ------------------------------------------------------------------

    def set_window_icon(self):
        """Automatically loads the right icon for each OS"""
        try:
            from utils.config import APP_ICON_WINDOWS, APP_ICON_MAC, APP_ICON_LINUX

            if sys.platform == "win32":
                icon_path, platform_name = APP_ICON_WINDOWS, "Windows"
            elif sys.platform == "darwin":
                icon_path, platform_name = APP_ICON_MAC, "macOS"
            elif sys.platform.startswith("linux"):
                icon_path, platform_name = APP_ICON_LINUX, "Linux"
            else:
                icon_path, platform_name = APP_ICON_LINUX, "Linux (fallback)"

            if icon_path.exists():
                self.setWindowIcon(QtGui.QIcon(str(icon_path)))
                logger.info(f"{platform_name} icon loaded: {icon_path}")
            else:
                logger.warning(f"{platform_name} icon not found: {icon_path}")
        except Exception as e:
            logger.error(f"Error loading icon: {e}", exc_info=True)

    def _show_tesseract_missing_warning(self):
        """
        A visible dialog (not just a log) - otherwise the user just sees that
        OCR "doesn't work", with no clear reason. Deferred from __init__ so that it
        appears after the main window is already visible.
        """
        if not self._tesseract_found:
            self._tesseract_found = show_tesseract_missing(self, self.i18n)

    def closeEvent(self, event):
        # The text window goes first - on hide it writes its size into
        # self.settings, which is saved on the next line.
        if self.text_window:
            self.text_window.close()
            self.text_window.wait_for_threads()
        if self.history_window:
            self.history_window.close()
        if self._update_thread:
            self._update_thread.wait(3000)  # a thread destroyed while running crashes Qt on exit
        self.save_settings_to_file()
        self.hotkey_manager.stop()
        self._close_translation_overlay()  # otherwise it is left "orphaned" on screen after closing
        super().closeEvent(event)
