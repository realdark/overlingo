"""
SCREEN CAPTURE (screenshot + OCR preprocessing)

Extracted from ui/main_window.py so the UI class doesn't depend on the
mss/OpenCV details, and so the logic can be tested separately.
"""

from utils.imports import mss, cv2, np
from utils.logging_setup import logger


class CaptureError(Exception):
    """Screen capture error (region too small, missing display, etc.)."""
    pass


MIN_REGION_SIZE = 10
# How many times the image is upscaled before OCR (more accurate recognition
# of small text). The font size detector needs to know this in order to
# measure in real screen pixels.
OCR_UPSCALE = 2


def is_region_too_small(rect):
    """Checks whether the selected region is large enough for OCR."""
    width = rect.right() - rect.left()
    height = rect.bottom() - rect.top()
    return width < MIN_REGION_SIZE or height < MIN_REGION_SIZE


def physical_region(left, top, width, height, screen_origin=(0, 0), ratio=1.0):
    """
    Qt (logical) coordinates -> real screen pixels for mss. With display scaling
    (devicePixelRatio > 1) Qt keeps each screen's top-left corner in real pixels
    and scales only the distances within the screen.
    """
    ox, oy = screen_origin
    return {
        "left": int(round(ox + (left - ox) * ratio)),
        "top": int(round(oy + (top - oy) * ratio)),
        "width": max(1, int(round(width * ratio))),
        "height": max(1, int(round(height * ratio))),
    }


def _screen_of(rect):
    """The QScreen the rect is on (by its center), or None without a QApplication."""
    from utils.imports import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    return QtWidgets.QApplication.screenAt(rect.center()) or QtWidgets.QApplication.primaryScreen()


def _mss_region(rect):
    screen = _screen_of(rect)
    if screen is None:
        return physical_region(rect.left(), rect.top(), rect.width(), rect.height())
    origin = screen.geometry().topLeft()
    return physical_region(
        rect.left(), rect.top(), rect.width(), rect.height(),
        (origin.x(), origin.y()), screen.devicePixelRatio(),
    )


def capture_region_as_gray(rect):
    """
    Takes a screenshot of the given rect (global Qt coordinates) and returns a
    preprocessed grayscale image (numpy array), ready for OCR.

    Raises CaptureError if the region is too small or the capture fails.
    """
    if is_region_too_small(rect):
        raise CaptureError("area_too_small")

    try:
        monitor = _mss_region(rect)
        with mss.mss() as sct:
            raw = np.array(sct.grab(monitor))
    except Exception as e:
        raise CaptureError("screenshot_error") from e

    bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Binarization (Otsu) + upscaling - improve OCR accuracy
    _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray = cv2.resize(gray, None, fx=OCR_UPSCALE, fy=OCR_UPSCALE, interpolation=cv2.INTER_CUBIC)

    return gray


def warm_up():
    """
    Takes a single throwaway screenshot - only to "warm up" mss's one-time
    initialization (on Windows: binding to GDI functions via ctypes; on
    Linux: connecting to the X server). Without this, the user's FIRST real
    selection freezes the UI for 1-2 seconds, because start_selection()
    runs synchronously on the main thread. Called once in a background
    thread at application startup (see MainWindow), to pay this cost
    quietly before the user has even clicked.
    """
    try:
        with mss.mss() as sct:
            sct.grab(sct.monitors[0])
    except Exception as e:
        logger.warning(f"Failed to warm up mss: {e}")


def capture_screen_qimage(screen):
    """
    Screenshot of one monitor (a QScreen) as a QImage - the background of the
    area selection window, which opens on that monitor.
    """
    from utils.imports import QtGui

    geometry = screen.geometry()
    monitor = physical_region(
        geometry.left(), geometry.top(), geometry.width(), geometry.height(),
        (geometry.left(), geometry.top()), screen.devicePixelRatio(),
    )
    with mss.mss() as sct:
        raw = np.ascontiguousarray(np.array(sct.grab(monitor))[:, :, :3])

    height, width, _ = raw.shape
    # mss gives BGRA - the first three bytes are blue, green, red (as RGB888 the
    # colours came out swapped).
    image = QtGui.QImage(raw.tobytes(), width, height, 3 * width, QtGui.QImage.Format_BGR888)
    # Copy the data so it doesn't dangle after raw is freed
    return image.copy()
