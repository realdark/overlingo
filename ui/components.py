"""
UI КОМПОНЕНТИ
"""

from utils.imports import QtWidgets, QtCore, QtGui
from utils.config import image_path
from core.audio_playback import AudioPlaybackToggle
from core.fullscreen_detector import FullscreenDetector

def _warn_audio_needs_internet(parent, i18n):
    """edge-tts е онлайн услуга - без връзка озвучаването не може да проработи."""
    QtWidgets.QMessageBox.warning(parent, i18n.tr("warning_title"), i18n.tr("audio_requires_internet"))


class OverlayPanel(QtWidgets.QWidget):
    """Панел с полупрозрачен фон и заоблени ъгли за основния прозорец."""

    RADIUS = 8

    def __init__(self, alpha=200, parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor(0, 0, 0)
        self.set_alpha(alpha)

    def set_alpha(self, a: int):
        """Задава ниво на прозрачност (0-255)."""
        self._color.setAlpha(max(0, min(255, int(a))))
        self.update()

    def paintEvent(self, e):
        """Рисува полупрозрачен фон със заоблени ъгли."""
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(self.rect(), self.RADIUS, self.RADIUS)

class SelectionWindow(QtWidgets.QWidget):
    # Escape или десен бутон затварят прозореца без сигнал - нищо не се превежда.
    selection_made = QtCore.pyqtSignal(QtCore.QRect)

    def __init__(self, screenshot, hint_text=""):
        super().__init__()
        self.screenshot = screenshot
        self.hint_text = hint_text
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setWindowState(self.windowState() | QtCore.Qt.WindowFullScreen)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()
        self.selecting = False

    def showEvent(self, event):
        super().showEvent(event)
        # Без фокус Escape не стига до прозореца - особено когато маркирането
        # е пуснато с hotkey, докато друго приложение е активно.
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _cancel(self):
        self.selecting = False
        self.close()

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        qp.drawImage(0, 0, self.screenshot)
        if self.selecting:
            qp.setPen(QtGui.QPen(QtGui.QColor(0, 255, 0), 2))
            qp.setBrush(QtGui.QColor(0, 255, 0, 50))
            qp.drawRect(QtCore.QRect(self.begin, self.end).normalized())
        elif self.hint_text:
            self._draw_hint(qp)

    def _draw_hint(self, qp):
        """Кратка подсказка горе в средата ("... · Esc за отказ"), докато още не се маркира."""
        font = qp.font()
        font.setPointSize(11)
        font.setBold(True)
        qp.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        box = metrics.boundingRect(self.hint_text).adjusted(-14, -8, 14, 8)
        box.moveCenter(QtCore.QPoint(self.width() // 2, 40))
        qp.setPen(QtCore.Qt.NoPen)
        qp.setBrush(QtGui.QColor(0, 0, 0, 170))
        qp.drawRoundedRect(box, 8, 8)
        qp.setPen(QtGui.QColor(255, 255, 255))
        qp.drawText(box, QtCore.Qt.AlignCenter, self.hint_text)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self._cancel()
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.begin = event.pos()
            self.end = self.begin
            self.selecting = True
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.selecting:
            self.end = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.selecting:
            rect = QtCore.QRect(self.begin, self.end).normalized()
            self.selection_made.emit(rect)
            self.close()
        super().mouseReleaseEvent(event)

class WindowDragFilter(QtCore.QObject):
    """
    Event filter (не subclass на QWidget - нарочно, за да не рискуваме да
    променим как се рисува/стилизира целевия widget) - закачен за празната
    лента с бутони, позволява задръж-и-мести на цялата програма. Заменя
    отделния "move" бутон: вече не трябва да се цели в конкретна икона,
    просто хващаш някъде по празното пространство на лентата. Бутоните,
    които лежат отгоре (по-висок z-order), се обработват първи от Qt и
    консумират собствените си кликове - filter-ът вижда само събития по
    местата, върху които няма друг widget.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._drag_offset = None

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            self._drag_offset = event.globalPos() - watched.window().frameGeometry().topLeft()
        elif event.type() == QtCore.QEvent.MouseMove and self._drag_offset is not None:
            if event.buttons() & QtCore.Qt.LeftButton:
                watched.window().move(event.globalPos() - self._drag_offset)
        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            self._drag_offset = None
        return False  # никога не поглъщаме събитието - оставяме Qt да си продължи нормално

class SecondaryOverlay(QtWidgets.QFrame):
    closed = QtCore.pyqtSignal()

    def __init__(self, text, rect, i18n, font_size=14, font_color="#FFFFFF", background_opacity=200, audio_lang="", audio_speed=1.0):
        super().__init__()

        self.audio_lang = audio_lang
        self.audio_speed = audio_speed
        self.i18n = i18n
        self._current_translated_text = text  # за "Копирай" и "Чети на глас"; сменя се в setText()
        self._audio = AudioPlaybackToggle(
            set_icon=self._set_play_button_icon, on_no_internet=self._on_audio_no_internet
        )
        self.original_rect = rect

        # Запази параметрите за setup_ui
        self._font_size = font_size
        self._font_color = font_color
        self._background_opacity = background_opacity
        self._text = text

        # Инициализация на детектора
        self.fullscreen_detector = FullscreenDetector(self)

        self.setup_ui()  # ⬅️ ИЗВАДЕН В ОТДЕЛЕН МЕТОД
        self.setup_buttons()
        self.setup_connections()

    def setup_ui(self):
        """Настройка на UI - отделен метод като в MainWindow"""
        base_flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        self.fullscreen_detector.apply_window_flags(self, base_flags)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        # Запазваме оригиналния rect
        self.setGeometry(self.original_rect)

        self.setFrameStyle(QtWidgets.QFrame.Box)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, {self._background_opacity});
                border-radius: 8px;
                border: none;
            }}
        """)

        # ✅ Създаваме отделен контейнер за текста
        self.text_container = QtWidgets.QWidget(self)
        self.text_container.setGeometry(0, 0, self.original_rect.width(), self.original_rect.height())

        text_layout = QtWidgets.QVBoxLayout(self.text_container)
        text_layout.setContentsMargins(10, 10, 10, 10)

        self.text_label = QtWidgets.QLabel(self._text)  # Празен текст, ще се сетне после
        self.text_label.setWordWrap(True)
        # По подразбиране QLabel НЕ позволява маркиране/копиране на текста -
        # без това, преводът в overlay-я се вижда, но не може да се копира
        # (за разлика от text_display в главния прозорец, който е QTextEdit
        # и поддържа copy по подразбиране).
        self.text_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.text_label.setStyleSheet(f"color: {self._font_color}; font-size:{self._font_size}px; padding:5px 10px 5px 10px;")
        text_layout.addWidget(self.text_label)

    def _make_action_button(self, icon_file, base_rgb, hover_rgb):
        """Помощен метод: play_btn и close_btn се различават само по икона и цвят."""
        btn = QtWidgets.QToolButton(self)
        btn.setFixedSize(35, 35)
        btn.setIcon(QtGui.QIcon(image_path(icon_file)))
        btn.setIconSize(QtCore.QSize(30, 30))
        btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        btn.setStyleSheet(f"""
            QToolButton {{
                color: white;
                background-color: rgba{base_rgb};
                border: none;
                font-weight: bold;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: rgba{hover_rgb};
            }}
        """)
        return btn

    def setup_buttons(self):
        self.copy_btn = self._make_action_button(
            "copy_button_white.png", (90, 90, 90, 230), (120, 120, 120, 255)
        )
        self.play_btn = self._make_action_button(
            "play_button.png", (0, 150, 255, 230), (0, 200, 255, 255)
        )
        self.close_btn = self._make_action_button(
            "close_button.png", (255, 0, 0, 230), (255, 50, 50, 255)
        )

        # ✅ Автоматично оразмеряване
        self.adjust_size()
        self.show()

    def setup_connections(self):
        """Настройка на връзките - отделен метод"""
        self.close_btn.clicked.connect(self.close)
        self.play_btn.clicked.connect(self.toggle_audio)
        self.copy_btn.clicked.connect(self.copy_text)

    def adjust_size(self):
        """Автоматично оразмерява прозореца според съдържанието"""
        # Необходимата височина за текста при дадената ширина
        text_width = self.original_rect.width() - 20  # Вадим padding
        text_height = self.text_label.heightForWidth(text_width) - 20  # Добавяме малко padding


        # ✅ ПОПРАВЕНО: Минимална и максимална височина
        min_height = 100  # Минимална височина
        buttons_height = 50
        margins = 30

        required_height = text_height + buttons_height + margins
        required_height = max(min_height, required_height)  # Не по-малко от min_height

        # Максимална височина (60% от екрана, вместо 80%)
        screen_height = QtWidgets.QApplication.primaryScreen().geometry().height()
        max_height = int(screen_height * 0.6)

        # Финална височина
        final_height = min(required_height, max_height)

        # ✅ Оразмеряваме целия прозорец
        self.setGeometry(
            self.original_rect.x(),
            self.original_rect.y(),
            self.original_rect.width(),
            final_height
        )

        # ✅ Оразмеряваме текстовия контейнер
        # Добавяме 10 за да доближм контейнера до overlay
        self.text_container.setGeometry(0, 0, self.width(), final_height - buttons_height + 10)

        # ✅ Позиционираме бутоните ОТДОЛУ
        self.copy_btn.move(self.width() - 135, final_height - 45)
        self.play_btn.move(self.width() - 90, final_height - 45)
        self.close_btn.move(self.width() - 45, final_height - 45)

    def setText(self, text):
        """Променя текста и автоматично оразмерява прозореца"""
        self.text_label.setText(text)
        # Иначе "Копирай" и "Чети на глас" в overlay-я остават с първия
        # превод след авто-рефреш или "Преведи отново".
        self._current_translated_text = text
        self.adjust_size()

    def _set_play_button_icon(self, icon_filename):
        self.play_btn.setIcon(QtGui.QIcon(image_path(icon_filename)))

    def toggle_audio(self):
        self._audio.toggle(self._current_translated_text, self.audio_lang, self.audio_speed)

    def copy_text(self):
        """Копира текущия превод в клипборда - по-удобно от ръчно маркиране върху плаващия overlay."""
        QtWidgets.QApplication.clipboard().setText(self._current_translated_text)

    def _on_audio_no_internet(self):
        _warn_audio_needs_internet(self, self.i18n)

    def closeEvent(self, event):
        self.fullscreen_detector.stop()
        self._audio.stop()
        self.closed.emit()
        super().closeEvent(event)


class AudioButton(QtWidgets.QPushButton):
    """
    Бутон play/stop (само икона) за прозорците с история и превод на текст.
    get_text() връща текста за четене, get_audio_settings() - (глас, скорост)
    от текущите настройки (могат да се сменят, докато прозорецът е отворен).
    """

    def __init__(self, i18n, get_text, get_audio_settings, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._get_text = get_text
        self._get_audio_settings = get_audio_settings
        self._audio = AudioPlaybackToggle(set_icon=self._set_icon, on_no_internet=self._on_no_internet)
        self._set_icon("play_button.png")
        self.clicked.connect(self._toggle)

    def _set_icon(self, icon_filename):
        playing = icon_filename.startswith("stop")
        self.setIcon(QtGui.QIcon(image_path(icon_filename.replace(".png", "_white.png"))))
        # Само икона, както play бутоните в лентата и в overlay-я; текстът е в подсказката.
        self.setToolTip(self.i18n.tr("stop_audio" if playing else "read_aloud"))

    def _toggle(self):
        voice, speed = self._get_audio_settings()
        if not voice and not self._audio.is_playing():
            QtWidgets.QMessageBox.information(self.window(), self.i18n.tr("warning_title"), self.i18n.tr("no_audio_lang"))
            return
        self._audio.toggle(self._get_text(), voice, speed)

    def stop(self):
        self._audio.stop()

    def update_text(self):
        """Обновява надписа според езика на интерфейса и дали в момента се чете."""
        self._set_icon("stop_button.png" if self._audio.is_playing() else "play_button.png")

    def _on_no_internet(self):
        _warn_audio_needs_internet(self.window(), self.i18n)


class CopyButton(QtWidgets.QPushButton):
    """
    Бутон "копирай" (само икона, като в overlay-я). Копира get_text() в
    клипборда и за момент показва "Копирано ✓" като подсказка до бутона.
    """

    def __init__(self, i18n, get_text, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._get_text = get_text
        self.setIcon(QtGui.QIcon(image_path("copy_button_white.png")))
        self.update_text()
        self.clicked.connect(self._copy)

    def update_text(self):
        """Подсказката според езика на интерфейса."""
        self.setToolTip(self.i18n.tr("copy_button"))

    def _copy(self):
        text = self._get_text()
        if not text:
            return
        QtWidgets.QApplication.clipboard().setText(text)
        # Без надпис на бутона потвърждението излиза като подсказка до него.
        QtWidgets.QToolTip.showText(
            self.mapToGlobal(QtCore.QPoint(0, self.height())), self.i18n.tr("copied_feedback"), self
        )
