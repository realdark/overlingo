"""
ДЕТЕКЦИЯ НА РАЗМЕРА НА ШРИФТА

За "Запази големината на оригиналния шрифт" - преводът в overlay-я да е
със същия размер като оригиналния текст под него. Без Qt зависимост.

Как се мери (размерът е "font-size" в пиксели, както в стила на overlay-я):
  1. Tesseract дава кутия за всяка разпозната дума - височината на думата
     (от горния край на високите букви до долния на "g", "p"...) е около
     0.75 от размера на шрифта.
  2. OpenCV дава "петната" текст: картинката за OCR е бинаризирана и после
     уголемена 2 пъти, а уголемяването оставя тънък сив ореол около буквите,
     който слепва съседните букви в думи/срички. Медианната височина на
     тези петна е около 0.875 от размера на шрифта. (Отделните букви не
     стават - височината на малките букви е много различна при различните
     шрифтове.) Затова детекторът очаква картинка, подготвена точно като в
     core/capture.py, и не я бинаризира наново - иначе ореолът изчезва.
  Крайният резултат е средното от двете - всяко поотделно греши в различни
  посоки при различни шрифтове, а заедно грешат по-малко.

Коефициентите са измерени върху текст с известен размер (12-40 px, 10
шрифта, светъл и тъмен фон, малки и главни букви, един и няколко реда):
средна грешка ~7%, 98% от пробите в рамките на ±20%. Предишната версия
мереше уголемената за OCR картинка като истински пиксели и изхвърляше
всичко над 50 px - едрият текст (игри, субтитри) падаше към 14 px.
"""

from utils.imports import pytesseract, Output, cv2, np
from utils.logging_setup import logger

WORD_HEIGHT_TO_FONT = 1.333    # размер ≈ височина на дума × 1.333
BLOB_HEIGHT_TO_FONT = 1.143    # размер ≈ медианна височина на петно текст × 1.143
MIN_FONT_SIZE, MAX_FONT_SIZE = 8, 120
MIN_WORD_CONFIDENCE = 60


class FontSizeDetector:
    def __init__(self, ocr_lang="eng"):
        self.ocr_lang = ocr_lang

    def detect(self, image, scale=1.0):
        """
        Размерът на шрифта в пиксели на екрана, или None, ако не може да се
        измери (тогава overlay-ят ползва размера от Настройки).

        scale: колко пъти е уголемена картинката спрямо екрана (картинката
        за OCR е уголемена 2 пъти - виж OCR_UPSCALE в core/capture.py).
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
        """Медианна височина на разпознатите думи (Tesseract), в пиксели на екрана."""
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
            if data["level"][i] == 5  # дума
            and (data["text"][i] or "").strip()
            and float(data["conf"][i]) > MIN_WORD_CONFIDENCE
            and data["height"][i] / scale >= 4
        ]
        return float(np.median(heights)) if heights else None

    def _median_blob_height(self, gray, scale):
        """Медианна височина на петната текст (OpenCV), в пиксели на екрана - виж бележката горе."""
        try:
            text_white = gray if np.mean(gray) < 127 else 255 - gray  # текстът - светъл върху тъмно
            mask = (text_white > 0).astype(np.uint8)  # с ореола от уголемяването (не бинаризираме наново)
            count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            min_area = 4 * scale * scale  # без шум и точици
            heights = np.array([
                stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, count)
                if stats[i, cv2.CC_STAT_AREA] >= min_area
            ], dtype=float) / scale
            if len(heights) == 0:
                return None
            median = np.median(heights)
            # без запетаи/точки (много ниски) и рамки/линии (много високи)
            typical = heights[(heights >= median * 0.5) & (heights <= median * 2.5)]
            return float(np.median(typical)) if len(typical) else None
        except Exception as e:
            logger.warning(f"OpenCV size error: {e}")
            return None
