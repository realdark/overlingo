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


def capture_region_as_gray(rect):
    """
    Takes a screenshot of the given rect and returns a preprocessed
    grayscale image (numpy array), ready for OCR.

    Raises CaptureError if the region is too small or the capture fails.
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


def capture_full_screen_qimage():
    """
    Takes a screenshot of the entire primary monitor and returns it as a QImage
    (used by the region selection window).
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
        # Copy the data so it doesn't dangle after raw/img_bytes are freed
        return image.copy()
