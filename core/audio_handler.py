"""
AUDIO FUNCTIONALITY
"""

from utils.imports import QThread, QtCore, asyncio, edge_tts, tempfile, pygame, time, os
from utils.logging_setup import logger
from core.network import has_internet_connection


class AudioThread(QThread):
    finished_signal = QtCore.pyqtSignal()
    no_internet_signal = QtCore.pyqtSignal()

    def __init__(self, text, audio_lang, speed=1.0):
        super().__init__()
        self.text = text
        self.audio_lang = audio_lang
        self.speed = speed  # 1.0 = normal speed (like YouTube's 0.5x/1x/1.5x/2x)
        self.temp_file = None
        self._stop_flag = False

    def run(self):
        asyncio.run(self._play_edge_tts())
        
    def stop(self):
        self._stop_flag = True
        # Stop can come before playback has started (the audio is still being
        # downloaded) - then the mixer isn't initialized yet and stop() would raise.
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except pygame.error as e:
            logger.warning(f"Could not stop playback: {e}")
        self.cleanup_temp_file()
        
    def cleanup_temp_file(self):
        """Clean up the temporary file"""
        try:
            # Stop the music first to release the file
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            
            # Short delay so the file gets released
            time.sleep(0.1)
            
            if self.temp_file:
                try:
                    os.remove(self.temp_file)
                    logger.info(f"Deleted temporary file: {self.temp_file}")
                except (OSError, TypeError) as e:
                    logger.warning(f"Error deleting file {self.temp_file}: {e}")
                    
        except Exception as e:
            logger.error(f"General error during cleanup: {e}", exc_info=True)
        finally:
            self.temp_file = None
        
    def __del__(self):
        """Destructor - guarantees cleanup when the object is deleted"""
        if getattr(self, "temp_file", None):  # getattr - __init__ may not have got this far
            self.cleanup_temp_file()

    async def _play_edge_tts(self):
        try:
            if not has_internet_connection():
                self.no_internet_signal.emit()
                return
            path = await self._download_audio()
            if self._stop_flag:
                return  # stopped while downloading - don't start playing
            self._play_audio_blocking(path)
        except Exception as e:
            logger.error(f"Audio playback error: {e}", exc_info=True)
        finally:
            if self.temp_file is not None:
                self.cleanup_temp_file()
            self.finished_signal.emit()

    async def _download_audio(self):
        """Downloads the synthesized speech (edge-tts) into a local temporary .mp3 file."""
        # edge-tts expects rate as a percentage offset from normal speed
        # (e.g. "+50%"), not a multiplier - a 1.5x value -> "+50%".
        rate_percent = round((self.speed - 1.0) * 100)
        rate_str = f"{rate_percent:+d}%"
        communicate = edge_tts.Communicate(self.text, voice=self.audio_lang, rate=rate_str)
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        self.temp_file = path

        # The file is opened once for all chunks (not once per chunk).
        with open(path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

        return path

    def _play_audio_blocking(self, path):
        """Plays the downloaded .mp3 and waits (checking _stop_flag) until it finishes."""
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
    Fetches the list of available edge-tts voices (e.g. "bg-BG-KalinaNeural"),
    so the audio language dropdown in Settings can show a real list instead
    of the user guessing/looking up names themselves. Requires network -
    if it fails, the field simply stays editable, as before.
    """

    voices_ready = QtCore.pyqtSignal(list)  # sorted list of ShortName strings
    failed = QtCore.pyqtSignal(str)

    def run(self):
        try:
            voices = asyncio.run(edge_tts.list_voices())
            names = sorted(v["ShortName"] for v in voices if v.get("ShortName"))
            self.voices_ready.emit(names)
        except Exception as e:
            logger.error(f"Error fetching edge-tts voices: {e}", exc_info=True)
            self.failed.emit(str(e))