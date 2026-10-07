import unittest
from unittest import mock

from core import translations
from core.translations import (
    FallbackTranslator,
    GoogleTranslator,
    MicrosoftTranslator,
    TranslationCache,
    TranslationThread,
    create_translator,
)


class TranslationCacheTest(unittest.TestCase):
    def test_miss_then_hit(self):
        cache = TranslationCache()
        self.assertIsNone(cache.get("Hello", "BG"))
        cache.put("Hello", "Здравей", "BG")
        self.assertEqual(cache.get("Hello", "BG"), "Здравей")

    def test_whitespace_and_case_are_ignored(self):
        cache = TranslationCache()
        cache.put("Hello   World", "Здравей, свят", "BG")
        self.assertEqual(cache.get("  hello\nworld ", "bg"), "Здравей, свят")

    def test_target_language_is_part_of_the_key(self):
        cache = TranslationCache()
        cache.put("Hello", "Здравей", "BG")
        self.assertIsNone(cache.get("Hello", "DE"))  # otherwise the old translation shows after a language change

    def test_oldest_unused_entry_is_dropped(self):
        cache = TranslationCache(max_items=2)
        cache.put("a", "1", "BG")
        cache.put("b", "2", "BG")
        cache.get("a", "BG")          # "a" was used recently
        cache.put("c", "3", "BG")     # overflow - "b" is evicted
        self.assertEqual(cache.get("a", "BG"), "1")
        self.assertIsNone(cache.get("b", "BG"))
        self.assertEqual(len(cache.cache), 2)

    def test_clear(self):
        cache = TranslationCache()
        cache.put("a", "b", "BG")
        cache.clear()
        self.assertIsNone(cache.get("a", "BG"))


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
        self.assertEqual(translator.fallback_used, "")
        self.assertEqual(fallback.calls, 0)

    def test_switches_to_fallback_on_error(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), _Fixed("fallback"))
        self.assertEqual(translator.translate("x", "BG"), "fallback")
        self.assertEqual(translator.fallback_used, "google")

    def test_fallback_used_resets_on_next_call(self):
        primary = _Fixed(error=RuntimeError("down"))
        translator = FallbackTranslator(primary, _Fixed("fallback"))
        translator.translate("x", "BG")
        primary.error = None
        primary.result = "primary"
        translator.translate("x", "BG")
        self.assertEqual(translator.fallback_used, "")

    def test_without_fallback_error_is_raised(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), None)
        with self.assertRaises(RuntimeError):
            translator.translate("x", "BG")

    def test_no_internet_uses_offline_translation(self):
        offline, google = _Fixed("без интернет"), _Fixed("google")
        translator = FallbackTranslator(_Fixed(error=translations.NoInternetError("x")), google, offline)
        self.assertEqual(translator.translate("x", "BG"), "без интернет")
        self.assertEqual(translator.fallback_used, "offline")
        self.assertEqual(google.calls, 0)  # without internet Google wouldn't work either

    def test_no_internet_without_offline_models_reports_no_internet(self):
        offline = _Fixed(error=translations.ArgosModelMissingError("en → bg"))
        translator = FallbackTranslator(_Fixed(error=translations.NoInternetError("x")), _Fixed("g"), offline)
        with self.assertRaises(translations.NoInternetError):
            translator.translate("x", "BG")

    def test_other_errors_still_go_to_google(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("HTTP 500")), _Fixed("google"), _Fixed("offline"))
        self.assertEqual(translator.translate("x", "BG"), "google")
        self.assertEqual(translator.fallback_used, "google")

    def test_fallback_state_is_per_thread(self):
        import threading
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), _Fixed("google"))
        translator.translate("x", "BG")
        seen = []
        worker = threading.Thread(target=lambda: seen.append(translator.fallback_used))
        worker.start()
        worker.join()
        self.assertEqual(seen, [""])  # the other thread doesn't see this one's result
        self.assertEqual(translator.fallback_used, "google")


class CreateTranslatorTest(unittest.TestCase):
    def test_google_has_no_extra_fallback(self):
        with mock.patch.object(translations, "libraries_available", return_value=False):
            self.assertIsInstance(create_translator("google"), GoogleTranslator)

    def test_paid_service_without_key_gives_none(self):
        self.assertIsNone(create_translator("deepl", ""))
        self.assertIsNone(create_translator("microsoft", None))

    def test_paid_service_gets_google_fallback(self):
        translator = create_translator("microsoft", "key")
        self.assertIsInstance(translator, FallbackTranslator)
        self.assertIsInstance(translator.primary, MicrosoftTranslator)
        self.assertIsInstance(translator.fallback, GoogleTranslator)

    def test_offline_fallback_only_when_libraries_are_installed(self):
        with mock.patch.object(translations, "libraries_available", return_value=True):
            translator = create_translator("google", source_lang="de")
            self.assertIsInstance(translator.offline, translations.ArgosTranslator)
            self.assertEqual(translator.offline.source_lang, "de")
            self.assertIsNone(translator.fallback)  # Google doesn't fall back to itself
        with mock.patch.object(translations, "libraries_available", return_value=False):
            self.assertIsNone(create_translator("deepl", "key").offline)

    def test_fallback_can_be_disabled(self):
        self.assertIsInstance(create_translator("microsoft", "key", enable_fallback=False), MicrosoftTranslator)

    def test_offline_service_never_falls_back_to_cloud(self):
        translator = create_translator("argos", source_lang="en")
        self.assertIsInstance(translator, translations.ArgosTranslator)

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
        # Nothing is lost at the chunk boundaries.
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
                         ("Здравей", False, ""))
        self.assertEqual(cache.get("hello", "BG"), "Здравей")

    def test_second_call_comes_from_cache(self):
        cache, translator = TranslationCache(), _Fixed("Здравей")
        translations.translate_with_cache(translator, "Hello", "BG", cache)
        self.assertEqual(translations.translate_with_cache(translator, "Hello", "BG", cache),
                         ("Здравей", True, ""))
        self.assertEqual(translator.calls, 1)

    def test_reports_fallback(self):
        translator = FallbackTranslator(_Fixed(error=RuntimeError("down")), _Fixed("резерва"))
        self.assertEqual(translations.translate_with_cache(translator, "x", "BG"), ("резерва", False, "google"))

    def test_offline_translation_is_not_cached(self):
        cache = TranslationCache()
        translator = FallbackTranslator(_Fixed(error=translations.NoInternetError("x")), None, _Fixed("офлайн"))
        self.assertEqual(translations.translate_with_cache(translator, "x", "BG", cache), ("офлайн", False, "offline"))
        self.assertIsNone(cache.get("x", "BG"))

    def test_notice_keys(self):
        self.assertEqual(translations.fallback_notice_key("google"), "fallback_notice")
        self.assertEqual(translations.fallback_notice_key("offline"), "offline_notice")

    def test_errors_are_not_cached(self):
        cache = TranslationCache()
        with self.assertRaises(RuntimeError):
            translations.translate_with_cache(_Fixed(error=RuntimeError("down")), "x", "BG", cache)
        self.assertEqual(len(cache.cache), 0)


class ErrorKeyTest(unittest.TestCase):
    def test_known_errors_get_their_own_message(self):
        self.assertEqual(translations.error_key_for(translations.NoInternetError("x")), ("no_internet", ""))
        self.assertEqual(translations.error_key_for(translations.ArgosModelMissingError("en → bg")),
                         ("argos_model_missing", "en → bg"))
        self.assertEqual(translations.error_key_for(RuntimeError("HTTP 500")), ("translation_error", "HTTP 500"))


class FontSizeInThreadTest(unittest.TestCase):
    """Font size is measured in the background thread and only on request."""

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
