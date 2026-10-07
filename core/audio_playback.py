"""
PLAY/STOP TOGGLE FOR AUDIO PLAYBACK

Shared by every play button (toolbar, overlay, history and text windows):
starts reading with the chosen engine, stops it on the next click and keeps
the button icon in sync.

Engines (Settings -> Audio -> "Reading voice"):
  - "system" (default): the computer's own voices, offline (core/system_tts.py).
    If the computer has no voice for the language, it falls back to the online
    Edge voice - when there is internet - and says so.
  - "edge": Microsoft Edge neural voices via edge-tts (online, core/audio_handler.py).
"""

from collections import namedtuple

from core.audio_handler import AudioThread
from core.network import has_internet_connection
from core.system_tts import SystemSpeech, language_of

ENGINE_SYSTEM = "system"
ENGINE_EDGE = "edge"

# What to read with: engine, Edge voice ("" = automatic by language), speed
# (0.5-2.0) and the language of the text (the translation target, e.g. "BG").
AudioOptions = namedtuple("AudioOptions", "engine voice speed language")

# Default Edge voice per language, used when no voice is chosen in Settings
# (the voice field is empty) or the chosen one is for another language.
DEFAULT_EDGE_VOICES = {
    "ar": "ar-SA-ZariyahNeural", "bg": "bg-BG-KalinaNeural", "cs": "cs-CZ-VlastaNeural",
    "da": "da-DK-ChristelNeural", "de": "de-DE-KatjaNeural", "el": "el-GR-AthinaNeural",
    "en": "en-US-AriaNeural", "es": "es-ES-ElviraNeural", "et": "et-EE-AnuNeural",
    "fi": "fi-FI-NooraNeural", "fr": "fr-FR-DeniseNeural", "he": "he-IL-HilaNeural",
    "hi": "hi-IN-SwaraNeural", "hr": "hr-HR-GabrijelaNeural", "hu": "hu-HU-NoemiNeural",
    "id": "id-ID-GadisNeural", "it": "it-IT-ElsaNeural", "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural", "lt": "lt-LT-OnaNeural", "lv": "lv-LV-EveritaNeural",
    "mk": "mk-MK-MarijaNeural", "nb": "nb-NO-PernilleNeural", "nl": "nl-NL-ColetteNeural",
    "no": "nb-NO-PernilleNeural", "pl": "pl-PL-ZofiaNeural", "pt": "pt-PT-RaquelNeural",
    "ro": "ro-RO-AlinaNeural", "ru": "ru-RU-SvetlanaNeural", "sk": "sk-SK-ViktoriaNeural",
    "sl": "sl-SI-PetraNeural", "sr": "sr-RS-SophieNeural", "sv": "sv-SE-SofieNeural",
    "tr": "tr-TR-EmelNeural", "uk": "uk-UA-PolinaNeural", "zh": "zh-CN-XiaoxiaoNeural",
}


def edge_voice_for(options):
    """
    The Edge voice to use: the one chosen in Settings if it is for the same
    language as the text, otherwise the default for the language ("" if none).
    """
    language = language_of(options.language)
    chosen = (options.voice or "").strip()
    if chosen and (not language or chosen.lower().startswith(language + "-")):
        return chosen
    return DEFAULT_EDGE_VOICES.get(language, chosen)


class AudioPlaybackToggle:
    """
    toggle(text, options) - starts reading, or stops it if already reading.

    set_icon:  callback(icon_filename), called with "play_button.png" or
               "stop_button.png" when the state changes.
    on_notice: optional callback(message_key) for things the user should know:
               "audio_requires_internet" (Edge voice, no internet),
               "tts_fallback_online" (no voice on this computer - reading online),
               "tts_no_voice" (no voice on this computer and no internet),
               "no_audio_lang" (no Edge voice for the language).
    """

    def __init__(self, set_icon, on_notice=None):
        self._set_icon = set_icon
        self._on_notice = on_notice
        self.audio_thread = None
        self._system = None

    def _notify(self, key):
        if self._on_notice:
            self._on_notice(key)

    def is_playing(self):
        edge = self.audio_thread is not None and self.audio_thread.isRunning()
        return edge or (self._system is not None and self._system.is_speaking())

    def toggle(self, text, options):
        if self.is_playing():
            self.stop()
        else:
            self.start(text, options)

    def start(self, text, options):
        if not text:
            return
        if options.engine != ENGINE_EDGE:
            if self._system is None:
                self._system = SystemSpeech()
                self._system.finished.connect(self._on_finished)
            if self._system.speak(text, options.language, options.speed):
                self._set_icon("stop_button.png")
                return
            # No voice for this language on the computer - online Edge voice, if possible.
            if not has_internet_connection():
                self._notify("tts_no_voice")
                return
            self._notify("tts_fallback_online")
        self._start_edge(text, options)

    def _start_edge(self, text, options):
        voice = edge_voice_for(options)
        if not voice:
            self._notify("no_audio_lang")
            return
        self.audio_thread = AudioThread(text, voice, speed=options.speed)
        self.audio_thread.finished_signal.connect(self._on_finished)
        self.audio_thread.no_internet_signal.connect(lambda: self._notify("audio_requires_internet"))
        self.audio_thread.start()
        self._set_icon("stop_button.png")

    def stop(self):
        if self._system is not None:
            self._system.stop()
        if self.audio_thread:
            self.audio_thread.stop()
            self.audio_thread.wait()
            self.audio_thread = None
        self._set_icon("play_button.png")

    def _on_finished(self):
        self._set_icon("play_button.png")
        if self.audio_thread:
            self.audio_thread.wait()
            self.audio_thread = None
