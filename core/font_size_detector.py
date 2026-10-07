"""
FONT SIZE DETECTION

For "Keep the original font size" - the translation in the overlay should
have the same size as the original text beneath it. No Qt dependency.

How it is measured (the size is "font-size" in pixels, as in the overlay's style):
  1. Tesseract gives a box for each recognized word - the word height
     (from the top of the tall letters to the bottom of "g", "p"...) is about
     0.75 of the font size.
  2. OpenCV gives the text "blobs": the OCR image is binarized and then
     upscaled 2x, and the upscaling leaves a thin gray halo around the letters
     that glues neighboring letters into words/syllables. The median height of
     these blobs is about 0.875 of the font size. (Individual letters don't
     work - lowercase letter height varies a lot between fonts.) That is why
     the detector expects an image prepared exactly as in core/capture.py and
     does not re-binarize it - otherwise the halo disappears.
  The final result is the average of the two - each one alone errs in
  different directions for different fonts, and together they err less.

The coefficients were measured on text of known size (12-40 px, 10
fonts, light and dark background, lowercase and uppercase, single and multiple
lines): mean error ~7%, 98% of samples within ±20%. The previous version
measured the OCR-upscaled image as real pixels and discarded everything
above 50 px - large text (games, subtitles) fell to 14 px.
"""

from utils.imports import pytesseract, Output, cv2, np
from utils.logging_setup import logger

WORD_HEIGHT_TO_FONT = 1.333    # size ≈ word height × 1.333
BLOB_HEIGHT_TO_FONT = 1.143    # size ≈ median text blob height × 1.143
MIN_FONT_SIZE, MAX_FONT_SIZE = 8, 120
MIN_WORD_CONFIDENCE = 60


class FontSizeDetector:
    def __init__(self, ocr_lang="eng"):
        self.ocr_lang = ocr_lang

    def detect(self, image, scale=1.0):
        """
        The font size in screen pixels, or None if it cannot be measured
        (then the overlay uses the size from Settings).

        scale: how many times the image is upscaled relative to the screen
        (the OCR image is upscaled 2x - see OCR_UPSCALE in core/capture.py).
        """
        if image is None or image.size == 0:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        estimates = []
        word_height = self._median_word_height(gray, scale)
        if word_height:
            estimates.append(word_height * WORD_HEIGHT_TO_FONT)
        blob_height = self._median_blob_height(gray, scale)
        if blob_height:
            estimates.append(blob_height * BLOB_HEIGHT_TO_FONT)

        if not estimates:
            return None
        size = sum(estimates) / len(estimates)
        return int(round(min(MAX_FONT_SIZE, max(MIN_FONT_SIZE, size))))

    def _median_word_height(self, gray, scale):
        """Median height of the recognized words (Tesseract), in screen pixels."""
        try:
            data = pytesseract.image_to_data(
                gray, lang=self.ocr_lang, config="--oem 3 --psm 6", output_type=Output.DICT
            )
        except Exception as e:
            logger.warning(f"OCR size error: {e}")
            return None
        heights = [
            data["height"][i] / scale
            for i in range(len(data["text"]))
            if data["level"][i] == 5  # word
            and (data["text"][i] or "").strip()
            and float(data["conf"][i]) > MIN_WORD_CONFIDENCE
            and data["height"][i] / scale >= 4
        ]
        return float(np.median(heights)) if heights else None

    def _median_blob_height(self, gray, scale):
        """Median height of the text blobs (OpenCV), in screen pixels - see the note above."""
        try:
            text_white = gray if np.mean(gray) < 127 else 255 - gray  # text - light on dark
            mask = (text_white > 0).astype(np.uint8)  # with the upscaling halo (we don't re-binarize)
            count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            min_area = 4 * scale * scale  # skip noise and dots
            heights = np.array([
                stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, count)
                if stats[i, cv2.CC_STAT_AREA] >= min_area
            ], dtype=float) / scale
            if len(heights) == 0:
                return None
            median = np.median(heights)
            # skip commas/periods (very short) and frames/lines (very tall)
            typical = heights[(heights >= median * 0.5) & (heights <= median * 2.5)]
            return float(np.median(typical)) if len(typical) else None
        except Exception as e:
            logger.warning(f"OpenCV size error: {e}")
            return None
