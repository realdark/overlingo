"""
ГЛОБАЛЕН HOTKEY (Windows и Linux/X11)

Ползва pynput.keyboard.GlobalHotKeys, което слуша на системно ниво -
работи независимо кой прозорец има фокус в момента. Поддържано на:
- Windows - pynput работи надеждно там без специални разрешения.
- Linux, САМО под X11 сесия - X11 позволява на обикновени приложения
  да слушат клавиатурата глобално (същата причина, поради която
  FullscreenDetector-ът с X11Bypass трика работи там). Открива се чрез
  XDG_SESSION_TYPE - ако не е изрично "x11" (напр. липсва, или е
  "wayland"), приемаме, че НЕ е поддържано - по-безопасно да откажем,
  отколкото да предположим грешно.
Не е поддържано на:
- Linux/Wayland - compositor-ът нарочно блокира глобално слушане на
  клавиатура от нормални приложения, по съображения за сигурност; няма
  client-side заобикаляне, аналогично на X11Bypass.
- macOS - изисква изрично Accessibility разрешение и има допълнителни
  ограничения (SecureEventInput) при определени видове съдържание.

pynput вика callback-а от СОБСТВЕНА нишка, не от Qt главната нишка -
затова HotkeyManager е QObject с pyqtSignal: емитването на сигнал от
чужда нишка е thread-safe в Qt (автоматично се превръща в queued
connection), докато директно пипане на widget-и от pynput нишката
би било опасно.
"""

from utils.imports import QtCore, sys, os
from utils.logging_setup import logger

IS_WINDOWS = sys.platform == "win32"
IS_LINUX_X11 = sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"
HOTKEY_SUPPORTED = IS_WINDOWS or IS_LINUX_X11


# Действия, които могат да имат hotkey. Стойността е ключът в настройките.
ACTION_MARK_TRANSLATE = "mark_translate"
ACTION_RETRANSLATE = "retranslate"
HOTKEY_SETTING_KEYS = {
    ACTION_MARK_TRANSLATE: "hotkey_combo",
    ACTION_RETRANSLATE: "hotkey_retranslate_combo",
}


def format_combo(combo):
    """
    pynput формат -> четим текст за подсказки: "<ctrl>+<alt>+t" -> "Ctrl+Alt+T".
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
    Връща текст на грешката, ако комбинацията не е валиден pynput формат,
    иначе None. Ако pynput липсва, не можем да проверим - връща None.
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
    # действие (ACTION_*), чийто hotkey е натиснат
    triggered = QtCore.pyqtSignal(str)
    # error message (напр. невалиден формат на комбинацията)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None

    def start(self, combos):
        """
        Стартира глобалния слушател. combos е {действие: комбинация} в
        pynput формат (напр. {"mark_translate": "<ctrl>+<alt>+t"}); празни
        комбинации се пропускат. Безопасно за повторно извикване - спира
        предишния слушател, ако има такъв.
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
            logger.error(f"pynput не е наличен: {e}", exc_info=True)
            self.failed.emit(str(e))
            return

        try:
            self._listener = keyboard.GlobalHotKeys({
                combo: (lambda a=action: self.triggered.emit(a)) for action, combo in combos.items()
            })
            self._listener.start()
            logger.info(f"Глобални hotkey-и активни: {combos}")
        except Exception as e:
            logger.error(f"Невалидна hotkey комбинация {combos}: {e}", exc_info=True)
            self._listener = None
            self.failed.emit(str(e) or repr(e))

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
