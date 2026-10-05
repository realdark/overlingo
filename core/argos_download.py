"""
СВАЛЯНЕ НА МОДЕЛИ ЗА ПРЕВОД БЕЗ ИНТЕРНЕТ (ARGOS) ОТ НАСТРОЙКИТЕ

Взима индекса на Argos, решава кои двойки трябват за превод "език на
оригинала -> целеви език" (директно или през английски), сваля липсващите
(~70 MB всяка) и ги разархивира в папката argos-models до програмата.
"""

from utils.imports import QThread, pyqtSignal, requests, tempfile, os, Path
from utils.logging_setup import logger
from core import argos


class ArgosDownloadThread(QThread):
    # двойка ("en → bg"), свалени байтове, общо байтове (-1 = неизвестно)
    progress = pyqtSignal(str, int, int)
    # success, message_key, params - при успех params["name"] са свалените двойки
    finished_download = pyqtSignal(bool, str, object)

    # Пазим референция към всяка пусната нишка, докато работи: ако диалогът
    # с настройките се затвори по време на сваляне, нишката не бива да бъде
    # унищожена от garbage collector-а ("QThread: Destroyed while running").
    # Служи и за това нов диалог да знае, че вече тече сваляне.
    _active = []

    def __init__(self, source_lang, target_lang):
        """Езиците са двубуквени ISO кодове ("en", "bg")."""
        super().__init__()
        self.source_lang = source_lang
        self.target_lang = target_lang

    @classmethod
    def is_busy(cls):
        """Има ли сваляне, което още тече (от този или от предишен диалог)."""
        cls._active[:] = [t for t in cls._active if t.isRunning()]
        return bool(cls._active)

    def start(self, *args):
        type(self)._active.append(self)
        super().start(*args)

    def run(self):
        try:
            headers = {"User-Agent": argos.USER_AGENT}
            response = requests.get(argos.INDEX_URL, headers=headers, timeout=30)
            response.raise_for_status()
            index = argos.parse_index(response.text)
            installed = argos.installed_pairs()
            needed = argos.pairs_to_download(self.source_lang, self.target_lang, index, installed)
            for pair in needed:
                self._download(pair, index[pair], headers)
            done = argos.find_route(self.source_lang, self.target_lang, argos.installed_pairs()) or []
            self.finished_download.emit(True, "", {"name": ", ".join(argos.pair_label(p) for p in done)})
        except argos.ArgosPackageUnavailableError as e:
            self.finished_download.emit(False, "argos_pair_unavailable", {"pair": str(e)})
        except requests.exceptions.RequestException as e:
            self.finished_download.emit(False, "network_error_detail", {"error": str(e)})
        except Exception as e:
            logger.error(f"Грешка при сваляне на модел за офлайн превод: {e}", exc_info=True)
            self.finished_download.emit(False, "unexpected_error_detail", {"error": str(e)})

    def _download(self, pair, url, headers):
        label = argos.pair_label(pair)
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", -1))
        downloaded = 0
        # Уникално име - две копия на програмата не си пречат.
        fd, name = tempfile.mkstemp(prefix=f"overlingo-argos-{pair[0]}_{pair[1]}-", suffix=".part")
        archive = Path(name)
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(label, downloaded, total)
            argos.install_package(archive, pair)
        finally:
            archive.unlink(missing_ok=True)
