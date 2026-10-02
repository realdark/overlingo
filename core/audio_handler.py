"""
АУДИО ФУНКЦИОНАЛНОСТ
"""

from utils.imports import QThread, QtCore, asyncio, edge_tts, tempfile, pygame, time, os
from utils.logging_setup import logger
from core.network import has_internet_connection


class AudioThread(QThread):
    finished_signal = QtCore.pyqtSignal()  # ✅ Сега QtCore е импортиран
    no_internet_signal = QtCore.pyqtSignal()

    def __init__(self, text, audio_lang, speed=1.0):
        super().__init__()
        self.text = text
        self.audio_lang = audio_lang
        self.speed = speed  # 1.0 = нормална скорост (както YouTube-ските 0.5x/1x/1.5x/2x)
        self.temp_file = None
        self._stop_flag = False

    def run(self):
        asyncio.run(self._play_edge_tts())
        
    def stop(self):
        self._stop_flag = True
        pygame.mixer.music.stop()
        self.cleanup_temp_file()
        
    def cleanup_temp_file(self):
        """Почистване на временния файл"""
        try:
            # Спираме музиката първо, за да освободим файла
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            
            # Малка забавяка за да се освободи файла
            time.sleep(0.1)
            
            # Директно опитваме да изтрием, без сложни проверки
            if hasattr(self, 'temp_file') and self.temp_file:
                try:
                    os.remove(self.temp_file)
                    logger.info(f"Изтрит временен файл: {self.temp_file}")
                except (OSError, TypeError) as e:
                    logger.warning(f"Грешка при изтриване на файл {self.temp_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Обща грешка при почистване: {e}", exc_info=True)
        finally:
            self.temp_file = None
        
    def __del__(self):
        """Деструктор - гарантира почистване при изтриване на обекта"""
        if hasattr(self, 'temp_file') and self.temp_file:
            self.cleanup_temp_file()

    async def _play_edge_tts(self):
        try:
            if not has_internet_connection():
                self.no_internet_signal.emit()
                return
            path = await self._download_audio()
            self._play_audio_blocking(path)
        except Exception as e:
            logger.error(f"Грешка при аудио възпроизвеждане: {e}", exc_info=True)
        finally:
            if hasattr(self, 'temp_file') and self.temp_file is not None:
                self.cleanup_temp_file()
            self.finished_signal.emit()

    async def _download_audio(self):
        """Изтегля синтезираната реч (edge-tts) в локален временен .mp3 файл."""
        # edge-tts очаква rate като процент отклонение от нормалната скорост
        # (напр. "+50%"), не множител - 1.5x стойност -> "+50%".
        rate_percent = round((self.speed - 1.0) * 100)
        rate_str = f"{rate_percent:+d}%"
        communicate = edge_tts.Communicate(self.text, voice=self.audio_lang, rate=rate_str)
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        self.temp_file = path

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                with open(path, "ab") as f:
                    f.write(chunk["data"])

        return path

    def _play_audio_blocking(self, path):
        """Пуска изтегления .mp3 и изчаква (проверявайки _stop_flag), докато свърши."""
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if self._stop_flag:
                pygame.mixer.music.stop()
                break
            time.sleep(0.1)


class EdgeVoicesThread(QThread):
    """
    Извлича списъка с налични edge-tts гласове (напр. "bg-BG-KalinaNeural"),
    за да може падащото меню за аудио език в Settings да покаже реален
    списък, вместо потребителят да гадае/търси имена сам. Изисква мрежа -
    ако провалиш, полето просто си остава редактируемо, както преди.
    """

    voices_ready = QtCore.pyqtSignal(list)  # сортиран списък от ShortName низове
    failed = QtCore.pyqtSignal(str)

    def run(self):
        try:
            voices = asyncio.run(edge_tts.list_voices())
            names = sorted(v["ShortName"] for v in voices if v.get("ShortName"))
            self.voices_ready.emit(names)
        except Exception as e:
            logger.error(f"Грешка при извличане на edge-tts гласове: {e}", exc_info=True)
            self.failed.emit(str(e))