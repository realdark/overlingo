"""
ПРЕВОДНИ УСЛУГИ И КЕШИРАНЕ

Трите преводача (Google / DeepL / Microsoft) споделят общ интерфейс:
    translate(text, target_lang) -> str

Всички връщат директно текст (str), вместо отделен обект-обвивка
за всяка услуга - опростява извикващия код.
"""

import re

from utils.imports import QThread, pyqtSignal, requests, deepl, pytesseract
from utils.logging_setup import logger
from core.retry import retry_with_backoff
from core.network import has_internet_connection
from core.font_size_detector import FontSizeDetector
from core.capture import OCR_UPSCALE


class NoInternetError(Exception):
    """
    Хвърля се от облачните преводачи (Google/DeepL/Microsoft), ако няма
    никаква интернет връзка - за да се провали бързо, вместо да чака
    целия retry цикъл (~7s) напразно. Съобщението НЕ съдържа думи като
    "connection"/"timeout"/"429", за да не бъде сметнато за retryable от
    is_retryable_error() в core/retry.py - тук няма смисъл от нов опит.
    Ollama НЕ използва това - тя е локална, работи офлайн по дизайн.
    """
    pass


class OllamaUnavailableError(Exception):
    """Ollama не отговаря на зададения адрес (str(e) е адресът)."""
    pass


class OllamaEmptyResponseError(Exception):
    """Ollama отговори, но без превод - обикновено моделът не е изтеглен (str(e) е моделът)."""
    pass


def error_key_for(exc):
    """
    Грешка от преводач -> (ключ за текст в locales, технически детайл).
    Така съобщението към потребителя е на езика на интерфейса, а детайлът
    (напр. текстът на HTTP грешката) се показва след него.
    """
    if isinstance(exc, NoInternetError):
        return "no_internet", ""
    if isinstance(exc, OllamaUnavailableError):
        return "ollama_unavailable", str(exc)
    if isinstance(exc, OllamaEmptyResponseError):
        return "ollama_empty_response", str(exc)
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


class OllamaTranslator(BaseTranslator):
    """
    Локален превод чрез Ollama (напр. llama3.2, gemma2, qwen2.5) - работи
    офлайн, без ключ, без rate limit. Изисква Ollama да работи локално
    (`ollama serve`, по подразбиране на localhost:11434) с изтеглен модел
    (`ollama pull llama3.2`).
    """

    def __init__(self, model="llama3.2", base_url="http://localhost:11434"):
        self.model = model or "llama3.2"
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")

    def _request(self, text, target_lang):
        prompt = (
            f"Translate the following text to {target_lang}. "
            f"Output ONLY the translation itself, with no explanation, "
            f"quotes, or extra commentary:\n\n{text}"
        )
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=60,  # локалните модели могат да са бавни, особено при първо зареждане
        )
        response.raise_for_status()
        return response.json()

    def translate(self, text, target_lang):
        try:
            result = retry_with_backoff(
                lambda: self._request(text, target_lang), max_attempts=2, label="Ollama"
            )
        except requests.exceptions.ConnectionError:
            raise OllamaUnavailableError(self.base_url)
        except Exception as e:
            raise Exception(f"Ollama: {e}")

        translated = (result.get("response") or "").strip()
        if not translated:
            raise OllamaEmptyResponseError(self.model)
        return translated


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
    def __init__(self):
        self.cache = {}
        self.hits = 0
        self.misses = 0

    def get(self, text):
        normalized = self._normalize_text(text)
        if normalized in self.cache:
            self.hits += 1
            return self.cache[normalized]
        self.misses += 1
        return None

    def put(self, text, translation):
        normalized = self._normalize_text(text)
        self.cache[normalized] = translation

    def _normalize_text(self, text):
        if not text:
            return ""
        return " ".join(text.split()).strip().lower()

    def clear(self):
        """Изчиства целия кеш (статистиката hits/misses се запазва)."""
        self.cache.clear()


class FallbackTranslator(BaseTranslator):
    """
    Обвива основен преводач; ако той гръмне (след собствените си retry
    опити), автоматично пробва резервния (обикновено Google - безплатен,
    не изисква ключ, винаги достъпен). used_fallback показва дали
    последният translate() е минал през резервния преводач - вика се от
    TranslationThread, за да покаже съобщение на потребителя.
    """

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.used_fallback = False

    def translate(self, text, target_lang):
        self.used_fallback = False
        try:
            return self.primary.translate(text, target_lang)
        except Exception as e:
            if self.fallback is None:
                raise
            logger.warning(f"Основната услуга за превод се провали ({e}) - опитвам резервна (Google)")
            self.used_fallback = True
            return self.fallback.translate(text, target_lang)


# Съпоставя стойността от настройките (api_type) с конкретния клас преводач.
_TRANSLATOR_FACTORIES = {
    "google": lambda api_key, **kw: GoogleTranslator(),
    "deepl": lambda api_key, **kw: DeepLTranslator(api_key) if api_key else None,
    "microsoft": lambda api_key, **kw: MicrosoftTranslator(api_key) if api_key else None,
    "ollama": lambda api_key, **kw: OllamaTranslator(
        model=kw.get("ollama_model"), base_url=kw.get("ollama_url")
    ),
}

# api_type-ове, за които НЕ се добавя автоматичен fallback към Google:
# - "google" самото то е fallback-а, няма смисъл от себе-фолбек
# - "ollama" е нарочно избран за офлайн/приватен превод - тихо падане
#   към облачен Google би нарушило точно причината да избереш Ollama
_NO_AUTO_FALLBACK = {"google", "ollama"}


def create_translator(api_type, api_key=None, enable_fallback=True, **kwargs):
    """
    Фабрика: връща инстанция на подходящия BaseTranslator за api_type,
    или None ако няма нужния api_key (за deepl/microsoft).
    За "ollama" kwargs може да съдържа ollama_model/ollama_url.

    Ако enable_fallback=True и услугата не е в _NO_AUTO_FALLBACK,
    резултатът се обвива във FallbackTranslator с Google като резервен
    вариант (Google не изисква ключ, така че винаги може да послужи).
    """
    factory = _TRANSLATOR_FACTORIES.get(api_type)
    primary = factory(api_key, **kwargs) if factory else None
    if primary is None:
        return None
    if enable_fallback and api_type not in _NO_AUTO_FALLBACK:
        return FallbackTranslator(primary, GoogleTranslator())
    return primary


def translate_with_cache(translator, text, target_lang, cache=None):
    """
    Превежда text, като първо гледа в кеша. Връща
    (превод, от_кеша, през_резервната_услуга). Грешките от преводача се
    подават нагоре непроменени. Общо за превода от екрана и за прозореца
    за превод на текст.
    """
    cached = cache.get(text) if cache is not None else None
    if cached is not None:
        return cached, True, False
    translated = translator.translate(text, target_lang)
    used_fallback = getattr(translator, "used_fallback", False)
    if cache is not None:
        cache.put(text, translated)
    return translated, False, used_fallback


class TranslationThread(QThread):
    """Изпълнява OCR + превод във фонова нишка, за да не блокира UI-а."""

    # source_text, translated_text, from_cache, used_fallback,
    # font_size (размер на оригиналния шрифт в px; 0 = не е мерен)
    finished_signal = pyqtSignal(str, str, bool, bool, int)
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
                translated_text, from_cache, used_fallback = translate_with_cache(
                    self.translator, text_for_translation, self.target_lang, self.translation_cache
                )
            except Exception as e:
                self.failed_signal.emit(text_for_translation, *error_key_for(e))
                return
            self.finished_signal.emit(
                text_for_translation, translated_text, from_cache, used_fallback, self._font_size()
            )

        except Exception as e:
            self.failed_signal.emit("", "unexpected_error", str(e))


class TextTranslationThread(QThread):
    """
    Превод на готов текст (без OCR) във фонова нишка - за прозореца за
    превод на текст. request_id се връща обратно, за да може прозорецът да
    изхвърли закъснял резултат, ако междувременно текстът е променен.
    """

    # request_id, source_text, translated_text, from_cache, used_fallback
    finished_signal = pyqtSignal(int, str, str, bool, bool)
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
            translated, from_cache, used_fallback = translate_with_cache(
                self.translator, self.text, self.target_lang, self.translation_cache
            )
        except Exception as e:
            self.failed_signal.emit(self.request_id, *error_key_for(e))
            return
        self.finished_signal.emit(self.request_id, self.text, translated, from_cache, used_fallback)
