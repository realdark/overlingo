"""
UI COMPONENTS
"""

from utils.imports import QtWidgets, QtCore, QtGui
from utils.config import image_path
from core.audio_playback import AudioPlaybackToggle
from core.fullscreen_detector import FullscreenDetector

def _show_audio_notice(parent, i18n, key):
    """
    Messages from the playback (see AudioPlaybackToggle): no voice / no internet
    as a warning; "reading with the online voice" only as information.
    """
    show = QtWidgets.QMessageBox.information if key == "tts_fallback_online" else QtWidgets.QMessageBox.warning
    show(parent, i18n.tr("warning_title"), i18n.tr(key))


class OverlayPanel(QtWidgets.QWidget):
    """Panel with a semi-transparent background and rounded corners for the main window."""

    RADIUS = 8

    def __init__(self, alpha=200, parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor(0, 0, 0)
        self.set_alpha(alpha)

    def set_alpha(self, a: int):
        """Sets the opacity level (0-255)."""
        self._color.setAlpha(max(0, min(255, int(a))))
        self.update()

    def paintEvent(self, e):
        """Paints a semi-transparent background with rounded corners."""
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(self.rect(), self.RADIUS, self.RADIUS)

class SelectionWindow(QtWidgets.QWidget):
    # Escape or right click closes the window without a signal - nothing is translated.
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
        # Without focus Escape never reaches the window - especially when selection
        # is started via hotkey while another application is active.
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
        """Short hint at the top center ("... · Esc to cancel") until selection starts."""
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
    Event filter (not a QWidget subclass - deliberately, so we don't risk
    changing how the target widget is painted/styled) - attached to the empty
    button toolbar, it lets you press-and-drag the whole app. Replaces the
    separate "move" button: you no longer have to aim at a specific icon,
    just grab anywhere on the empty space of the toolbar. Buttons
    lying on top (higher z-order) are handled first by Qt and
    consume their own clicks - the filter only sees events in
    places not covered by another widget.
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
        return False  # never swallow the event - let Qt carry on as normal

class SecondaryOverlay(QtWidgets.QFrame):
    closed = QtCore.pyqtSignal()

    def __init__(self, text, rect, i18n, get_audio_settings, font_size=14, font_color="#FFFFFF", background_opacity=200):
        super().__init__()

        # callback() -> AudioOptions from the current settings (they may change while the overlay is open)
        self._get_audio_settings = get_audio_settings
        self.i18n = i18n
        self._current_translated_text = text  # for "Copy" and "Read aloud"; updated in setText()
        self._audio = AudioPlaybackToggle(set_icon=self._set_play_button_icon, on_notice=self._on_audio_notice)
        self.original_rect = rect

        # Store the parameters for setup_ui
        self._font_size = font_size
        self._font_color = font_color
        self._background_opacity = background_opacity
        self._text = text

        # Initialize the detector
        self.fullscreen_detector = FullscreenDetector(self)

        self.setup_ui()  # ⬅️ MOVED INTO A SEPARATE METHOD
        self.setup_buttons()
        self.setup_connections()

    def setup_ui(self):
        """UI setup - a separate method, like in MainWindow"""
        base_flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        self.fullscreen_detector.apply_window_flags(self, base_flags)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        # Keep the original rect
        self.setGeometry(self.original_rect)

        self.setFrameStyle(QtWidgets.QFrame.Box)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, {self._background_opacity});
                border-radius: 8px;
                border: none;
            }}
        """)

        # ✅ Create a separate container for the text
        self.text_container = QtWidgets.QWidget(self)
        self.text_container.setGeometry(0, 0, self.original_rect.width(), self.original_rect.height())

        text_layout = QtWidgets.QVBoxLayout(self.text_container)
        text_layout.setContentsMargins(10, 10, 10, 10)

        self.text_label = QtWidgets.QLabel(self._text)  # Empty text, set later
        self.text_label.setWordWrap(True)
        # By default QLabel does NOT allow selecting/copying the text -
        # without this, the translation in the overlay is visible but cannot be copied
        # (unlike text_display in the main window, which is a QTextEdit
        # and supports copy by default).
        self.text_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.text_label.setStyleSheet(f"color: {self._font_color}; font-size:{self._font_size}px; padding:5px 10px 5px 10px;")
        text_layout.addWidget(self.text_label)

    def _make_action_button(self, icon_file, base_rgb, hover_rgb):
        """Helper: play_btn and close_btn differ only by icon and color."""
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

        # ✅ Automatic sizing
        self.adjust_size()
        self.show()

    def setup_connections(self):
        """Connection setup - a separate method"""
        self.close_btn.clicked.connect(self.close)
        self.play_btn.clicked.connect(self.toggle_audio)
        self.copy_btn.clicked.connect(self.copy_text)

    def adjust_size(self):
        """Automatically sizes the window to fit the content"""
        # Height needed for the text at the given width
        text_width = self.original_rect.width() - 20  # Subtract padding
        text_height = self.text_label.heightForWidth(text_width) - 20  # Add a little padding


        # ✅ FIXED: Minimum and maximum height
        min_height = 100  # Minimum height
        buttons_height = 50
        margins = 30

        required_height = text_height + buttons_height + margins
        required_height = max(min_height, required_height)  # No less than min_height

        # Maximum height (60% of the screen, instead of 80%)
        screen_height = QtWidgets.QApplication.primaryScreen().geometry().height()
        max_height = int(screen_height * 0.6)

        # Final height
        final_height = min(required_height, max_height)

        # ✅ Resize the whole window
        self.setGeometry(
            self.original_rect.x(),
            self.original_rect.y(),
            self.original_rect.width(),
            final_height
        )

        # ✅ Resize the text container
        # Add 10 to bring the container closer to the overlay
        self.text_container.setGeometry(0, 0, self.width(), final_height - buttons_height + 10)

        # ✅ Position the buttons at the BOTTOM
        self.copy_btn.move(self.width() - 135, final_height - 45)
        self.play_btn.move(self.width() - 90, final_height - 45)
        self.close_btn.move(self.width() - 45, final_height - 45)

    def setText(self, text):
        """Changes the text and automatically resizes the window"""
        self.text_label.setText(text)
        # Otherwise "Copy" and "Read aloud" in the overlay keep the first
        # translation after an auto-refresh or "Translate again".
        self._current_translated_text = text
        self.adjust_size()

    def _set_play_button_icon(self, icon_filename):
        self.play_btn.setIcon(QtGui.QIcon(image_path(icon_filename)))

    def toggle_audio(self):
        self._audio.toggle(self._current_translated_text, self._get_audio_settings())

    def copy_text(self):
        """Copies the current translation to the clipboard - easier than selecting it by hand on the floating overlay."""
        QtWidgets.QApplication.clipboard().setText(self._current_translated_text)

    def _on_audio_notice(self, key):
        _show_audio_notice(self, self.i18n, key)

    def closeEvent(self, event):
        self.fullscreen_detector.stop()
        self._audio.stop()
        self.closed.emit()
        super().closeEvent(event)


class AudioButton(QtWidgets.QPushButton):
    """
    Play/stop button (icon only) for the history and text translation windows.
    get_text() returns the text to read, get_audio_settings() - AudioOptions
    from the current settings (they may change while the window is open).
    """

    def __init__(self, i18n, get_text, get_audio_settings, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._get_text = get_text
        self._get_audio_settings = get_audio_settings
        self._audio = AudioPlaybackToggle(set_icon=self._set_icon, on_notice=self._on_notice)
        self._set_icon("play_button.png")
        self.clicked.connect(self._toggle)

    def _set_icon(self, icon_filename):
        playing = icon_filename.startswith("stop")
        self.setIcon(QtGui.QIcon(image_path(icon_filename.replace(".png", "_white.png"))))
        # Icon only, like the play buttons in the toolbar and the overlay; the text is in the tooltip.
        self.setToolTip(self.i18n.tr("stop_audio" if playing else "read_aloud"))

    def _toggle(self):
        self._audio.toggle(self._get_text(), self._get_audio_settings())

    def stop(self):
        self._audio.stop()

    def update_text(self):
        """Updates the button for the UI language and whether audio is currently playing."""
        self._set_icon("stop_button.png" if self._audio.is_playing() else "play_button.png")

    def _on_notice(self, key):
        _show_audio_notice(self.window(), self.i18n, key)


class CopyButton(QtWidgets.QPushButton):
    """
    "Copy" button (icon only, like in the overlay). Copies get_text() to
    the clipboard and briefly shows "Copied ✓" as a tooltip next to the button.
    """

    def __init__(self, i18n, get_text, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._get_text = get_text
        self.setIcon(QtGui.QIcon(image_path("copy_button_white.png")))
        self.update_text()
        self.clicked.connect(self._copy)

    def update_text(self):
        """The tooltip, per the UI language."""
        self.setToolTip(self.i18n.tr("copy_button"))

    def _copy(self):
        text = self._get_text()
        if not text:
            return
        QtWidgets.QApplication.clipboard().setText(text)
        # With no label on the button, the confirmation appears as a tooltip next to it.
        QtWidgets.QToolTip.showText(
            self.mapToGlobal(QtCore.QPoint(0, self.height())), self.i18n.tr("copied_feedback"), self
        )
