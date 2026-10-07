"""
PLAY/STOP TOGGLE FOR AUDIO PLAYBACK

This logic (start AudioThread / stop it / change the button icon) was
duplicated identically in MainWindow.start_play and
ui.components.SecondaryOverlay.toggle_audio. It is extracted here once;
both classes now just tell it which button to update.
"""

from core.audio_handler import AudioThread


class AudioPlaybackToggle:
    """
    Wraps a single AudioThread and toggles play/stop on each call to toggle().

    set_icon: callback(icon_filename: str), called with "play_button.png"
              or "stop_button.png" when the state changes.
    on_no_internet: optional callback(), called if edge-tts cannot be
                     reached (the service is online-only).
    """

    def __init__(self, set_icon, on_no_internet=None):
        self._set_icon = set_icon
        self._on_no_internet = on_no_internet
        self.audio_thread = None

    def is_playing(self):
        return self.audio_thread is not None and self.audio_thread.isRunning()

    def toggle(self, text, audio_lang, speed=1.0):
        if self.is_playing():
            self.stop()
        else:
            self.start(text, audio_lang, speed)

    def start(self, text, audio_lang, speed=1.0):
        if not text:
            return
        self.audio_thread = AudioThread(text, audio_lang, speed=speed)
        self.audio_thread.finished_signal.connect(self._on_finished)
        if self._on_no_internet:
            self.audio_thread.no_internet_signal.connect(self._on_no_internet)
        self.audio_thread.start()
        self._set_icon("stop_button.png")

    def stop(self):
        if not self.audio_thread:
            return
        self.audio_thread.stop()
        self.audio_thread.wait()
        self.audio_thread = None
        self._set_icon("play_button.png")

    def _on_finished(self):
        self._set_icon("play_button.png")
        if self.audio_thread:
            self.audio_thread.wait()
            self.audio_thread = None
