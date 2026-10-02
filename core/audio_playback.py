"""
ПРЕВКЛЮЧВАНЕ ПУСНИ/СПРИ ЗА АУДИО ВЪЗПРОИЗВЕЖДАНЕ

Тази логика (стартирай AudioThread / спри го / смени иконата на бутона)
се повтаряше идентично в MainWindow.start_play и
ui.components.SecondaryOverlay.toggle_audio. Извадена е тук веднъж,
двата класа вече само й подават кой бутон да оцветят.
"""

from core.audio_handler import AudioThread


class AudioPlaybackToggle:
    """
    Обвива един AudioThread и превключва play/stop при всяко извикване на toggle().

    set_icon: callback(icon_filename: str), извиква се с "play_button.png"
              или "stop_button.png" при промяна на състоянието.
    on_no_internet: опционален callback(), извиква се ако edge-tts не може
                     да се достигне (услугата е само online).
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
