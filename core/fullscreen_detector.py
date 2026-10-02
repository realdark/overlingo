from utils.imports import sys, QtCore, QtWidgets
from utils.logging_setup import logger

class FullscreenDetector(QtCore.QObject):
    """Клас за откриване на fullscreen приложения и управление на флаговете"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.x11_bypass_applied = False

        # Автоматично обновяване за Linux
        if sys.platform == "linux":
            self.update_timer = QtCore.QTimer(self)
            self.update_timer.timeout.connect(self._auto_update_check)
            self.update_timer.start(1000)  # Проверка на всеки 1 секунда

    def stop(self):
        """
        Спира авто-проверката. ЗАДЪЛЖИТЕЛНО се вика, когато прозорецът,
        към който детекторът е прикачен, се затваря - иначе таймерът
        продължава да тиктака върху скрит widget и рано или късно пак
        го показва чрез _auto_update_check() -> self.parent().show().
        """
        if hasattr(self, "update_timer"):
            self.update_timer.stop()

    def is_fullscreen_application_active(self):
        """Проверява дали има активен fullscreen прозорец"""
        if sys.platform != "linux":
            return False

        try:
            # Метод 1: Проверка с xprop
            import subprocess
            result = subprocess.run(['xprop', '-root', '_NET_ACTIVE_WINDOW'],
                                  capture_output=True, text=True, timeout=2)

            if result.returncode == 0:
                window_id = result.stdout.strip().split()[-1]
                if window_id != '0x0':
                    result = subprocess.run(['xprop', '-id', window_id, '_NET_WM_STATE'],
                                          capture_output=True, text=True, timeout=2)
                    return '_NET_WM_STATE_FULLSCREEN' in result.stdout

        except Exception:
            # Метод 2: Опростена проверка по размер
            try:
                active_window = QtWidgets.QApplication.activeWindow()
                if active_window and active_window != self.parent():
                    screen = QtWidgets.QApplication.primaryScreen().geometry()
                    window_geometry = active_window.geometry()

                    return (window_geometry.width() >= screen.width() * 0.95 and
                           window_geometry.height() >= screen.height() * 0.95)
            except Exception:
                pass

        return False

    def apply_window_flags(self, window, base_flags):
        """Прилага подходящите флагове според fullscreen статуса"""
        if sys.platform == "linux":
            try:
                if self.is_fullscreen_application_active():
                    # Добави X11Bypass за fullscreen приложения
                    new_flags = base_flags | QtCore.Qt.X11BypassWindowManagerHint
                    window.setWindowFlags(new_flags)
                    self.x11_bypass_applied = True
                    return new_flags
                else:
                    # Стандартни флагове за нормален режим
                    window.setWindowFlags(base_flags)
                    self.x11_bypass_applied = False
                    return base_flags
            except Exception as e:
                logger.error(f"Fullscreen detector error: {e}", exc_info=True)
                window.setWindowFlags(base_flags)
                return base_flags
        else:
            # За не-Linux системи - стандартни флагове
            window.setWindowFlags(base_flags)
            return base_flags

    def _auto_update_check(self):
        """Автоматично обновява флаговете при промяна на fullscreen статуса"""
        if self.parent() and hasattr(self.parent(), 'windowFlags'):
            try:
                # Ако прозорецът е минимизиран (потребителят го е скрил
                # нарочно), НЕ пипаме нищо - иначе self.parent().show()
                # по-долу би го възстановил насила, само защото
                # детекторът преприлага флагове заради fullscreen статус
                # (напр. собствения ни SelectionWindow, засечен погрешно
                # като "чуждо fullscreen приложение"), без връзка с
                # решението на потребителя да го минимизира.
                if hasattr(self.parent(), 'isMinimized') and self.parent().isMinimized():
                    return

                # Вземи текущите флагове (без X11Bypass за сравнение)
                current_flags = self.parent().windowFlags()
                base_flags = current_flags & ~QtCore.Qt.X11BypassWindowManagerHint

                # Принови флаговете според текущия статус
                new_flags = self.apply_window_flags(self.parent(), base_flags)

                # Ако флаговете са се променили, прерисувай прозореца
                if current_flags != new_flags:
                    self.parent().setWindowFlags(new_flags)
                    self.parent().show()  # Прерисуване

            except Exception as e:
                logger.error(f"Auto-update error: {e}", exc_info=True)
