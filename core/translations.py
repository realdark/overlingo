"""
TRANSLATION SERVICES AND CACHING

The translators (Google / DeepL / Microsoft / offline Argos) share a common interface:
    translate(text, target_lang) -> str

All of them return plain text (str) directly instead of a separate wrapper object
per service - this simplifies the calling code.
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
    Raised by the cloud translators (Google/DeepL/Microsoft) when there is
    no internet connection at all - to fail fast instead of waiting through
    the whole retry cycle (~7s) for nothing. The message must NOT contain words like
    "connection"/"timeout"/"429", so that is_retryable_error() in core/retry.py
    doesn't treat it as retryable - a new attempt is pointless here.
    Argos (on-device translation) doesn't use this - it works offline by design.
    """
    pass


def error_key_for(exc):
    """
    Translator error -> (locale text key, technical detail).
    This way the user message is in the UI language, and the detail
    (e.g. the HTTP error text) is shown after it.
    """
    if isinstance(exc, NoInternetError):
        return "no_internet", ""
    if isinstance(exc, ArgosModelMissingError):
        return "argos_model_missing", str(exc)
    if isinstance(exc, ArgosNotInstalledError):
        return "argos_not_installed", str(exc)
    return "translation_error", str(exc)


class BaseTranslator:
    """Common interface for all text translators."""

    def translate(self, text, target_lang):
        raise NotImplementedError


class MicrosoftTranslator(BaseTranslator):
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://api.cognitive.microsofttranslator.com"

    def translate(self, text, target_lang):
        """Translates text via the Microsoft Translator API (with retry on 429/5xx)."""
        if not has_internet_connection():
            raise NoInternetError("No internet access - Microsoft Translator requires online access")

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
    """Google Translate via requests, with automatic splitting of long text."""

    MAX_CHUNK_LEN = 3000

    def __init__(self):
        self.endpoint = "https://translate.googleapis.com"
        self.session = requests.Session()

    def _split_text(self, text, max_len=None):
        """
        Splits the text into chunks of up to max_len characters, only at the end of
        a sentence (. ! ?). Each chunk keeps the whitespace that follows it,
        so "".join(chunks) gives exactly the original text - nothing is
        lost at the boundaries (previously ". " used to disappear there).
        A sentence longer than max_len stays whole in its own chunk.
        """
        max_len = max_len or self.MAX_CHUNK_LEN
        parts = re.split(r"(?<=[.!?])(\s+)", text)
        # parts = [sentence, whitespace, sentence, whitespace, ...]
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
        """Translates (possibly long) text via Google Translate (with retry on 429/5xx)."""
        if not has_internet_connection():
            raise NoInternetError("No internet access - Google Translate requires online access")

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
                # The whitespace between chunks (space or newline) is
                # restored, otherwise translations of adjacent chunks get glued together.
                translated_parts.append(chunk[len(chunk.rstrip()):])

            return "".join(translated_parts).rstrip()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Google Translate API error: {e}")
        except (IndexError, KeyError, TypeError) as e:
            raise Exception(f"Google Translate response parsing error: {e}")
        except Exception as e:
            raise Exception(f"Google Translate error: {e}")


class DeepLTranslator(BaseTranslator):
    """Thin wrapper around the official deepl library so it fits BaseTranslator."""

    def __init__(self, api_key):
        self._client = deepl.Translator(api_key)

    def translate(self, text, target_lang):
        if not has_internet_connection():
            raise NoInternetError("No internet access - DeepL requires online access")

        result = retry_with_backoff(
            lambda: self._client.translate_text(text, target_lang=target_lang),
            label="DeepL",
        )
        return result.text


class TranslationCache:
    """
    Already translated text -> translation, so the same request isn't sent again (on
    auto-refresh, "Translate again", identical text in the text window).
    The key is the text (ignoring whitespace and case differences) TOGETHER with
    the target language - otherwise the old translation showed up after changing the language.
    Keeps at most MAX_ITEMS entries; on overflow the least recently
    used one is dropped.
    """

    MAX_ITEMS = 500

    def __init__(self, max_items=MAX_ITEMS):
        self.max_items = max_items
        self.cache = OrderedDict()

    def get(self, text, target_lang=""):
        key = self._key(text, target_lang)
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)  # just used - dropped last
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
        """Clears the whole cache."""
        self.cache.clear()


class FallbackTranslator(BaseTranslator):
    """
    Wraps a primary translator with backup options:
        - no internet -> on-device translation (Argos), if the models are downloaded;
        - other error -> fallback (usually Google - free, no key).
    fallback_used tells what happened on the last translate():
    "" - the primary service, "google" - the fallback, "offline" - no internet.
    """

    def __init__(self, primary, fallback, offline=None):
        self.primary = primary
        self.fallback = fallback
        self.offline = offline
        # One translator is used by several threads at once (screen
        # translation + the text window) - each thread sees its own result.
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
                logger.info(f"No internet, and offline translation is not possible either: {offline_error}")
                raise NoInternetError("No internet access") from None
            logger.info("No internet - translated on this computer (Argos)")
            self.fallback_used = "offline"
            return result
        except Exception as e:
            if self.fallback is None:
                raise
            logger.warning(f"Primary translation service failed ({e}) - trying fallback (Google)")
            self.fallback_used = "google"
            return self.fallback.translate(text, target_lang)


# Maps the settings value (api_type) to a concrete translator class.
_TRANSLATOR_FACTORIES = {
    "google": lambda api_key, source_lang: GoogleTranslator(),
    "deepl": lambda api_key, source_lang: DeepLTranslator(api_key) if api_key else None,
    "microsoft": lambda api_key, source_lang: MicrosoftTranslator(api_key) if api_key else None,
    "argos": lambda api_key, source_lang: ArgosTranslator(source_lang or "en"),
}

# Online services that fall back to Google on error ("google" is itself the
# fallback; "argos" is a deliberately chosen offline translation).
_GOOGLE_FALLBACK = {"deepl", "microsoft"}


def create_translator(api_type, api_key=None, enable_fallback=True, source_lang="en"):
    """
    Factory: returns the appropriate translator for api_type, or None if the
    required api_key is missing (for deepl/microsoft).
    source_lang - the two-letter source language (for Argos, see
    core.argos.source_language).

    If enable_fallback=True, online services are wrapped in a
    FallbackTranslator: DeepL/Microsoft fall back to Google on error, and
    all online services - to on-device translation (Argos) if there is no
    internet and the models for the languages are downloaded.
    """
    factory = _TRANSLATOR_FACTORIES.get(api_type)
    primary = factory(api_key, source_lang) if factory else None
    if primary is None or not enable_fallback or api_type == "argos":
        return primary
    google = GoogleTranslator() if api_type in _GOOGLE_FALLBACK else None
    offline = ArgosTranslator(source_lang) if libraries_available() else None
    if google is None and offline is None:
        return primary  # nothing to fall back to
    return FallbackTranslator(primary, google, offline)


def fallback_notice_key(fallback_used):
    """The message key for the fallback translation ("google" / "offline")."""
    return "offline_notice" if fallback_used == "offline" else "fallback_notice"


def translate_with_cache(translator, text, target_lang, cache=None):
    """
    Translates text, checking the cache first. Returns
    (translation, from_cache, fallback), where fallback is ""
    (the primary service), "google" or "offline" (see FallbackTranslator).
    Translator errors are propagated unchanged. Shared by screen
    translation and the text translation window.
    """
    cached = cache.get(text, target_lang) if cache is not None else None
    if cached is not None:
        return cached, True, ""
    translated = translator.translate(text, target_lang)
    fallback_used = getattr(translator, "fallback_used", "")
    # Offline translation (when there is no internet) is not cached - once the internet
    # is back, the same text should go through the better online service again.
    if cache is not None and fallback_used != "offline":
        cache.put(text, translated, target_lang)
    return translated, False, fallback_used


class TranslationThread(QThread):
    """Runs OCR + translation in a background thread so as not to block the UI."""

    # source_text, translated_text, from_cache, fallback_used ("" / "google" / "offline"),
    # font_size (original font size in px; 0 = not measured)
    finished_signal = pyqtSignal(str, str, bool, str, int)
    # source_text (may be empty), error_key (translation key in locales), detail
    failed_signal = pyqtSignal(str, str, str)

    def __init__(self, gray_img, ocr_lang, translator, target_lang, translation_cache=None,
                 detect_font_size=False):
        """
        detect_font_size: whether to also measure the font size (a second
        Tesseract pass) - only when the overlay is yet to be
        created. Done here, in the background thread, so the UI doesn't freeze.
        """
        super().__init__()
        self.detect_font_size = detect_font_size
        self.gray_img = gray_img
        self.ocr_lang = ocr_lang
        self.translator = translator  # BaseTranslator or None
        self.target_lang = target_lang
        self.translation_cache = translation_cache

    def group_paragraphs(self, raw_lines):
        """
        Groups OCR lines into paragraphs and sentences.
        Returns a list of paragraphs, where each paragraph is a list of sentences.

        - Blank line = new paragraph, unless the previous line has no terminal punctuation (.!?;:)
            → in that case the blank line is ignored and the following text is joined on.
        - Within a paragraph, lines are joined until terminal punctuation is reached.
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
        """Removes or replaces problematic characters before translation."""
        return text.replace("|", "I")

    def _font_size(self):
        """The original font size, if requested; 0 if not, or if measuring fails."""
        if not self.detect_font_size:
            return 0
        try:
            size = FontSizeDetector(ocr_lang=self.ocr_lang).detect(self.gray_img, scale=OCR_UPSCALE)
            return size or 0  # None = not measured -> the overlay uses the size from Settings
        except Exception as e:
            logger.warning(f"Could not measure the font size: {e}")
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
    Translation of ready text (no OCR) in a background thread - for the text
    translation window. request_id is passed back so the window can
    discard a late result if the text has changed in the meantime.
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
