"""
ВХОДНА ТОЧКА НА ПРИЛОЖЕНИЕТО
"""

import sys

# Windows: ctranslate2 (превод без интернет) се зарежда ПРЕДИ PyQt5/OpenCV.
# PyQt5 носи по-стара версия на C++ библиотеката msvcp140.dll; ако тя е
# заредена първа, ctranslate2 (компилиран с по-нова) я ползва и при първия
# превод процесът пада без никаква грешка. Заредена първа, по-новата
# системна версия важи за всички.
if sys.platform == "win32":
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except Exception:
        pass  # не са инсталирани - преводът без интернет просто няма да е наличен

from utils.imports import sys, os, QtWidgets, QtGui, QtCore
from utils.logging_setup import logger
from utils.config import THEME_FILE, APP_ICON_LINUX, BASE_DIR
from core.single_instance import SingleInstance
from ui.main_window import MainWindow

def load_theme(app):
    """Прилага общата тъмна тема (assets/theme.qss) върху цялото приложение."""
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        # Липсваща/повредена theme.qss не бива да пречи на стартирането -
        # приложението просто ще изглежда с default стил на Qt.
        logger.warning(f"Не успях да заредя темата ({THEME_FILE}): {e}")

def show_splash(app):
    """
    Показва иконата веднага, докато MainWindow() се строи (Tesseract
    discovery, зареждане на locale файлове, построяване на UI-а) - без
    това, между двоен клик и появата на прозореца няма никаква видима
    реакция, особено на по-бавна машина, и потребителят може да си
    помисли, че нищо не се е случило (и да кликне пак, отваряйки втора
    инстанция). .png версията на иконата работи навсякъде за QPixmap,
    независимо от платформата.
    """
    pixmap = QtGui.QPixmap(str(APP_ICON_LINUX))
    if pixmap.isNull():
        return None
    pixmap = pixmap.scaled(160, 160, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    splash = QtWidgets.QSplashScreen(
        pixmap, QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint
    )
    # Иконата има прозрачни ъгли (заоблена форма) - без това splash
    # прозорецът щеше да изглежда като плътен квадрат около нея.
    splash.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    splash.show()
    app.processEvents()  # уверява се, че splash-ът реално се рисува веднага
    return splash


def main():
    """Основна функция на приложението"""
    try:
        # Работна папка = папката на програмата, независимо откъде е
        # стартирана (меню с приложения, пряк път, друга папка в
        # терминала). Всички пътища вече са абсолютни (виж
        # utils/config.py), това е само допълнителна защита.
        try:
            os.chdir(BASE_DIR)
        except OSError as e:
            logger.warning(f"Не успях да сменя работната папка към {BASE_DIR}: {e}")
        app = QtWidgets.QApplication(sys.argv)

        # Ако Overlingo вече е отворена, само я показваме и излизаме -
        # преди splash-а, за да не мигне излишно (виж core/single_instance.py).
        instance = SingleInstance()
        if instance.notify_running_instance():
            logger.info("Overlingo вече работи - показвам отвореното копие.")
            return 0
        instance.listen()

        load_theme(app)
        splash = show_splash(app)
        window = MainWindow()
        instance.activation_requested.connect(window.bring_to_front)
        window.show()
        if splash:
            splash.finish(window)  # затваря splash-а веднага щом прозорецът е готов
        return app.exec_()
    except Exception as e:
        logger.error(f"Грешка при стартиране: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())