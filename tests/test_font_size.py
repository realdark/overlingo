import shutil
import unittest
from unittest import mock

import numpy as np

from core import font_size_detector as fsd
from core.font_size_detector import FontSizeDetector


class CombinationTest(unittest.TestCase):
    """Calculations on the two measurements - without Tesseract."""

    def _detect(self, word, blob):
        detector = FontSizeDetector()
        with mock.patch.object(detector, "_median_word_height", return_value=word), \
             mock.patch.object(detector, "_median_blob_height", return_value=blob):
            return detector.detect(np.zeros((40, 200), dtype=np.uint8), scale=2)

    def test_average_of_both(self):
        expected = round((15 * fsd.WORD_HEIGHT_TO_FONT + 14 * fsd.BLOB_HEIGHT_TO_FONT) / 2)
        self.assertEqual(self._detect(15, 14), expected)

    def test_one_measure_is_enough(self):
        self.assertEqual(self._detect(None, 14), round(14 * fsd.BLOB_HEIGHT_TO_FONT))

    def test_nothing_measured_gives_none(self):
        self.assertIsNone(self._detect(None, None))

    def test_result_is_clamped(self):
        self.assertEqual(self._detect(1, 1), fsd.MIN_FONT_SIZE)
        self.assertEqual(self._detect(500, 500), fsd.MAX_FONT_SIZE)

    def test_empty_image(self):
        self.assertIsNone(FontSizeDetector().detect(np.zeros((0, 0), dtype=np.uint8)))


def _real_ocr_available():
    try:
        import cv2  # noqa: F401
        import pytesseract  # noqa: F401
        from PIL import ImageFont  # noqa: F401
    except Exception:
        return False
    return shutil.which("tesseract") is not None


@unittest.skipUnless(_real_ocr_available(), "requires Tesseract, OpenCV and Pillow")
class RealTextTest(unittest.TestCase):
    """Real text of known size, prepared as a screenshot for OCR."""

    def _measure(self, size, dark_background):
        import cv2
        from PIL import Image, ImageDraw, ImageFont
        from core.capture import OCR_UPSCALE

        font = ImageFont.load_default(size=size)
        text = "The quick brown fox jumps over the lazy dog"
        left, top, right, bottom = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font)
        bg, fg = (25, 235) if dark_background else (245, 20)
        img = Image.new("L", (right - left + 30, bottom - top + 24), bg)
        ImageDraw.Draw(img).text((15 - left, 12 - top), text, font=font, fill=fg)
        gray = np.array(img)
        # same preprocessing as core/capture.py
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        gray = cv2.resize(gray, None, fx=OCR_UPSCALE, fy=OCR_UPSCALE, interpolation=cv2.INTER_CUBIC)
        return FontSizeDetector("eng").detect(gray, scale=OCR_UPSCALE)

    def test_sizes_within_25_percent(self):
        for size in (16, 24, 40):  # 40 px - the large text the old version missed
            for dark in (True, False):
                measured = self._measure(size, dark)
                self.assertIsNotNone(measured, size)
                self.assertLessEqual(abs(measured - size) / size, 0.25, f"{size}px -> {measured}px")


if __name__ == "__main__":
    unittest.main()
