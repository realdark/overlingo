import unittest
from unittest import mock

from tests import _stubs  # noqa: F401 - stubs for Qt if it is missing
from core import system_tts
from core.system_tts import SystemSpeech, lcid_language, sapi_rate


class HelpersTest(unittest.TestCase):
    def test_lcid_language(self):
        self.assertEqual(lcid_language("402"), "bg")
        self.assertEqual(lcid_language("409;9"), "en")
        self.assertEqual(lcid_language("407"), "de")
        self.assertEqual(lcid_language(""), "")
        self.assertEqual(lcid_language("zz"), "")

    def test_sapi_rate(self):
        self.assertEqual(sapi_rate(1.0), 0)
        self.assertEqual(sapi_rate(3.0), 10)
        self.assertEqual(sapi_rate(2.0), 6)
        self.assertEqual(sapi_rate(0.5), -6)
        self.assertEqual(sapi_rate(100), 10)
        self.assertEqual(sapi_rate("bad"), 0)


class _FakeSapi:
    def __init__(self):
        self.voices = [("en", "Microsoft Zira Desktop", "zira"), ("bg", "Microsoft Ivan", "ivan")]
        self.spoken = []
        self.done = False
        self.stopped = False

    def find(self, language):
        for voice_language, name, token in self.voices:
            if voice_language == language:
                return name, token
        return None

    def speak(self, token, text, speed):
        self.spoken.append((token, text, speed))

    def is_done(self):
        return self.done

    def stop(self):
        self.stopped = True


class SapiSpeechTest(unittest.TestCase):
    def setUp(self):
        self.sapi = _FakeSapi()
        patcher = mock.patch.object(system_tts, "_load_sapi", return_value=self.sapi)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.speech = SystemSpeech()
        self.speech.finished = mock.Mock()
        self.speech._start_polling = mock.Mock()

    def test_onecore_voice_is_found(self):
        self.assertEqual(self.speech.voice_name("BG"), "Microsoft Ivan")
        self.assertEqual(self.speech.voice_name("EN-GB"), "Microsoft Zira Desktop")
        self.assertEqual(self.speech.voice_name("DE"), "")

    def test_speak_and_finish(self):
        self.assertTrue(self.speech.speak("Здравей", "BG", 1.5))
        self.assertEqual(self.sapi.spoken, [("ivan", "Здравей", 1.5)])
        self.assertTrue(self.speech.is_speaking())
        self.speech._check_done()
        self.speech.finished.emit.assert_not_called()
        self.sapi.done = True
        self.speech._check_done()
        self.assertFalse(self.speech.is_speaking())
        self.speech.finished.emit.assert_called_once()

    def test_no_voice_for_language(self):
        self.assertFalse(self.speech.speak("Hallo", "DE", 1.0))
        self.assertEqual(self.sapi.spoken, [])

    def test_stop(self):
        self.speech.speak("Здравей", "BG", 1.0)
        self.speech.stop()
        self.assertTrue(self.sapi.stopped)
        self.assertFalse(self.speech.is_speaking())
        self.speech.finished.emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
