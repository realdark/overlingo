import unittest
from unittest import mock

from core import audio_playback
from core.audio_playback import AudioOptions, AudioPlaybackToggle, edge_voice_for
from core.system_tts import language_of


class LanguageTest(unittest.TestCase):
    def test_language_of_target_codes(self):
        self.assertEqual(language_of("BG"), "bg")
        self.assertEqual(language_of("EN-US"), "en")
        self.assertEqual(language_of("pt_BR"), "pt")
        self.assertEqual(language_of(""), "")


class EdgeVoiceTest(unittest.TestCase):
    def test_automatic_voice_by_language(self):
        self.assertEqual(edge_voice_for(AudioOptions("edge", "", 1.0, "BG")), "bg-BG-KalinaNeural")
        self.assertEqual(edge_voice_for(AudioOptions("edge", "", 1.0, "EN-GB")), "en-US-AriaNeural")

    def test_chosen_voice_wins_when_it_matches_the_language(self):
        self.assertEqual(edge_voice_for(AudioOptions("edge", "bg-BG-BorislavNeural", 1.0, "BG")), "bg-BG-BorislavNeural")

    def test_chosen_voice_for_another_language_is_replaced(self):
        # Translating to German with a Bulgarian voice chosen would read German with a Bulgarian accent.
        self.assertEqual(edge_voice_for(AudioOptions("edge", "bg-BG-BorislavNeural", 1.0, "DE")), "de-DE-KatjaNeural")

    def test_unknown_language_keeps_the_chosen_voice_or_nothing(self):
        self.assertEqual(edge_voice_for(AudioOptions("edge", "", 1.0, "XX")), "")


class _FakeSpeech:
    def __init__(self, has_voice):
        self.has_voice = has_voice
        self.spoken = []
        self.finished = mock.Mock()

    def speak(self, text, language, speed):
        if self.has_voice:
            self.spoken.append((text, language, speed))
        return self.has_voice

    def is_speaking(self):
        return bool(self.spoken)

    def stop(self):
        pass


class ToggleTest(unittest.TestCase):
    def _toggle(self, has_voice, internet=True):
        self.icons, self.notices = [], []
        speech = _FakeSpeech(has_voice)
        patches = [
            mock.patch.object(audio_playback, "SystemSpeech", return_value=speech),
            mock.patch.object(audio_playback, "has_internet_connection", return_value=internet),
            mock.patch.object(audio_playback, "AudioThread"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.edge_thread = audio_playback.AudioThread
        toggle = AudioPlaybackToggle(set_icon=self.icons.append, on_notice=self.notices.append)
        return toggle, speech

    def test_system_voice_reads_offline(self):
        toggle, speech = self._toggle(has_voice=True)
        toggle.start("Здравей", AudioOptions("system", "", 1.25, "BG"))
        self.assertEqual(speech.spoken, [("Здравей", "BG", 1.25)])
        self.assertEqual(self.icons, ["stop_button.png"])
        self.edge_thread.assert_not_called()
        self.assertEqual(self.notices, [])

    def test_no_system_voice_falls_back_to_edge_with_notice(self):
        toggle, _ = self._toggle(has_voice=False, internet=True)
        toggle.start("Hallo", AudioOptions("system", "", 1.0, "DE"))
        self.assertEqual(self.notices, ["tts_fallback_online"])
        self.edge_thread.assert_called_once_with("Hallo", "de-DE-KatjaNeural", speed=1.0)

    def test_no_system_voice_and_no_internet(self):
        toggle, _ = self._toggle(has_voice=False, internet=False)
        toggle.start("Hallo", AudioOptions("system", "", 1.0, "DE"))
        self.assertEqual(self.notices, ["tts_no_voice"])
        self.edge_thread.assert_not_called()
        self.assertEqual(self.icons, [])

    def test_edge_engine_skips_system_voices(self):
        toggle, speech = self._toggle(has_voice=True)
        toggle.start("Hello", AudioOptions("edge", "", 1.0, "EN"))
        self.assertEqual(speech.spoken, [])
        self.edge_thread.assert_called_once_with("Hello", "en-US-AriaNeural", speed=1.0)

    def test_empty_text_does_nothing(self):
        toggle, speech = self._toggle(has_voice=True)
        toggle.start("", AudioOptions("system", "", 1.0, "BG"))
        self.assertEqual((speech.spoken, self.icons), ([], []))


if __name__ == "__main__":
    unittest.main()
