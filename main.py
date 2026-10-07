"""
APPLICATION ENTRY POINT
"""

import sys

# Windows: ctranslate2 (offline translation) is loaded BEFORE PyQt5/OpenCV.
# PyQt5 ships an older version of the C++ library msvcp140.dll; if it is
# loaded first, ctranslate2 (compiled against a newer one) uses it and the
# process dies on the first translation without any error. Loaded first, the
# newer system version applies to everyone.
if sys.platform == "win32":
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except Exception:
        pass  # not installed - offline translation simply won't be available

from utils.imports import sys, os, QtWidgets, QtGui, QtCore
from utils.logging_setup import logger
from utils.config import THEME_FILE, APP_ICON_LINUX, BASE_DIR
from core.single_instance import SingleInstance
from ui.main_window import MainWindow

def load_theme(app):
    """Applies the shared dark theme (assets/theme.qss) to the whole application."""
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        # A missing/corrupted theme.qss must not prevent startup -
        # the application will simply use Qt's default style.
        logger.warning(f"Could not load the theme ({THEME_FILE}): {e}")

def show_splash(app):
    """
    Shows the icon immediately while MainWindow() is being built (Tesseract
    discovery, loading locale files, building the UI) - without this, there
    is no visible reaction between the double-click and the window
    appearing, especially on a slower machine, and the user may think
    nothing happened (and click again, opening a second instance). The .png
    version of the icon works everywhere for QPixmap, regardless of the
    platform.
    """
    pixmap = QtGui.QPixmap(str(APP_ICON_LINUX))
    if pixmap.isNull():
        return None
    pixmap = pixmap.scaled(160, 160, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    splash = QtWidgets.QSplashScreen(
        pixmap, QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint
    )
    # The icon has transparent corners (rounded shape) - without this the splash
    # window would look like a solid square around it.
    splash.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    splash.show()
    app.processEvents()  # makes sure the splash is actually painted right away
    return splash


def main():
    """Main application function"""
    if "--self-test" in sys.argv:
        # Automatic build check (GitHub Actions) - see core/selftest.py.
        from core.selftest import run_self_test
        return run_self_test(sys.argv)
    try:
        # Working directory = the program folder, regardless of where it was
        # launched from (applications menu, shortcut, another folder in the
        # terminal). All paths are already absolute (see
        # utils/config.py), this is just an extra safeguard.
        try:
            os.chdir(BASE_DIR)
        except OSError as e:
            logger.warning(f"Could not change the working directory to {BASE_DIR}: {e}")
        app = QtWidgets.QApplication(sys.argv)
        # Linux: ties the window to the overlingo.desktop launcher (from install.sh) -
        # so the taskbar/dock shows the program's icon (especially under Wayland).
        app.setDesktopFileName("overlingo")

        # If Overlingo is already open, just show it and exit -
        # before the splash, so it doesn't flash needlessly (see core/single_instance.py).
        instance = SingleInstance()
        if instance.notify_running_instance():
            logger.info("Overlingo is already running - showing the open instance.")
            return 0
        instance.listen()

        load_theme(app)
        splash = show_splash(app)
        window = MainWindow()
        instance.activation_requested.connect(window.bring_to_front)
        window.show()
        if splash:
            splash.finish(window)  # closes the splash as soon as the window is ready
        return app.exec_()
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())