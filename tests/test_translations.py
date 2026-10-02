import unittest
from unittest import mock

from core import translations
from core.translations import (
    FallbackTranslator,
    GoogleTranslator,
    MicrosoftTranslator,
    OllamaTranslator,
    TranslationCache,
    TranslationThread,
    create_translator,
)


class TranslationCacheTest(unittest.TestCase):
    def test_miss_then_hit(self):
        cache = TranslationCache()
        self.assertIsNone(cache.get("Hello"))
        cache.put("Hello", "Здравей")
        self.assertEqual(cache.get("Hello"), "Здравей")
        self.assertEqual((cache.hits, cache.misses), (1, 1))

    def test_whitespace_and_case_are_ignored(self):
        cache = TranslationCache()
        cache.put("Hello   World", "Здравей, свят")
        self.assertEqual(cache.get("  hello\nworld "), "Здравей, свят")

    def test_clear(self):
        cache = TranslationCache()
        cache.put("a", "b")
        cache.clear()
        self.assertIsNone(cache.get("a"))


class _Fixed:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def translate(self, text, target_lang):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FallbackTranslatorTest(unittest.TestCase):
    def test_uses_primary_when_it_works(self):
        primary, fallback = _Fixed("primary"), _Fixed("fallback")
        translator = FallbackTranslator(primary, fallback)
        self.assertEqual(translator.translate("x", "BG"), "primary")
        self.assertFalse(translator.used_fallback)
        self.assertEqual(fallback.calls, 0)

    def test_switches_to_fallback_on_error(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), _Fixed("fallback"))
        self.assertEqual(translator.translate("x", "BG"), "fallback")
        self.assertTrue(translator.used_fallback)

    def test_used_fallback_resets_on_next_call(self):
        primary = _Fixed(error=RuntimeError("down"))
        translator = FallbackTranslator(primary, _Fixed("fallback"))
        translator.translate("x", "BG")
        primary.error = None
        primary.result = "primary"
        translator.translate("x", "BG")
        self.assertFalse(translator.used_fallback)

    def test_without_fallback_error_is_raised(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), None)
        with self.assertRaises(RuntimeError):
            translator.translate("x", "BG")


class CreateTranslatorTest(unittest.TestCase):
    def test_google_has_no_extra_fallback(self):
        self.assertIsInstance(create_translator("google"), GoogleTranslator)

    def test_paid_service_without_key_gives_none(self):
        self.assertIsNone(create_translator("deepl", ""))
        self.assertIsNone(create_translator("microsoft", None))

    def test_paid_service_gets_google_fallback(self):
        translator = create_translator("microsoft", "key")
        self.assertIsInstance(translator, FallbackTranslator)
        self.assertIsInstance(translator.primary, MicrosoftTranslator)
        self.assertIsInstance(translator.fallback, GoogleTranslator)

    def test_fallback_can_be_disabled(self):
        self.assertIsInstance(create_translator("microsoft", "key", enable_fallback=False), MicrosoftTranslator)

    def test_ollama_never_falls_back_to_cloud(self):
        translator = create_translator("ollama", ollama_model="qwen", ollama_url="http://host:1/")
        self.assertIsInstance(translator, OllamaTranslator)
        self.assertEqual(translator.model, "qwen")
        self.assertEqual(translator.base_url, "http://host:1")

    def test_unknown_service_gives_none(self):
        self.assertIsNone(create_translator("nope"))


class GoogleSplitTextTest(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(GoogleTranslator()._split_text("One. Two."), ["One. Two."])

    def test_long_text_keeps_every_sentence(self):
        sentences = [f"Sentence number {i} is here." for i in range(40)]
        text = " ".join(sentences)
        chunks = GoogleTranslator()._split_text(text, max_len=120)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.rstrip()) <= 120 for c in chunks))
        # Нищо не се губи на границите между парчетата.
        self.assertEqual("".join(chunks), text)

    def test_newlines_are_kept(self):
        text = "First paragraph.\n\nSecond paragraph."
        self.assertEqual("".join(GoogleTranslator()._split_text(text, max_len=20)), text)


class _GoogleResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class GoogleTranslateTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(translations, "has_internet_connection", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_joins_segments(self):
        translator = GoogleTranslator()
        translator.session = mock.Mock()
        translator.session.get.return_value = _GoogleResponse([[["Здравей. ", "Hello. "], ["Свят.", "World."]]])
        self.assertEqual(translator.translate("Hello. World.", "BG"), "Здравей. Свят.")
        params = translator.session.get.call_args.kwargs["params"]
        self.assertEqual(params["tl"], "bg")

    def test_chunks_are_separated_in_result(self):
        translator = GoogleTranslator()
        translator.session = mock.Mock()
        translator.session.get.side_effect = [
            _GoogleResponse([[["Първо.", "First."]]]),
            _GoogleResponse([[["Второ.", "Second."]]]),
        ]
        with mock.patch.object(GoogleTranslator, "_split_text", return_value=["First. ", "Second."]):
            self.assertEqual(translator.translate("First. Second.", "BG"), "Първо. Второ.")

    def test_no_internet_fails_fast(self):
        with mock.patch.object(translations, "has_internet_connection", return_value=False):
            with self.assertRaises(translations.NoInternetError):
                GoogleTranslator().translate("Hello", "BG")


class TranslateWithCacheTest(unittest.TestCase):
    def test_first_call_translates_and_fills_cache(self):
        cache, translator = TranslationCache(), _Fixed("Здравей")
        self.assertEqual(translations.translate_with_cache(translator, "Hello", "BG", cache),
                         ("Здравей", False, False))
        self.assertEqual(cache.get("hello"), "Здравей")

    def test_second_call_comes_from_cache(self):
        cache, translator = TranslationCache(), _Fixed("Здравей")
        translations.translate_with_cache(translator, "Hello", "BG", cache)
        self.assertEqual(translations.translate_with_cache(translator, "Hello", "BG", cache),
                         ("Здравей", True, False))
        self.assertEqual(translator.calls, 1)

    def test_reports_fallback(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), _Fixed("резерва"))
        self.assertEqual(translations.translate_with_cache(translator, "x", "BG"), ("резерва", False, True))

    def test_errors_are_not_cached(self):
        cache = TranslationCache()
        with self.assertRaises(RuntimeError):
            translations.translate_with_cache(_Fixed(error=RuntimeError("down")), "x", "BG", cache)
        self.assertEqual(cache.cache, {})


class ErrorKeyTest(unittest.TestCase):
    def test_known_errors_get_their_own_message(self):
        self.assertEqual(translations.error_key_for(translations.NoInternetError("x")), ("no_internet", ""))
        self.assertEqual(translations.error_key_for(translations.OllamaUnavailableError("http://h:1")),
                         ("ollama_unavailable", "http://h:1"))
        self.assertEqual(translations.error_key_for(RuntimeError("HTTP 500")), ("translation_error", "HTTP 500"))

    def test_ollama_not_running(self):
        with mock.patch.object(translations.requests, "post",
                               side_effect=translations.requests.exceptions.ConnectionError("refused")), \
             mock.patch("core.retry.time.sleep"):
            with self.assertRaises(translations.OllamaUnavailableError):
                OllamaTranslator().translate("Hello", "BG")

    def test_ollama_empty_answer(self):
        response = mock.Mock()
        response.json.return_value = {"response": "  "}
        with mock.patch.object(translations.requests, "post", return_value=response):
            with self.assertRaises(translations.OllamaEmptyResponseError):
                OllamaTranslator(model="tiny").translate("Hello", "BG")


class FontSizeInThreadTest(unittest.TestCase):
    """Размерът на шрифта се мери във фоновата нишка и само при поискване."""

    def _thread(self, detect):
        return TranslationThread(gray_img=object(), ocr_lang="eng", translator=None,
                                 target_lang="BG", detect_font_size=detect)

    def test_not_measured_unless_asked(self):
        with mock.patch.object(translations, "FontSizeDetector") as detector:
            self.assertEqual(self._thread(False)._font_size(), 0)
        detector.assert_not_called()

    def test_measured_when_asked(self):
        with mock.patch.object(translations, "FontSizeDetector") as detector:
            detector.return_value.detect.return_value = 18
            self.assertEqual(self._thread(True)._font_size(), 18)

    def test_failure_falls_back_to_zero(self):
        with mock.patch.object(translations, "FontSizeDetector") as detector:
            detector.return_value.detect.side_effect = RuntimeError("tesseract")
            self.assertEqual(self._thread(True)._font_size(), 0)


class GroupParagraphsTest(unittest.TestCase):
    group = staticmethod(lambda lines: TranslationThread.group_paragraphs(None, lines))

    def test_lines_are_joined_until_sentence_end(self):
        self.assertEqual(self.group(["This is", "one sentence.", "Next one."]),
                         [["This is one sentence.", "Next one."]])

    def test_blank_line_after_sentence_starts_new_paragraph(self):
        self.assertEqual(self.group(["First.", "", "Second."]), [["First."], ["Second."]])

    def test_blank_line_inside_sentence_is_ignored(self):
        self.assertEqual(self.group(["Broken", "", "sentence."]), [["Broken sentence."]])


if __name__ == "__main__":
    unittest.main()
