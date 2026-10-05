"""
ПРЕВОДНИ УСЛУГИ И КЕШИРАНЕ

Преводачите (Google / DeepL / Microsoft / Argos без интернет) споделят общ интерфейс:
    translate(text, target_lang) -> str

Всички връщат директно текст (str), вместо отделен обект-обвивка
за всяка услуга - опростява извикващия код.
"""

import re
import threading
from collections import OrderedDict

from utils.imports import QThread, pyqtSignal, requests, deepl, pytesseract
from utils.logging_setup import logger
from core.retry import retry_with_backoff
from core.network import has_internet_connection
from core.font_size_detector import FontSizeDetector
from core.capture import OCR_UPSCALE
from core.argos import ArgosTranslator, ArgosModelMissingError, ArgosNotInstalledError, libraries_available


class NoInternetError(Exception):
    """
    Хвърля се от облачните преводачи (Google/DeepL/Microsoft), ако няма
    никаква интернет връзка - за да се провали бързо, вместо да чака
    целия retry цикъл (~7s) напразно. Съобщението НЕ съдържа думи като
    "connection"/"timeout"/"429", за да не бъде сметнато за retryable от
    is_retryable_error() в core/retry.py - тук няма смисъл от нов опит.
    Argos (превод на компютъра) не използва това - работи без интернет по дизайн.
    """
    pass


def error_key_for(exc):
    """
    Грешка от преводач -> (ключ за текст в locales, технически детайл).
    Така съобщението към потребителя е на езика на интерфейса, а детайлът
    (напр. текстът на HTTP грешката) се показва след него.
    """
    if isinstance(exc, NoInternetError):
        return "no_internet", ""
    if isinstance(exc, ArgosModelMissingError):
        return "argos_model_missing", str(exc)
    if isinstance(exc, ArgosNotInstalledError):
        return "argos_not_installed", str(exc)
    return "translation_error", str(exc)


class BaseTranslator:
    """Общ интерфейс за всички преводачи на текст."""

    def translate(self, text, target_lang):
        raise NotImplementedError


class MicrosoftTranslator(BaseTranslator):
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://api.cognitive.microsofttranslator.com"

    def translate(self, text, target_lang):
        """Превежда текст чрез Microsoft Translator API (с retry при 429/5xx)."""
        if not has_internet_connection():
            raise NoInternetError("Няма интернет връзка - Microsoft Translator изисква онлайн достъп")

        def _request():
            url = self.endpoint + "/translate"
            params = {"api-version": "3.0", "to": target_lang.lower()}
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-type": "application/json",
            }
            body = [{"text": text}]

            response = requests.post(url, params=params, headers=headers, json=body, timeout=15)
            response.raise_for_status()
            return response.json()

        try:
            result = retry_with_backoff(_request, label="Microsoft")
            if result and "translations" in result[0]:
                return result[0]["translations"][0]["text"]
            raise Exception("No translation returned from Microsoft Translate")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Microsoft Translate API error: {e}")
        except Exception as e:
            raise Exception(f"Microsoft Translate error: {e}")


class GoogleTranslator(BaseTranslator):
    """Google Translate чрез requests, с автоматично делене на дълъг текст."""

    MAX_CHUNK_LEN = 3000

    def __init__(self):
        self.endpoint = "https://translate.googleapis.com"
        self.session = requests.Session()

    def _split_text(self, text, max_len=None):
        """
        Разделя текста на парчета до max_len знака, само след край на
        изречение (. ! ?). Всяко парче пази и празното място след себе си,
        така че "".join(парчетата) дава точно оригиналния текст - нищо не
        се губи на границите (по-рано там изчезваше ". ").
        Изречение, по-дълго от max_len, остава цяло в собствено парче.
        """
        max_len = max_len or self.MAX_CHUNK_LEN
        parts = re.split(r"(?<=[.!?])(\s+)", text)
        # parts = [изречение, празно място, изречение, празно място, ...]
        pieces = [parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
                  for i in range(0, len(parts), 2)]

        chunks = []
        current = ""
        for piece in pieces:
            if current and len(current) + len(piece.rstrip()) > max_len:
                chunks.append(current)
                current = piece
            else:
                current += piece
        if current.strip():
            chunks.append(current)
        return chunks

    def _translate_chunk(self, chunk, target_lang, url, headers):
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang.lower(),
            "dt": "t",
            "q": chunk,
        }
        response = self.session.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def translate(self, text, target_lang):
        """Превежда (евентуално дълъг) текст чрез Google Translate (с retry при 429/5xx)."""
        if not has_internet_connection():
            raise NoInternetError("Няма интернет връзка - Google Translate изисква онлайн достъп")

        try:
            url = self.endpoint + "/translate_a/single"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://translate.google.com/",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
            }

            translated_parts = []
            for chunk in self._split_text(text):
                data = retry_with_backoff(
                    lambda c=chunk.strip(): self._translate_chunk(c, target_lang, url, headers),
                    label="Google",
                )

                if isinstance(data, list) and data:
                    for segment in data[0]:
                        if isinstance(segment, list) and segment:
                            translated_parts.append(segment[0])
                # Празното място между парчетата (интервал или нов ред) се
                # връща, иначе преводите на съседни парчета се слепват.
                translated_parts.append(chunk[len(chunk.rstrip()):])

            return "".join(translated_parts).rstrip()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Google Translate API error: {e}")
        except (IndexError, KeyError, TypeError) as e:
            raise Exception(f"Google Translate response parsing error: {e}")
        except Exception as e:
            raise Exception(f"Google Translate error: {e}")


class DeepLTranslator(BaseTranslator):
    """Тънка обвивка около официалната deepl библиотека, за да пасне на BaseTranslator."""

    def __init__(self, api_key):
        self._client = deepl.Translator(api_key)

    def translate(self, text, target_lang):
        if not has_internet_connection():
            raise NoInternetError("Няма интернет връзка - DeepL изисква онлайн достъп")

        result = retry_with_backoff(
            lambda: self._client.translate_text(text, target_lang=target_lang),
            label="DeepL",
        )
        return result.text


class TranslationCache:
    """
    Вече преведен текст -> превод, за да не се праща същата заявка пак (при
    авто-рефреш, "Преведи отново", еднакъв текст в прозореца за текст).
    Ключът е текстът (без разлика в интервалите и главните букви) ЗАЕДНО с
    целевия език - иначе след смяна на езика излизаше старият превод.
    Пази най-много MAX_ITEMS записа; при препълване отпада най-отдавна
    ползваният.
    """

    MAX_ITEMS = 500

    def __init__(self, max_items=MAX_ITEMS):
        self.max_items = max_items
        self.cache = OrderedDict()

    def get(self, text, target_lang=""):
        key = self._key(text, target_lang)
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)  # току-що ползван - отпада последен
        return self.cache[key]

    def put(self, text, translation, target_lang=""):
        key = self._key(text, target_lang)
        self.cache[key] = translation
        self.cache.move_to_end(key)
        while len(self.cache) > self.max_items:
            self.cache.popitem(last=False)

    @staticmethod
    def _key(text, target_lang):
        normalized = " ".join((text or "").split()).lower()
        return (normalized, (target_lang or "").upper())

    def clear(self):
        """Изчиства целия кеш."""
        self.cache.clear()


class FallbackTranslator(BaseTranslator):
    """
    Обвива основен преводач с резервни варианти:
      - няма интернет -> превод на компютъра (Argos), ако моделите са свалени;
      - друга грешка -> fallback (обикновено Google - безплатен, без ключ).
    fallback_used казва какво е станало при последния translate():
    "" - основната услуга, "google" - резервната, "offline" - без интернет.
    """

    def __init__(self, primary, fallback, offline=None):
        self.primary = primary
        self.fallback = fallback
        self.offline = offline
        # Един преводач се ползва от няколко нишки едновременно (превод от
        # екрана + прозореца за текст) - всяка нишка вижда своя резултат.
        self._state = threading.local()

    @property
    def fallback_used(self):
        return getattr(self._state, "fallback_used", "")

    @fallback_used.setter
    def fallback_used(self, value):
        self._state.fallback_used = value

    def translate(self, text, target_lang):
        self.fallback_used = ""
        try:
            return self.primary.translate(text, target_lang)
        except NoInternetError:
            if self.offline is None:
                raise
            try:
                result = self.offline.translate(text, target_lang)
            except Exception as offline_error:
                logger.info(f"Няма интернет, а и превод без интернет не е възможен: {offline_error}")
                raise NoInternetError("Няма интернет връзка") from None
            logger.info("Няма интернет - преведено на компютъра (Argos)")
            self.fallback_used = "offline"
            return result
        except Exception as e:
            if self.fallback is None:
                raise
            logger.warning(f"Основната услуга за превод се провали ({e}) - опитвам резервна (Google)")
            self.fallback_used = "google"
            return self.fallback.translate(text, target_lang)


# Съпоставя стойността от настройките (api_type) с конкретния клас преводач.
_TRANSLATOR_FACTORIES = {
    "google": lambda api_key, source_lang: GoogleTranslator(),
    "deepl": lambda api_key, source_lang: DeepLTranslator(api_key) if api_key else None,
    "microsoft": lambda api_key, source_lang: MicrosoftTranslator(api_key) if api_key else None,
    "argos": lambda api_key, source_lang: ArgosTranslator(source_lang or "en"),
}

# Онлайн услугите, които при грешка падат към Google ("google" е самият
# резервен вариант; "argos" е нарочно избран превод без интернет).
_GOOGLE_FALLBACK = {"deepl", "microsoft"}


def create_translator(api_type, api_key=None, enable_fallback=True, source_lang="en"):
    """
    Фабрика: връща подходящия преводач за api_type, или None ако няма
    нужния api_key (за deepl/microsoft).
    source_lang - двубуквеният език на оригинала (за Argos, виж
    core.argos.source_language).

    Ако enable_fallback=True, онлайн услугите се обвиват във
    FallbackTranslator: DeepL/Microsoft падат към Google при грешка, а
    всички онлайн услуги - към превод на компютъра (Argos), ако няма
    интернет и моделите за езиците са свалени.
    """
    factory = _TRANSLATOR_FACTORIES.get(api_type)
    primary = factory(api_key, source_lang) if factory else None
    if primary is None or not enable_fallback or api_type == "argos":
        return primary
    google = GoogleTranslator() if api_type in _GOOGLE_FALLBACK else None
    offline = ArgosTranslator(source_lang) if libraries_available() else None
    if google is None and offline is None:
        return primary  # няма към какво да падне
    return FallbackTranslator(primary, google, offline)


def fallback_notice_key(fallback_used):
    """Ключът на съобщението за резервния превод ("google" / "offline")."""
    return "offline_notice" if fallback_used == "offline" else "fallback_notice"


def translate_with_cache(translator, text, target_lang, cache=None):
    """
    Превежда text, като първо гледа в кеша. Връща
    (превод, от_кеша, резервен_вариант), където резервният вариант е ""
    (основната услуга), "google" или "offline" (виж FallbackTranslator).
    Грешките от преводача се подават нагоре непроменени. Общо за превода
    от екрана и за прозореца за превод на текст.
    """
    cached = cache.get(text, target_lang) if cache is not None else None
    if cached is not None:
        return cached, True, ""
    translated = translator.translate(text, target_lang)
    fallback_used = getattr(translator, "fallback_used", "")
    # Офлайн преводът (при липса на интернет) не се кешира - щом интернетът
    # се върне, същият текст да мине пак през по-добрата онлайн услуга.
    if cache is not None and fallback_used != "offline":
        cache.put(text, translated, target_lang)
    return translated, False, fallback_used


class TranslationThread(QThread):
    """Изпълнява OCR + превод във фонова нишка, за да не блокира UI-а."""

    # source_text, translated_text, from_cache, fallback_used ("" / "google" / "offline"),
    # font_size (размер на оригиналния шрифт в px; 0 = не е мерен)
    finished_signal = pyqtSignal(str, str, bool, str, int)
    # source_text (може да е празен), error_key (ключ за превод в locales), detail
    failed_signal = pyqtSignal(str, str, str)

    def __init__(self, gray_img, ocr_lang, translator, target_lang, translation_cache=None,
                 detect_font_size=False):
        """
        detect_font_size: да се измери ли и размерът на шрифта (второ
        минаване на Tesseract) - само когато overlay-ят тепърва ще се
        създава. Тук, във фоновата нишка, за да не замръзва интерфейсът.
        """
        super().__init__()
        self.detect_font_size = detect_font_size
        self.gray_img = gray_img
        self.ocr_lang = ocr_lang
        self.translator = translator  # BaseTranslator или None
        self.target_lang = target_lang
        self.translation_cache = translation_cache

    def group_paragraphs(self, raw_lines):
        """
        Групира OCR редове в параграфи и изречения.
        Връща списък от параграфи, където всеки параграф е списък от изречения.

        - Празен ред = нов параграф, освен ако предният ред няма крайна пунктуация (.!?;:)
          → тогава празният ред се игнорира и следващият текст се слепва.
        - Вътре в параграф редовете се слепват, докато не срещнем крайна пунктуация.
        """
        paragraphs = []
        buffer = []

        i = 0
        while i < len(raw_lines):
            line = raw_lines[i].strip()

            if line == "":
                if buffer:
                    prev = buffer[-1]
                    j = i + 1
                    while j < len(raw_lines) and raw_lines[j].strip() == "":
                        j += 1
                    if j < len(raw_lines) and prev and prev[-1] not in ".!?;:":
                        i = j
                        continue
                    else:
                        paragraphs.append(buffer)
                        buffer = []
            else:
                buffer.append(line)

            i += 1

        if buffer:
            paragraphs.append(buffer)

        combined_paragraphs = []
        for para in paragraphs:
            sentences = []
            temp_line = ""
            for line in para:
                if temp_line:
                    if temp_line[-1] in ".!?;:":
                        sentences.append(temp_line)
                        temp_line = line
                    else:
                        temp_line += " " + line
                else:
                    temp_line = line
            if temp_line:
                sentences.append(temp_line)
            combined_paragraphs.append(sentences)

        return combined_paragraphs

    def preprocess_text(self, text):
        """Премахва или заменя проблемни символи преди превод."""
        return text.replace("|", "I")

    def _font_size(self):
        """Размерът на оригиналния шрифт, ако е поискан; 0 - ако не е или мерането гръмне."""
        if not self.detect_font_size:
            return 0
        try:
            size = FontSizeDetector(ocr_lang=self.ocr_lang).detect(self.gray_img, scale=OCR_UPSCALE)
            return size or 0  # None = не е измерен -> overlay-ят ползва размера от Настройки
        except Exception as e:
            logger.warning(f"Не успях да измеря размера на шрифта: {e}")
            return 0

    def run(self):
        try:
            try:
                text = pytesseract.image_to_string(self.gray_img, lang=self.ocr_lang)
            except Exception as e:
                self.failed_signal.emit("", "ocr_error", str(e))
                return

            raw_lines = [line.rstrip() for line in text.splitlines()]

            if not raw_lines or all(line.strip() == "" for line in raw_lines):
                self.failed_signal.emit("", "no_text_found", "")
                return

            combined_paragraphs = self.group_paragraphs(raw_lines)
            text_for_translation = "\n\n".join(
                "\n".join(sentences) for sentences in combined_paragraphs
            )
            text_for_translation = self.preprocess_text(text_for_translation)

            if not self.translator:
                self.failed_signal.emit(text_for_translation, "no_translator", "")
                return

            try:
                translated_text, from_cache, fallback_used = translate_with_cache(
                    self.translator, text_for_translation, self.target_lang, self.translation_cache
                )
            except Exception as e:
                self.failed_signal.emit(text_for_translation, *error_key_for(e))
                return
            self.finished_signal.emit(
                text_for_translation, translated_text, from_cache, fallback_used, self._font_size()
            )

        except Exception as e:
            self.failed_signal.emit("", "unexpected_error", str(e))


class TextTranslationThread(QThread):
    """
    Превод на готов текст (без OCR) във фонова нишка - за прозореца за
    превод на текст. request_id се връща обратно, за да може прозорецът да
    изхвърли закъснял резултат, ако междувременно текстът е променен.
    """

    # request_id, source_text, translated_text, from_cache, fallback_used ("" / "google" / "offline")
    finished_signal = pyqtSignal(int, str, str, bool, str)
    # request_id, error_key, detail
    failed_signal = pyqtSignal(int, str, str)

    def __init__(self, request_id, text, translator, target_lang, translation_cache=None):
        super().__init__()
        self.request_id = request_id
        self.text = text
        self.translator = translator
        self.target_lang = target_lang
        self.translation_cache = translation_cache

    def run(self):
        if not self.translator:
            self.failed_signal.emit(self.request_id, "no_translator", "")
            return
        try:
            translated, from_cache, fallback_used = translate_with_cache(
                self.translator, self.text, self.target_lang, self.translation_cache
            )
        except Exception as e:
            self.failed_signal.emit(self.request_id, *error_key_for(e))
            return
        self.finished_signal.emit(self.request_id, self.text, translated, from_cache, fallback_used)
