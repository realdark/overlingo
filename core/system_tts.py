"""
OFFLINE TEXT-TO-SPEECH WITH THE COMPUTER'S OWN VOICES

Uses the speech engine built into the operating system:
  - Windows: SAPI directly (pywin32), with BOTH kinds of installed voices:
      * the classic SAPI5 voices, and
      * the "OneCore" voices added in Settings -> Time & language -> Speech
        or Language -> "Text-to-speech" / Narrator (e.g. "Microsoft Ivan" -
        Bulgarian). Qt's own SAPI plugin does not see these, which is why
        Windows doesn't go through Qt (it is only the fallback without pywin32);
  - macOS:   the system voices through Qt (Accessibility -> Spoken Content);
  - Linux:   speech-dispatcher through Qt (usually with espeak-ng).
No internet and no extra download - but which languages can be read
depends on the voices installed on the computer. When there is no voice
for a language, core/audio_playback.py falls back to the online
Microsoft Edge voices (if there is internet).

Both engines live in the main (GUI) thread and speak asynchronously:
speak() returns immediately and `finished` reports the end.
"""

import locale
import math
import sys

from utils.imports import QtCore, pyqtSignal
from utils.logging_setup import logger

# Where Windows keeps the OneCore voices (Settings -> Speech / Narrator).
ONECORE_VOICES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"

# SpVoice.Speak flags
_SVSF_ASYNC = 1
_SVSF_PURGE = 2
_SVSF_NOT_XML = 16  # read "<" and "&" as text, not as SAPI XML

_POLL_MS = 200


def language_of(target_lang):
    """Translation target code ("BG", "EN-US", "pt-BR") -> two-letter language ("bg", "en", "pt")."""
    return (target_lang or "").strip().replace("_", "-").split("-")[0].lower()


def lcid_language(attribute):
    """
    SAPI "Language" attribute -> two-letter language, "" if unknown.
    The attribute is one or more hex LCIDs separated by ";": "402" -> "bg",
    "409;9" -> "en".
    """
    for part in (attribute or "").split(";"):
        try:
            name = locale.windows_locale.get(int(part.strip(), 16), "")
        except ValueError:
            continue
        if name:
            return language_of(name)
    return ""


def sapi_rate(speed):
    """App speed multiplier (0.5x-2x) -> SAPI rate (-10..10, 0 = normal, +10 is about 3x)."""
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return 0
    if speed <= 0:
        return 0
    return max(-10, min(10, round(10 * math.log(speed) / math.log(3))))


# ----------------------------------------------------------------------
# Windows: SAPI via pywin32
# ----------------------------------------------------------------------

class _SapiEngine:
    """SAPI SpVoice with the classic and the OneCore voices. Raises if SAPI isn't usable."""

    def __init__(self):
        import pythoncom
        from win32com.client import dynamic

        try:
            pythoncom.CoInitialize()  # already done by Qt in the GUI thread - harmless then
        except pythoncom.com_error:
            pass
        self._dispatch = dynamic.Dispatch
        self.voice = dynamic.Dispatch("SAPI.SpVoice")
        self.voices = self._list_voices()  # [(language, name, token)]

    def _tokens(self):
        try:
            yield from self._each(self.voice.GetVoices())
        except Exception as e:
            logger.warning(f"Could not list the SAPI voices: {e}")
        try:
            category = self._dispatch("SAPI.SpObjectTokenCategory")
            category.SetId(ONECORE_VOICES, False)
            yield from self._each(category.EnumerateTokens())
        except Exception as e:  # older Windows without OneCore voices
            logger.info(f"No OneCore voices: {e}")

    @staticmethod
    def _each(tokens):
        for i in range(tokens.Count):
            yield tokens.Item(i)

    def _list_voices(self):
        voices, seen = [], set()
        for token in self._tokens():
            try:
                name = token.GetAttribute("Name") or token.GetDescription()
                language = lcid_language(token.GetAttribute("Language"))
            except Exception:
                continue
            if name and name not in seen:  # some voices are registered in both places
                seen.add(name)
                voices.append((language, name, token))
        logger.info("Windows voices: " + (", ".join(f"{n} ({l or '?'})" for l, n, _ in voices) or "none"))
        return voices

    def find(self, language):
        for voice_language, name, token in self.voices:
            if voice_language == language:
                return name, token
        return None

    def speak(self, token, text, speed):
        self.voice.Voice = token
        self.voice.Rate = sapi_rate(speed)
        self.voice.Speak(text, _SVSF_ASYNC | _SVSF_NOT_XML)

    def is_done(self):
        return bool(self.voice.WaitUntilDone(0))

    def stop(self):
        self.voice.Speak("", _SVSF_ASYNC | _SVSF_PURGE)


def _load_sapi():
    if sys.platform != "win32":
        return None
    try:
        return _SapiEngine()
    except Exception as e:  # no pywin32 or broken SAPI - Qt's engine is the fallback
        logger.warning(f"SAPI (pywin32) is not available, using Qt TextToSpeech: {e}")
        return None


def _load_qt_module():
    try:
        from PyQt5 import QtTextToSpeech
        return QtTextToSpeech
    except Exception as e:  # missing from the PyQt5 build, or a broken plugin
        logger.warning(f"Qt TextToSpeech is not available: {e}")
        return None


class SystemSpeech(QtCore.QObject):
    """
    Reads with the computer's voices. finished is emitted when the text has
    been read (or reading was stopped / failed).
    """

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sapi = _load_sapi()
        self._module = None if self._sapi else _load_qt_module()
        self._engine = None
        self._speaking = False
        self._poll = None

    # -- Qt engine (macOS, Linux, Windows without pywin32) -----------------

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

    def _qt_voice_for(self, language):
        engine = self._tts()
        if engine is None:
            return None
        try:
            locales = [loc for loc in engine.availableLocales() if loc.name().split("_")[0].lower() == language]
        except Exception as e:
            logger.warning(f"Could not list the system voices: {e}")
            return None
        # The engine's current locale first (usually the system language), then the rest.
        current = engine.locale()
        locales.sort(key=lambda loc: loc.name() != current.name())
        for loc in locales:
            engine.setLocale(loc)
            voices = list(engine.availableVoices())
            if voices:
                return loc, voices[0]
        return None

    # -- common ------------------------------------------------------------

    def available(self):
        return self._sapi is not None or self._tts() is not None

    def voice_for(self, target_lang):
        """
        Which voice reads target_lang: ("sapi", name, token) or ("qt", locale, voice),
        None if the computer has no voice for that language.
        """
        language = language_of(target_lang)
        if not language:
            return None
        if self._sapi is not None:
            found = self._sapi.find(language)
            return ("sapi",) + found if found else None
        found = self._qt_voice_for(language)
        return ("qt",) + found if found else None

    def voice_name(self, target_lang):
        """Name of the voice for the language (for Settings), or "" if there is none."""
        found = self.voice_for(target_lang)
        if not found:
            return ""
        return found[1] if found[0] == "sapi" else found[2].name()

    def speak(self, text, target_lang, speed=1.0):
        """Starts reading. Returns False if there is no voice for the language (nothing is read)."""
        found = self.voice_for(target_lang) if text else None
        if not found:
            return False
        if found[0] == "sapi":
            _, name, token = found
            try:
                self._sapi.speak(token, text, speed)
            except Exception as e:
                logger.warning(f"SAPI could not read with {name}: {e}")
                return False
            self._speaking = True
            self._start_polling()
            logger.info(f"Reading with the system voice {name}")
            return True

        _, loc, voice = found
        engine = self._engine
        engine.setLocale(loc)
        engine.setVoice(voice)
        # Qt rate: -1.0 (slowest) .. 0 (normal) .. 1.0 (fastest); the app's speed
        # is a multiplier like on YouTube (0.5x-2x).
        engine.setRate(max(-1.0, min(1.0, float(speed) - 1.0)))
        self._speaking = True
        engine.say(text)
        logger.info(f"Reading with the system voice {voice.name()} ({loc.name()})")
        return True

    def stop(self):
        if not self._speaking:
            return
        if self._sapi is not None:
            try:
                self._sapi.stop()
            except Exception as e:
                logger.warning(f"SAPI could not stop: {e}")
            self._finish()
        elif self._engine is not None:
            self._engine.stop()

    def is_speaking(self):
        return self._speaking

    def _finish(self):
        if self._poll is not None:
            self._poll.stop()
        if self._speaking:
            self._speaking = False
            self.finished.emit()

    # SAPI reports the end through COM events; checking every 200 ms is simpler
    # and needs no event sink.
    def _start_polling(self):
        if self._poll is None:
            self._poll = QtCore.QTimer(self)
            self._poll.setInterval(_POLL_MS)
            self._poll.timeout.connect(self._check_done)
        self._poll.start()

    def _check_done(self):
        try:
            done = self._sapi.is_done()
        except Exception as e:
            logger.warning(f"SAPI error: {e}")
            done = True
        if done:
            self._finish()

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

