"""
ПОКАЗВАНЕ НАД ПРИЛОЖЕНИЯ НА ЦЯЛ ЕКРАН (само Linux/X11)

Под X11 прозорец "винаги отгоре" не стои над приложение на цял екран
(игра, видео). Ако такова е активно, прозорецът получава флага
X11BypassWindowManagerHint и тогава се вижда. На всяка секунда се
проверява дали нещо е на цял екран и флаговете се сменят при нужда.

Проверката (xprop) е обща за всички прозорци и се пази за около секунда -
лентата и overlay-ят не пускат всеки свои процеси. Ако xprop липсва
(напр. под Wayland), повече не се опитва и се приема, че няма приложение на
цял екран. (Резервна проверка през Qt няма смисъл: QApplication вижда само
собствените ни прозорци, т.е. би "засякла" само прозореца за маркиране.)
"""

import subprocess
import time

from utils.imports import sys, QtCore
from utils.logging_setup import logger

IS_LINUX = sys.platform.startswith("linux")
CHECK_INTERVAL_MS = 1000
_CACHE_SECONDS = 0.9


class FullscreenDetector(QtCore.QObject):
    """Следи дали има приложение на цял екран и сменя флаговете на прозореца-родител."""

    _cached_active = False
    _cached_at = 0.0
    _xprop_available = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.update_timer = None
        if IS_LINUX:
            self.update_timer = QtCore.QTimer(self)
            self.update_timer.timeout.connect(self._auto_update_check)
            self.update_timer.start(CHECK_INTERVAL_MS)

    def stop(self):
        """
        Спира проверката. ЗАДЪЛЖИТЕЛНО се вика, когато прозорецът-родител се
        затваря - иначе таймерът продължава върху скрит прозорец.
        """
        if self.update_timer:
            self.update_timer.stop()

    # ------------------------------------------------------------------

    @classmethod
    def is_fullscreen_application_active(cls):
        """Има ли активен прозорец на цял екран. Резултатът се пази ~1 s за всички прозорци."""
        if not IS_LINUX:
            return False
        now = time.monotonic()
        if now - cls._cached_at < _CACHE_SECONDS:
            return cls._cached_active
        cls._cached_active = cls._check_with_xprop() if cls._xprop_available else False
        cls._cached_at = now
        return cls._cached_active

    @classmethod
    def _check_with_xprop(cls):
        try:
            result = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                return False
            window_id = result.stdout.strip().split()[-1]
            if window_id == "0x0":
                return False
            result = subprocess.run(["xprop", "-id", window_id, "_NET_WM_STATE"],
                                    capture_output=True, text=True, timeout=2)
            return "_NET_WM_STATE_FULLSCREEN" in result.stdout
        except FileNotFoundError:
            logger.info("xprop липсва - показването над приложения на цял екран е изключено.")
            cls._xprop_available = False
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------

    def _desired_flags(self, base_flags):
        if self.is_fullscreen_application_active():
            return base_flags | QtCore.Qt.X11BypassWindowManagerHint
        return base_flags

    def apply_window_flags(self, window, base_flags):
        """Задава началните флагове на прозореца (вика се при създаването му)."""
        window.setWindowFlags(self._desired_flags(base_flags))

    def _auto_update_check(self):
        """На всяка секунда: сменя флаговете само ако статусът "цял екран" се е променил."""
        window = self.parent()
        if window is None:
            return
        # Скрит или минимизиран прозорец не се пипа - show() по-долу би го
        # показал насила (напр. overlay-я, скрит за момента на screenshot-а,
        # или лентата, минимизирана от потребителя).
        if not window.isVisible() or window.isMinimized():
            return
        try:
            current = window.windowFlags()
            desired = self._desired_flags(current & ~QtCore.Qt.X11BypassWindowManagerHint)
            if desired != current:
                window.setWindowFlags(desired)
                window.show()  # setWindowFlags скрива прозореца
        except Exception as e:
            logger.error(f"Auto-update error: {e}", exc_info=True)
