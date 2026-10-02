"""
ЗАСНЕМАНЕ НА ЕКРАНА (screenshot + OCR preprocessing)

Извадено от ui/main_window.py, за да не зависи UI класът от
mss/OpenCV детайлите, и за да може логиката да се тества отделно.
"""

from utils.imports import mss, cv2, np
from utils.logging_setup import logger


class CaptureError(Exception):
    """Грешка при заснемане на екрана (твърде малка област, липсващ дисплей и т.н.)."""
    pass


MIN_REGION_SIZE = 10
# Колко пъти се уголемява картинката преди OCR (по-точно разпознаване на
# дребен текст). Детекторът на шрифта трябва да знае това, за да мери в
# истински пиксели от екрана.
OCR_UPSCALE = 2


def is_region_too_small(rect):
    """Проверява дали маркираната област е достатъчно голяма за OCR."""
    width = rect.right() - rect.left()
    height = rect.bottom() - rect.top()
    return width < MIN_REGION_SIZE or height < MIN_REGION_SIZE


def capture_region_as_gray(rect):
    """
    Прави screenshot на подадения rect и връща preprocessed
    grayscale изображение (numpy array), готово за OCR.

    Хвърля CaptureError при твърде малка област или грешка при заснемане.
    """
    if is_region_too_small(rect):
        raise CaptureError("area_too_small")

    x1, y1 = rect.left(), rect.top()
    width = max(1, rect.right() - x1)
    height = max(1, rect.bottom() - y1)

    try:
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": width, "height": height}
            raw = np.array(sct.grab(monitor))
    except Exception as e:
        raise CaptureError("screenshot_error") from e

    bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Бинаризация (Otsu) + уголемяване - подобряват точността на OCR
    _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray = cv2.resize(gray, None, fx=OCR_UPSCALE, fy=OCR_UPSCALE, interpolation=cv2.INTER_CUBIC)

    return gray


def warm_up():
    """
    Прави еднократен, изхвърлен screenshot - само за да "загрее" mss-ката
    еднократна инициализация (на Windows: свързване с GDI функции през
    ctypes; на Linux: свързване с X сървъра). Без това, ПЪРВОТО реално
    маркиране на потребителя замръзва интерфейса за 1-2 секунди, защото
    start_selection() работи синхронно в главната нишка. Вика се веднъж
    във фонова нишка при стартиране на приложението (виж MainWindow),
    за да плати тази цена тихо, преди потребителят изобщо да е кликнал.
    """
    try:
        with mss.mss() as sct:
            sct.grab(sct.monitors[0])
    except Exception as e:
        logger.warning(f"Неуспешно загряване на mss: {e}")


def capture_full_screen_qimage():
    """
    Прави screenshot на целия основен монитор и го връща като QImage
    (използва се от прозореца за маркиране на област).
    """
    from utils.imports import QtGui

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        raw = np.array(sct.grab(monitor))[:, :, :3]

        height, width, _ = raw.shape
        bytes_per_line = 3 * width
        img_bytes = raw.tobytes()

        image = QtGui.QImage(
            img_bytes, width, height, bytes_per_line, QtGui.QImage.Format_RGB888
        )
        # Копираме данните, за да не увиснат след освобождаването на raw/img_bytes
        return image.copy()
