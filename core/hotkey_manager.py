"""
GLOBAL HOTKEY (Windows and Linux/X11)

Uses pynput.keyboard.GlobalHotKeys, which listens at the system level -
it works regardless of which window currently has focus. Supported on:
- Windows - pynput works reliably there without special permissions.
- Linux, ONLY under an X11 session - X11 lets ordinary applications
  listen to the keyboard globally (the same reason the FullscreenDetector's
  X11Bypass trick works there). Detected via XDG_SESSION_TYPE - unless
  it is explicitly "x11" (e.g. missing, or "wayland"), we assume it is
  NOT supported - it is safer to refuse than to guess wrong.
Not supported on:
- Linux/Wayland - the compositor deliberately blocks global keyboard
  listening by normal applications for security reasons; there is no
  client-side workaround analogous to X11Bypass.
- macOS - requires an explicit Accessibility permission and has extra
  restrictions (SecureEventInput) for certain kinds of content.

pynput calls the callback from its OWN thread, not from the Qt
main thread - that is why HotkeyManager is a QObject with a
pyqtSignal: emitting a signal from another thread is thread-safe
in Qt (it automatically becomes a queued connection), whereas
touching widgets directly from the pynput thread would be
dangerous (Qt widgets are not thread-safe).
"""

from utils.imports import QtCore, sys, os
from utils.logging_setup import logger

IS_WINDOWS = sys.platform == "win32"
IS_LINUX_X11 = sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"
HOTKEY_SUPPORTED = IS_WINDOWS or IS_LINUX_X11


# Actions that can have a hotkey.
ACTION_MARK_TRANSLATE = "mark_translate"
ACTION_RETRANSLATE = "retranslate"


def format_combo(combo):
    """
    pynput format -> readable text for hints: "<ctrl>+<alt>+t" -> "Ctrl+Alt+T".
    """
    if not combo:
        return ""
    parts = []
    for part in combo.split("+"):
        part = part.strip()
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            parts.append({"cmd": "Win", "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}.get(name, name.capitalize()))
        else:
            parts.append(part.upper())
    return "+".join(parts)


def combo_error(combo):
    """
    Returns the error text if the combination is not a valid pynput format,
    otherwise None. If pynput is missing we cannot check - returns None.
    """
    try:
        from pynput import keyboard
    except Exception:
        return None
    try:
        keyboard.HotKey.parse(combo)
        return None
    except Exception as e:
        return str(e) or repr(e)


class HotkeyManager(QtCore.QObject):
    # action (ACTION_*) whose hotkey was pressed
    triggered = QtCore.pyqtSignal(str)
    # error message (e.g. invalid combination format)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None

    def start(self, combos):
        """
        Starts the global listener. combos is {action: combination} in
        pynput format (e.g. {"mark_translate": "<ctrl>+<alt>+t"}); empty
        combinations are skipped. Safe to call repeatedly - stops the
        previous listener, if any.
        """
        self.stop()

        if not HOTKEY_SUPPORTED:
            return

        combos = {action: combo for action, combo in combos.items() if combo}
        if not combos:
            return

        try:
            from pynput import keyboard
        except Exception as e:
            logger.error(f"pynput is not available: {e}", exc_info=True)
            self.failed.emit(str(e))
            return

        try:
            self._listener = keyboard.GlobalHotKeys({
                combo: (lambda a=action: self.triggered.emit(a)) for action, combo in combos.items()
            })
            self._listener.start()
            logger.info(f"Global hotkeys active: {combos}")
        except Exception as e:
            logger.error(f"Invalid hotkey combination {combos}: {e}", exc_info=True)
            self._listener = None
            self.failed.emit(str(e) or repr(e))

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
