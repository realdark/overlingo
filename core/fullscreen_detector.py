"""
SHOWING ABOVE FULLSCREEN APPLICATIONS (Linux/X11 only)

Under X11 an "always on top" window does not stay above a fullscreen
application (game, video). If one is active, the window gets the
X11BypassWindowManagerHint flag and then becomes visible. Every second we
check whether something is fullscreen and change the flags if needed.

The check (xprop) is shared by all windows and cached for about a second -
the toolbar and the overlay don't each spawn their own processes. If xprop is
missing (e.g. under Wayland), it is not retried and we assume there is no
fullscreen app. (A fallback check via Qt is pointless: QApplication only sees
our own windows, i.e. it would only "detect" the selection window.)
"""

import subprocess
import time

from utils.imports import sys, QtCore
from utils.logging_setup import logger

IS_LINUX = sys.platform.startswith("linux")
CHECK_INTERVAL_MS = 1000
_CACHE_SECONDS = 0.9


class FullscreenDetector(QtCore.QObject):
    """Watches for a fullscreen application and changes the parent window's flags."""

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
        Stops the check. MUST be called when the parent window closes -
        otherwise the timer keeps running on a hidden window.
        """
        if self.update_timer:
            self.update_timer.stop()

    # ------------------------------------------------------------------

    @classmethod
    def is_fullscreen_application_active(cls):
        """Whether a fullscreen window is active. The result is cached ~1 s for all windows."""
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
            logger.info("xprop is missing - showing above fullscreen applications is disabled.")
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
        """Sets the window's initial flags (called when it is created)."""
        window.setWindowFlags(self._desired_flags(base_flags))

    def _auto_update_check(self):
        """Every second: changes the flags only if the "fullscreen" status has changed."""
        window = self.parent()
        if window is None:
            return
        # A hidden or minimized window is left alone - show() below would
        # force it visible (e.g. the overlay, hidden while the screenshot is
        # taken, or the toolbar, minimized by the user).
        if not window.isVisible() or window.isMinimized():
            return
        try:
            current = window.windowFlags()
            desired = self._desired_flags(current & ~QtCore.Qt.X11BypassWindowManagerHint)
            if desired != current:
                window.setWindowFlags(desired)
                window.show()  # setWindowFlags hides the window
        except Exception as e:
            logger.error(f"Auto-update error: {e}", exc_info=True)
