"""
OFFLINE TEXT-TO-SPEECH WITH THE COMPUTER'S OWN VOICES (Qt TextToSpeech)

Uses the speech engine built into the operating system, through Qt:
  - Windows: SAPI voices (Settings -> Time & language -> Speech);
  - macOS:   the system voices (System Settings -> Accessibility -> Spoken Content);
  - Linux:   speech-dispatcher (usually with espeak-ng).
No internet and no extra download - but which languages can be read
depends on the voices installed on the computer. When there is no voice
for a language, core/audio_playback.py falls back to the online
Microsoft Edge voices (if there is internet).

QTextToSpeech is a QObject - it lives in the main (GUI) thread and speaks
asynchronously; say() returns immediately and stateChanged reports the end.
"""

from utils.imports import QtCore, pyqtSignal
from utils.logging_setup import logger


def _load_module():
    try:
        from PyQt5 import QtTextToSpeech
        return QtTextToSpeech
    except Exception as e:  # missing from the PyQt5 build, or a broken plugin
        logger.warning(f"Qt TextToSpeech is not available: {e}")
        return None


def language_of(target_lang):
    """Translation target code ("BG", "EN-US", "pt-BR") -> two-letter language ("bg", "en", "pt")."""
    return (target_lang or "").strip().replace("_", "-").split("-")[0].lower()


class SystemSpeech(QtCore.QObject):
    """
    One QTextToSpeech instance. finished is emitted when the text has been read
    (or reading was stopped / failed).
    """

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._module = _load_module()
        self._engine = None
        self._speaking = False

    def _tts(self):
        """Created lazily - the first creation loads the OS speech engine (can take a moment)."""
        if self._engine is None and self._module is not None:
            try:
                engine = self._module.QTextToSpeech(self)
                engine.stateChanged.connect(self._on_state_changed)
                self._engine = engine
            except Exception as e:
                logger.warning(f"Could not start the system speech engine: {e}")
                self._module = None
        return self._engine

    def available(self):
        return self._tts() is not None

    def voice_for(self, target_lang):
        """
        The (QLocale, QVoice) to read target_lang with, or None if the computer
        has no voice for that language.
        """
        engine = self._tts()
        language = language_of(target_lang)
        if engine is None or not language:
            return None
        try:
            locales = [loc for loc in engine.availableLocales() if loc.name().split("_")[0].lower() == language]
        except Exception as e:
            logger.warning(f"Could not list the system voices: {e}")
            return None
        # The engine's current locale first (usually the system language), then the rest.
        current = engine.locale()
        locales.sort(key=lambda loc: loc.name() != current.name())
        for locale in locales:
            engine.setLocale(locale)
            voices = list(engine.availableVoices())
            if voices:
                return locale, voices[0]
        return None

    def voice_name(self, target_lang):
        """Name of the voice for the language (for Settings), or "" if there is none."""
        found = self.voice_for(target_lang)
        return found[1].name() if found else ""

    def speak(self, text, target_lang, speed=1.0):
        """Starts reading. Returns False if there is no voice for the language (nothing is read)."""
        found = self.voice_for(target_lang)
        if not found or not text:
            return False
        locale, voice = found
        engine = self._engine
        engine.setLocale(locale)
        engine.setVoice(voice)
        # Qt rate: -1.0 (slowest) .. 0 (normal) .. 1.0 (fastest); the app's speed
        # is a multiplier like on YouTube (0.5x-2x).
        engine.setRate(max(-1.0, min(1.0, float(speed) - 1.0)))
        self._speaking = True
        engine.say(text)
        logger.info(f"Reading with the system voice {voice.name()} ({locale.name()})")
        return True

    def stop(self):
        if self._engine is not None and self._speaking:
            self._engine.stop()

    def is_speaking(self):
        return self._speaking

    def _on_state_changed(self, state):
        module = self._module
        if module is None:
            return
        if state == module.QTextToSpeech.Speaking:
            self._speaking = True
        elif self._speaking and state in (module.QTextToSpeech.Ready, module.QTextToSpeech.BackendError):
            if state == module.QTextToSpeech.BackendError:
                logger.warning("The system speech engine reported an error")
            self._speaking = False
            self.finished.emit()
