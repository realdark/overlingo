"""
ГЛАВЕН ПРОЗОРЕЦ НА ПРИЛОЖЕНИЕТО

Тук остава само подредбата на UI-а, бутоните и връзките между тях.
Settings, screenshot+OCR+превод, преводачите и локализацията вече
живеят в отделни модули (виж core/).
"""

from utils.imports import QtWidgets, QtCore, QtGui, QTimer, sys, threading
from utils.logging_setup import logger
from utils.config import image_path
from core.translations import TranslationCache, create_translator, fallback_notice_key
from core import argos
from core.translation_controller import TranslationController
from core.settings_manager import SettingsManager
from core.localization import UiLocalizer
from core.audio_playback import AudioPlaybackToggle
from core.capture import capture_full_screen_qimage, warm_up
from ui.components import SelectionWindow, WindowDragFilter, SecondaryOverlay, OverlayPanel
from ui.settings_dialog import SettingsDialog
from ui.history_window import HistoryWindow
from ui.dialogs import show_about, show_help, show_tesseract_missing, show_update_result
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
        # Не се вижда никъде другаде (прозорецът е frameless, без заглавна
        # лента), но е важно за taskbar-а/Alt-Tab - особено сега, след
        # добавянето на "минимизирай" (showMinimized()).
        self.setWindowTitle("Overlingo")
        self._tesseract_found = configure_tesseract() is not None

        self.i18n = UiLocalizer()
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()

        self._load_settings_into_fields(self.settings)

        self.stats = SessionStats()  # показва се в прозореца с историята
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

        self.audio = AudioPlaybackToggle(
            set_icon=self._set_play_button_icon, on_no_internet=self._on_audio_no_internet
        )
        self._refresh_in_progress = False
        self.selection_rect = None
        self.selection_window = None
        self.translation_overlay = None

        self.history = TranslationHistory()
        self.history_window = None   # създават се при първото отваряне
        self._update_thread = None   # проверка за нова версия (менюто "?")
        self.text_window = None

        self.setup_ui()
        self.setup_connections()

        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(self.refresh_interval_ms)
        self.refresh_timer.timeout.connect(self.translate_selection)

        # Глобален hotkey - Windows и Linux/X11 (виж core/hotkey_manager.py
        # за причините Wayland/macOS да останат изключени засега).
        self.hotkey_manager = HotkeyManager(self)
        self.hotkey_manager.triggered.connect(self._on_hotkey_triggered)
        self.hotkey_manager.failed.connect(self._on_hotkey_failed)
        self._reconfigure_hotkey()

        # "Загрява" mss във фонова нишка - иначе първото реално маркиране
        # (start_selection, синхронно в главната нишка) замръзва за 1-2s
        # заради еднократната инициализация на mss (виж core/capture.py).
        threading.Thread(target=warm_up, daemon=True).start()

        # Отложено (не веднага) - за да се появи диалогът СЛЕД като главният
        # прозорец вече се вижда, не преди/по средата на construct-ването му.
        QtCore.QTimer.singleShot(300, self._show_tesseract_missing_warning)

    def _load_settings_into_fields(self, settings):
        """Разопакова речника с настройки в атрибути на прозореца."""
        self.text_size = settings["text_size"]
        self.font_color = settings["font_color"]
        self.overlay_opacity = settings["overlay_opacity"]
        self.translation_api = settings["translation_api"]
        self.translation_api_key = settings["translation_api_key"]
        self.audio_lang = settings["audio_lang"]
        self.audio_speed = settings["audio_speed"]
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
        """Пресъздава преводача според текущите настройки и го подава на контролера."""
        translator = create_translator(
            self.translation_api, self.translation_api_key,
            source_lang=argos.source_language(self.ocr_lang),
        )
        self.translation_controller.configure(translator, self.ocr_lang, self.target_lang)

    # ------------------------------------------------------------------
    # UI подредба
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Настройка на потребителския интерфейс"""
        base_flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        self.fullscreen_detector.apply_window_flags(self, base_flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.i18n.set_language(self.settings.get("interface_language", "en"))

        screen = QtWidgets.QApplication.primaryScreen().geometry()
        window_width, window_height = 800, 200
        self._full_window_height = window_height
        self._toolbar_only_height = 55  # само лентата с бутони, без overlay панела
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
        Заоблен полупрозрачен фон за лентата с бутони - и същевременно
        зоната, върху която можеш да задържиш и местиш цялата програма
        (виж WindowDragFilter). Бутоните се създават след това и лягат
        отгоре й (bg_widget.lower()), така че кликовете върху тях си
        работят нормално - местенето хваща само празното пространство.
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
        """Свързва сигналите със слотовете"""
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
        Спинърът стои в бутона "Маркирай и преведи", на малко разстояние
        след текста (не залепен за ръба - текстът е центриран и тогава
        почти го докосваше). Вика се и при смяна на езика, защото
        дължината на текста е различна.
        """
        icon_size = 22
        gap_after_text = 10
        btn = self.mark_translate_btn
        btn_geo = btn.geometry()
        btn.ensurePolished()  # размерът на шрифта идва от theme.qss
        text_width = QtGui.QFontMetrics(btn.font()).horizontalAdvance(btn.text())
        text_right = btn_geo.center().x() + text_width // 2
        x = min(text_right + gap_after_text, btn_geo.right() - icon_size - 2)
        y = btn_geo.top() + (btn_geo.height() - icon_size) // 2
        self.translation_status.setGeometry(x, y, icon_size, icon_size)
        self.translation_status.raise_()

    def setup_buttons(self):
        """
        Създава и позиционира бутоните. Лявата страна е в три групи с малко
        по-голямо разстояние между тях:
          превод от екрана:  [Маркирай и преведи] [⟳] [Изчисти] [▶]
          други начини:      [Aa] [история]
          изглед:            [око]
        Вдясно: [?] (помощ / за програмата), настройки, минимизиране, изход.
        """
        y, h = 10, 30
        gap, group_gap = 15, 30
        x = self.bg_widget.x() + 5

        # --- превод от екрана ---
        self.mark_translate_btn = QtWidgets.QPushButton(self)
        self.mark_translate_btn.setObjectName("primary_btn")
        self.mark_translate_btn.setGeometry(x, y, 230, h)  # място и за спинъра след текста
        x += 230 + gap

        self.retranslate_btn = self._make_icon_button(
            "retranslate_button_white.png", x, object_name="secondary_icon_btn"
        )
        self.retranslate_btn.setEnabled(False)  # докато няма маркирана област
        x += h + gap

        self.clear_btn = QtWidgets.QPushButton(self)
        self.clear_btn.setObjectName("secondary_btn")
        self.clear_btn.setGeometry(x, y, 90, h)
        x += 90 + gap

        self.play_btn = self._make_icon_button(
            "play_button_white.png", x, width=40, object_name="secondary_icon_btn"
        )
        self.play_btn.setEnabled(False)  # активен едва когато има превод за прочитане
        x += 40 + group_gap

        # --- други начини за превод ---
        self.text_translate_btn = self._make_icon_button(
            "text_translate_button_white.png", x, object_name="secondary_icon_btn"
        )
        x += h + gap
        self.history_btn = self._make_icon_button(
            "history_button_white.png", x, object_name="secondary_icon_btn"
        )
        x += h + group_gap

        # --- изглед ---
        self.toggle_overlay_btn = self._make_icon_button(
            "show_button_white.png", x, object_name="secondary_icon_btn"
        )

        self.translation_status = QtWidgets.QLabel(self)
        self.translation_status.setAlignment(QtCore.Qt.AlignCenter)
        # Лежи върху бутона за превод - без това кликовете точно върху
        # спинъра не биха стигали до бутона отдолу.
        self.translation_status.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.translation_status.hide()  # вижда се само докато тече превод

        # Бяла версия на spinner.png - контрастира добре на синия бутон.
        self.status_icon = QtGui.QPixmap(image_path("spinner_white.png"))
        self.scaled_icon = self.status_icon.scaled(18, 18, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.translation_status.setPixmap(self.scaled_icon)

        self.animation = QtCore.QVariantAnimation(self)
        self.animation.setDuration(1000)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self.rotate_icon)

        # --- вдясно, отдясно наляво ---
        step = 35
        right_x = self.bg_widget.x() + self.bg_widget.width() - 35
        self.exit_btn = self._make_icon_button("close_button_white.png", right_x)
        right_x -= step
        self.minimize_btn = self._make_icon_button("minimize_button_white.png", right_x)
        right_x -= step
        self.settings_btn = self._make_icon_button("settings_button_white.png", right_x)
        right_x -= step

        # "Помощ" и "За програмата" са в едно меню - по-рядко се ползват,
        # а така освобождаваме място за новите бутони вляво.
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
        Помощна функция: замества повтарящия се код за създаване на иконен
        бутон 30x30. width (по-широк бутон) и object_name покриват и
        нестандартните случаи (напр. play_btn - по-широк, със сив бокс стил).
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
        # "Изчисти" е активен само когато има нещо за изчистване
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
        """Текстовете на лентата (при старт и при смяна на езика)."""
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
        """Подсказките на двата бутона за превод показват и hotkey-я, ако е включен."""
        hotkeys_on = HOTKEY_SUPPORTED and self.hotkey_enabled

        def with_hotkey(text, combo):
            return f"{text} ({format_combo(combo)})" if hotkeys_on and combo else text

        self.mark_translate_btn.setToolTip(
            with_hotkey(self.i18n.tr("mark_translate_tooltip"), self.hotkey_combo))
        self.retranslate_btn.setToolTip(
            with_hotkey(self.i18n.tr("retranslate_tooltip"), self.hotkey_retranslate_combo))

    def toggle_overlay_visibility(self):
        """Превключва видимостта на overlay панела (бутонът с окото)"""
        self._set_overlay_panel_visible(not self.overlay_panel.isVisible())

    def _set_overlay_panel_visible(self, visible):
        """
        Показва/скрива overlay панела И оразмерява самия прозорец.

        Панелът е дете на главния прозорец - само да го скрием (hide) не
        стига, защото прозорецът (frameless, always-on-top) пак заема
        пълната си височина и продължава да "лови" кликовете над
        програмите под него, дори когато нищо не се вижда там. Свиваме
        прозореца до височината само на лентата с бутони, когато панелът
        е скрит, и го връщаме, когато е показан.
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
        """Маркиране и превод наведнъж"""
        self.start_selection(callback=self.on_selection_complete_for_translate)

    def on_selection_complete_for_translate(self, rect):
        # Затваряме предишния overlay веднага - иначе стои с текста от
        # предния превод, докато чакаме новия OCR+превод (или, ако новата
        # област е другаде на екрана, изобщо не се мести натам).
        self._close_translation_overlay()
        self.save_selection(rect)
        QtCore.QTimer.singleShot(100, self.translate_selection)

    def _close_translation_overlay(self):
        """Затваря текущия overlay (ако има) веднага, а не чак след като новият превод е готов."""
        if self.translation_overlay:
            self.translation_overlay.close()

    def show_about(self):
        show_about(self, self.i18n)

    def show_help(self):
        show_help(self, self.i18n)

    def check_for_updates(self):
        """
        "Провери за нова версия" от менюто "?". Заявката към GitHub е във
        фонова нишка; докато тече, редът в менюто е неактивен, за да не се
        пуснат две проверки едновременно.
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
    # Настройки
    # ------------------------------------------------------------------

    def show_settings(self):
        """Показва диалога с настройки (виж ui/settings_dialog.py)"""
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
        """Реагира на плъзгача за прозрачност веднага, преди да е натиснат Запази."""
        self.overlay_panel.set_alpha(value)

    def _collect_current_settings(self):
        """Текущото състояние на прозореца, представено като dict (за SettingsDialog)."""
        return {
            "text_size": self.text_size,
            "font_color": self.font_color,
            "overlay_opacity": self.overlay_opacity,
            "translation_api": self.translation_api,
            "translation_api_key": self.translation_api_key,
            "audio_lang": self.audio_lang,
            "audio_speed": self.audio_speed,
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
        """Прилага вече валидирани настройки (извиква се от SettingsDialog.on_save)."""
        self._load_settings_into_fields(settings)
        # Отметката "Автоматичен превод" не е в диалога с настройки, но
        # "Възстанови по подразбиране" трябва да я върне и нея.
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
        """Запазва текущите настройки във файл чрез SettingsManager."""
        self.settings.update(self._collect_current_settings())
        self.settings["window_pos"] = [self.x(), self.y()]
        self.settings["interface_language"] = self.i18n.current_lang
        self.settings_manager.save(self.settings)

    def apply_overlay_visibility(self):
        self._set_overlay_panel_visible(not self.hide_overlay_enabled)

    # ------------------------------------------------------------------
    # Маркиране на област
    # ------------------------------------------------------------------

    def start_selection(self, callback):
        """Стартира процеса на маркиране на област от екрана."""
        if self.selection_window and self.selection_window.isVisible():
            return  # вече се маркира (напр. hotkey-ят е натиснат два пъти)
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
    # Аудио
    # ------------------------------------------------------------------

    def _set_play_button_icon(self, icon_filename):
        # play_button.png/stop_button.png са черни - на плътния сив фон на
        # play бутона (secondary_icon_btn) искаме бялата версия, за да
        # пасва на останалите икони в лентата.
        white_filename = icon_filename.replace(".png", "_white.png")
        self.play_btn.setIcon(QtGui.QIcon(image_path(white_filename)))

    def _set_current_translation(self, text):
        """Запомня последния превод и активира/деактивира play бутона спрямо него."""
        self._current_translated_text = text or None
        self.play_btn.setEnabled(bool(self._current_translated_text))

    def _on_audio_no_internet(self):
        """edge-tts е онлайн услуга - без връзка озвучаването не може да проработи."""
        self.text_display.append(f"❌ {self.i18n.tr('audio_requires_internet')}\n")

    def start_play(self):
        if not self.audio_lang:
            self.text_display.append(f"{self.i18n.tr('no_audio_lang')}")
            return
        self.audio.toggle(self._current_translated_text, self.audio_lang, self.audio_speed)

    # ------------------------------------------------------------------
    # Превод (делегирано на TranslationController - виж core/translation_controller.py)
    # ------------------------------------------------------------------

    def translate_selection(self):
        """Стартира превод на маркираната област."""
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
                # .hide() само маркира прозореца за скриване - реалното
                # изчезване от екрана (прозоречният мениджър/compositor-ът)
                # отнема частица от секундата. processEvents() разчиства
                # само Qt-вата опашка, но не гарантира, че compositor-ът
                # реално е дорисувал екрана без overlay-я - затова и кратко
                # (неблокиращо, през event loop-а) изчакване след него,
                # преди screenshot-ът да бъде направен.
                QtWidgets.QApplication.processEvents()
                QtCore.QTimer.singleShot(80, self._capture_and_translate)
                return

        self._capture_and_translate()

    def _capture_and_translate(self):
        # Размерът на шрифта трябва само за нов overlay - при авто-рефреш и
        # "Преведи отново" върху вече отворен overlay второто OCR минаване
        # би било излишно.
        detect_font_size = (
            self.preserve_font_size and self.overlay_translation_enabled and self.translation_overlay is None
        )
        self.translation_controller.translate_region(self.selection_rect, detect_font_size=detect_font_size)

    def _reshow_overlay_if_pending(self):
        """
        Показва обратно overlay-я, ако сме го скрили за текущия цикъл.
        Извиква се веднага след screenshot-а (capture_finished) и при
        грешка/timeout - никога не се чака целият OCR+превод да завърши,
        за да не виси overlay-ят скрит с секунди без нужда.
        """
        if self._overlay_pending_reshow and self.translation_overlay:
            self.translation_overlay.show()
        self._overlay_pending_reshow = False

    def _on_capture_finished(self):
        """Screenshot-ът е готов - overlay-ят вече може да се покаже обратно, без да чакаме превода."""
        self._reshow_overlay_if_pending()

    def _on_translation_failed(self, error_key, detail, source_text):
        self._refresh_in_progress = False
        self.set_translation_status(False)
        if source_text:
            self.text_display.append(self.i18n.tr("detected_text"))
            self.text_display.append(source_text)
        message = f"❌ {self.i18n.tr(error_key)}"
        self.text_display.append(f"{message}: {detail}\n" if detail else f"{message}\n")
        if error_key == "translation_timeout":
            # Отделен видим pop-up само за timeout - за разлика от
            # останалите грешки, тук потребителят вероятно иска да знае
            # веднага (не само ред в текстовия панел), защото решението
            # обикновено е "увеличи timeout-а в Settings", не просто "пробвай пак".
            QtWidgets.QMessageBox.warning(
                self, self.i18n.tr("warning_title"), self.i18n.tr("translation_timeout")
            )
        self._reshow_overlay_if_pending()

    def _on_translation_finished(self, source_text, translated_text, from_cache, fallback_used,
                                  font_size, rect):
        """Обработва завършването на превода (сигнал от TranslationController)."""
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
        # font_size е измерен във фоновата нишка (виж _capture_and_translate);
        # 0 - не е мерен (размерът на шрифта не се пази, или overlay-ят вече е отворен).
        overlay_font_size = font_size or self.text_size

        if self.translation_overlay is None:
            self.translation_overlay = SecondaryOverlay(
                translated_text,
                QtCore.QRect(rect.left(), rect.top(), rect.width(), rect.height()),
                font_size=overlay_font_size,
                font_color=self.font_color,
                background_opacity=self.overlay_opacity,
                audio_lang=self.audio_lang,
                audio_speed=self.audio_speed,
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
        # НЕ викаме self.show() тук - ако потребителят сам е минимизирал
        # главния прозорец (или overlay-ят се появи, докато той вече беше
        # минимизиран), затварянето на overlay-я не бива насила да го
        # възстановява. Минимизирано състояние се сменя само ръчно.

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
        self.audio.stop()  # няма какво да се чете повече
        self._set_current_translation(None)
        self.text_display.clear()
        self.refresh_timer.stop()
        self.translation_cache.clear()
        self._close_translation_overlay()  # ако има активен overlay - "Изчистване" значи всичко
        self._update_clear_button()

    def _update_clear_button(self):
        """Активен, ако има текст в панела, маркирана област или отворен overlay."""
        has_something = bool(
            self.text_display.toPlainText().strip()
            or self.selection_rect
            or self.translation_overlay
        )
        self.clear_btn.setEnabled(has_something)

    # ------------------------------------------------------------------
    # Глобален hotkey (Windows и Linux/X11)
    # ------------------------------------------------------------------

    def _minimize_window(self):
        """Обикновено минимизиране в taskbar-а - вика се от minimize_btn."""
        self.showMinimized()

    def _restore_window(self):
        """Връща прозореца от минимизирано състояние (taskbar) - вика се от hotkey-я."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def bring_to_front(self):
        """Второ стартиране на програмата показва вече отворената (виж core/single_instance.py)."""
        self._restore_window()

    def _reconfigure_hotkey(self):
        """Пуска/спира глобалните hotkey-и според текущите настройки (Windows/Linux X11)."""
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
        Показваме прозореца обратно САМО ако overlay display е изключен -
        иначе резултатът и без друго излиза директно върху текста
        (SecondaryOverlay), а не в самия прозорец - връщането му тук би
        добавило само ненужно мигване.
        """
        if not self.overlay_translation_enabled:
            self._restore_window()
        if action == ACTION_RETRANSLATE:
            self.translate_selection()
        else:
            self.mark_and_translate()

    def _on_hotkey_failed(self, error):
        """
        Видимо съобщение, а не само запис в лога - иначе hotkey-ят просто
        "не работи" без обяснение. Отложено, защото може да дойде още
        докато прозорецът се създава.
        """
        logger.warning(f"Hotkey не можа да се активира: {error}")
        QtCore.QTimer.singleShot(0, lambda: QtWidgets.QMessageBox.warning(
            self, self.i18n.tr("warning_title"), f"{self.i18n.tr('hotkey_failed')}\n\n{error}"
        ))

    # ------------------------------------------------------------------
    # История и превод на текст
    # ------------------------------------------------------------------

    def _add_to_history(self, source, translation):
        self.history.add(source, translation)
        if self.history_window and self.history_window.isVisible():
            self.history_window.refresh()

    def _on_text_translated(self, source, translation, from_cache):
        """Превод от прозореца "Превод на текст" - брои се и влиза в историята."""
        self.stats.record(from_cache)
        self._add_to_history(source, translation)

    def _audio_settings(self):
        return self.audio_lang, self.audio_speed

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
        """"Покажи" от историята - преводът излиза в текстовия панел на лентата."""
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
    # Стартиране / затваряне
    # ------------------------------------------------------------------

    def set_window_icon(self):
        """Автоматично зарежда правилната икона за всяка OS"""
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
                logger.info(f"{platform_name} икона заредена: {icon_path}")
            else:
                logger.warning(f"{platform_name} икона не е намерена: {icon_path}")
        except Exception as e:
            logger.error(f"Грешка при зареждане на икона: {e}", exc_info=True)

    def _show_tesseract_missing_warning(self):
        """
        Видим диалог (не само лог) - иначе потребителят просто вижда, че
        OCR-ът "не работи", без ясна причина. Отложено от __init__, за да
        се появи след като главният прозорец вече се вижда.
        """
        if not self._tesseract_found:
            self._tesseract_found = show_tesseract_missing(self, self.i18n)

    def closeEvent(self, event):
        # Прозорецът за текст пръв - при скриване записва размера си в
        # self.settings, който се запазва на следващия ред.
        if self.text_window:
            self.text_window.close()
            self.text_window.wait_for_threads()
        if self.history_window:
            self.history_window.close()
        if self._update_thread:
            self._update_thread.wait(3000)  # нишка, унищожена докато работи, срива Qt при изход
        self.save_settings_to_file()
        self.hotkey_manager.stop()
        self._close_translation_overlay()  # иначе остава "осиротял" на екрана след затваряне
        super().closeEvent(event)
